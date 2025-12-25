from fastapi import APIRouter, Request, Form, UploadFile, File, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from psycopg2.extras import RealDictCursor
from security.session import set_cache_headers
from postgresql import get_db_context
from security.csrf import generate_csrf_token, verify_csrf_token
from utils.permission import has_permission
from services.analytics import log_action
from services.article_service import ArticleService
import shutil
import os
from core.templates import templates
import html 
import re # تم إضافة استيراد المكتبة للتحقق من الصيغة

router = APIRouter(prefix="/articles", tags=["articles"])


# دالة مساعدة للصلاحيات (الأدمن عنده كل شيء)
def can(user: dict | None, perm: str) -> bool:
    if not user:
        return False
    if user.get("role") == "admin":
        return True
    user_id = user.get("id")
    return user_id and has_permission(user_id, perm)

# === عرض قائمة المقالات (باستخدام الخدمة) ===
@router.get("/", response_class=HTMLResponse)
async def list_articles(request: Request, page: int = 1):
    user = request.session.get("user")
    can_add = can(user, "add_article")
    can_delete = can(user, "delete_article") 


    csrf_token = generate_csrf_token()
    request.session["csrf_token"] = csrf_token
    # استدعاء الخدمة لجلب البيانات والترقيم
    articles, total_pages = ArticleService.get_all_articles(page=page, per_page=12)

    response = templates.TemplateResponse("articles/list.html", {
        "request": request,
        "user": user,
        "articles": articles,
        "can_add": can_add,
        "csrf_token": csrf_token,
        "page": page,
        "total_pages": total_pages,
        "has_prev": page > 1,
        "has_next": page < total_pages
    })
    set_cache_headers(response)
    return response


# === 🌟 التوجيه إلى أحدث مقال (مسار ثابت) 🌟 ===
@router.get("/latest")
async def latest_article_redirect():
    with get_db_context() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            # 1. جلب ID أحدث مقال فقط
            cur.execute("""
                SELECT id 
                FROM articles 
                ORDER BY created_at DESC 
                LIMIT 1
            """)
            latest = cur.fetchone()
            
            if not latest:
                # إذا لم يكن هناك مقالات، وجههم إلى صفحة قائمة المقالات
                # نستخدم 303 Redirect لضمان أن المتصفح سيستخدم GET
                return RedirectResponse("/articles", status_code=303)
                
            # 2. التوجيه إلى صفحة المقال الفعلي باستخدام ID
            return RedirectResponse(f"/articles/{latest['id']}", status_code=303)

# === عرض مقال + التعليقات ===
@router.get("/{id:int}", response_class=HTMLResponse)
async def view_article(request: Request, id: int):
    user = request.session.get("user")
    article, comments = ArticleService.get_article_details(id)
    
    if not article: raise HTTPException(404, "المقال غير موجود")

    csrf_token = request.session.get("csrf_token") or generate_csrf_token()
    request.session["csrf_token"] = csrf_token

    return templates.TemplateResponse("articles/detail.html", {
        "request": request, "user": user, "article": article, "comments": comments,
        "csrf_token": csrf_token,
        "can_edit": can(user, "edit_article"),
        "can_delete": can(user, "delete_article"),
        "can_comment": user is not None
    })


# === إضافة مقال ===
@router.get("/add", response_class=HTMLResponse)
async def add_article_form(request: Request):
    user = request.session.get("user")
    if not can(user, "add_article"):
        return RedirectResponse("/articles")
    
    csrf_token = generate_csrf_token()
    request.session["csrf_token"] = csrf_token
    # تمرير form_data فارغة مبدئيا لتجنب الأخطاء في القالب
    return templates.TemplateResponse("articles/add.html", {
        "request": request, "user": user, "csrf_token": csrf_token, "form_data": {}
    })

@router.post("/add")
async def add_article(
    request: Request,
    title: str = Form(...),
    content: str = Form(...),
    image: UploadFile = File(None)
):
    user = request.session.get("user")
    if not can(user, "add_article"):
        return RedirectResponse("/articles")

    # التحقق من CSRF والنظافة (كما في كودك)
    form = await request.form()
    verify_csrf_token(request, form.get("csrf_token"))
    
    # تطبيق html.escape لمنع XSS قبل الحفظ
    title_stripped = title.strip()
    content_stripped = content.strip()
    title_safe = html.escape(title_stripped)
    content_safe = html.escape(content_stripped)
    
    error = None

    # التعبير النمطي الجديد يدعم العربية والإنجليزية والأرقام وعلامات الترقيم الشائعة
    VALID_TITLE_REGEX = r"[\u0600-\u06FFa-zA-Z\s\d\.\,\!\؟\-\(\)]+"
    VALID_CONTENT_REGEX = r"[\u0600-\u06FFa-zA-Z\s\d\.\,\!\؟\-\(\)\n\r]+"

    # 1. التحقق من عدم فراغ العنوان والمحتوى
    if not title_stripped:
        error = "عنوان المقال مطلوب."
    elif not content_stripped:
        error = "محتوى المقال مطلوب."
    
    # 2. التحقق من نظافة العنوان 
    elif not re.fullmatch(VALID_TITLE_REGEX, title_stripped):
        error = "العنوان يحتوي على رموز غير مسموح بها. يُسمح بالعربية والإنجليزية والأرقام وعلامات الترقيم الشائعة فقط."
        
    # 3. التحقق من نظافة المحتوى
    elif not re.fullmatch(VALID_CONTENT_REGEX, content_stripped):
        error = "المقال يحتوي على رموز غير مسموح بها في المحتوى. يُسمح بالعربية والإنجليزية والأرقام وعلامات الترقيم الشائعة فقط."

    image_url = None
    if image and image.filename:
        # إذا كان هناك خطأ، لن يتم الرفع على أي حال، لكن نستمر في الفحص
        pass
        
    if error:
        print(f"⚠️ Validation Error: {error}") # أضف هذا السطر للتشخيص
        csrf_token = generate_csrf_token()
        request.session["csrf_token"] = csrf_token
        return templates.TemplateResponse("articles/add.html", {
            "request": request, "user": user, "csrf_token": csrf_token,
            "error": error,
            "form_data": {"title": title, "content": content} # تمرير البيانات غير النظيفة ليراها المستخدم
        })
    try:
        # في حالة أردت التأكد من إغلاق الملف يدوياً (اختياري لأن FastAPI يقوم بذلك أحياناً)
        image_data = image.file if image and image.filename else None

        article_id = ArticleService.create_article(
            title=title_safe,
            content=content_safe,
            author_id=user["id"],
            image_file=image_data
        )

        if image:
            await image.close() # إغلاق الملف بعد الانتهاء

        # 2. ✅ إضافة العملية لسجل النشاطات
        
        log_action(
            user_id=user["id"], 
            action="إضافة مقال", 
            details=f"تم نشر مقال جديد بعنوان: {title_safe}"
        )    
        
        return RedirectResponse(f"/articles/{article_id}", status_code=303)
        
    except Exception as e:
        print(f"❌ Error: {e}")
        raise HTTPException(500, "حدث خطأ أثناء حفظ المقال")    
  
# === تعديل مقال ===
@router.get("/edit/{id:int}", response_class=HTMLResponse)
async def edit_article_form(request: Request, id: int):
    user = request.session.get("user")
    if not can(user, "edit_article"):
        return RedirectResponse("/articles")

    with get_db_context() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("SELECT * FROM articles WHERE id = %s", (id,))
            article = cur.fetchone()
            if not article:
                raise HTTPException(404, "المقال غير موجود")

    csrf_token = generate_csrf_token()
    request.session["csrf_token"] = csrf_token

    return templates.TemplateResponse("articles/edit.html", {
        "request": request,
        "user": user,
        "article": article,      
        "csrf_token": csrf_token
    })

# === حفظ التعديلات ===
@router.post("/edit/{id:int}")
async def update_article(
    request: Request, 
    id: int, 
    title: str = Form(...), 
    content: str = Form(...), 
    image: UploadFile = File(None)
):
    user = request.session.get("user")
    if not can(user, "edit_article"): return RedirectResponse("/articles")

    form = await request.form()
    verify_csrf_token(request, form.get("csrf_token"))

    # تطبيق html.escape لمنع XSS قبل الحفظ
    title_stripped = title.strip()
    content_stripped = content.strip()
    title_safe = html.escape(title_stripped)
    content_safe = html.escape(content_stripped)
    
    error = None

    # 1. تحديث الرموز المسموحة لتشمل علامات الترقيم الإضافية (مثل : ; " ' / + = _)
    VALID_TITLE_REGEX = r"[\u0600-\u06FFa-zA-Z\s\d\.\,\!\؟\-\(\)\[\]\{\}\:\/\'\"]+"
    VALID_CONTENT_REGEX = r"[\u0600-\u06FFa-zA-Z\s\d\.\,\!\؟\-\(\)\[\]\{\}\:\/\'\"\+\=\_\%\&\@\*\n\r]+"


    # 1. التحقق من عدم فراغ العنوان والمحتوى
    if not title_stripped:
        error = "عنوان المقال مطلوب."
    elif not content_stripped:
        error = "محتوى المقال مطلوب."
    
    # 2. التحقق من نظافة العنوان
    elif not re.fullmatch(VALID_TITLE_REGEX, title_stripped):
        error = "العنوان يحتوي على رموز غير مسموح بها. يُسمح بالعربية والإنجليزية والأرقام وعلامات الترقيم الشائعة فقط."
        
    # 3. التحقق من نظافة المحتوى
    elif not re.fullmatch(VALID_CONTENT_REGEX, content_stripped):
        error = "المقال يحتوي على رموز غير مسموح بها في المحتوى. يُسمح بالعربية والإنجليزية والأرقام وعلامات الترقيم الشائعة فقط."


    # في حالة وجود خطأ، يجب إعادة تحميل النموذج مع البيانات المدخلة
    if error:
        csrf_token = generate_csrf_token()
        request.session["csrf_token"] = csrf_token
        
        # جلب البيانات الأصلية للمقال لاستخدامها في القالب
        with get_db_context() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("SELECT * FROM articles WHERE id = %s", (id,))
                article = cur.fetchone()
                if not article:
                    raise HTTPException(404, "المقال غير موجود أثناء التعديل.")
        
        # استبدال العنوان والمحتوى بالمدخلات الجديدة لعرض الخطأ
        article['title'] = title
        article['content'] = content

        return templates.TemplateResponse("articles/edit.html", {
            "request": request, "user": user, "article": article,
            "csrf_token": csrf_token, "error": error
        })

    # استكمال عملية حفظ التعديلات
    ArticleService.update_article(
        article_id=id, 
        title=html.escape(title.strip()), 
        content=html.escape(content.strip()), 
        image_file=image.file if image and image.filename else None
    )

    # 🌟 إضافة سجل النشاطات (Analytics) 
    log_action(
        user_id=user["id"], 
        action="تعديل مقال", 
        details=f"قام {user['username']} بتعديل المقال رقم ({id}) بعنوان: {title[:50]}..."
    )
    return RedirectResponse(f"/articles/{id}", status_code=303)

# === حذف مقال ===
@router.post("/delete/{id:int}")
async def delete_article(request: Request, id: int):
    user = request.session.get("user")
    if not can(user, "delete_article"): 
        return RedirectResponse("/articles")

    form = await request.form()
    verify_csrf_token(request, form.get("csrf_token"))

    # جلب عنوان المقال قبل الحذف لاستخدامه في سجل النشاطات
    article_data = ArticleService.get_article_details(id)
    title = article_data[0]['title'] if article_data[0] else "مقال غير معروف"

    # تنفيذ عملية الحذف الشاملة
    ArticleService.delete_article(id)

    # 🌟 تسجيل عملية الحذف في السجل
    log_action(
        user_id=user["id"], 
        action="حذف مقال", 
        details=f"قام {user['username']} بحذف المقال رقم ({id}) بعنوان: {title} مع كافة ملحقاته"
    )

    return RedirectResponse("/articles", status_code=303)    

# === إضافة تعليق ===
@router.post("/{id:int}/comment")
async def add_comment(request: Request, id: int, content: str = Form(...)):
    user = request.session.get("user")
    if not user: return RedirectResponse("/auth/login")

    # 🌟 التحقق من الصلاحية: يجب أن يكون مسجلاً ويمتلك صلاحية إضافة تعليق
    if not user or not can(user, "add_comment"):
        return RedirectResponse(f"/articles/{id}", status_code=303)
    

    form = await request.form()
    verify_csrf_token(request, form.get("csrf_token"))

    content_safe = html.escape(content.strip())
    
    # تنفيذ الإضافة عبر السيرفس
    ArticleService.add_comment(id, user["id"], content_safe)

    # 🌟 تسجيل النشاط
    log_action(
        user_id=user["id"],
        action="إضافة تعليق",
        details=f"قام {user['username']} بالتعليق على المقال رقم ({id})"
    )

    return RedirectResponse(f"/articles/{id}#comments", status_code=303)

# === حذف تعليق ===
@router.post("/{article_id:int}/comment/{comment_id:int}/delete")
async def delete_comment(request: Request, article_id: int, comment_id: int):
    user = request.session.get("user")
    if not user: return RedirectResponse("/auth/login")

    verify_csrf_token(request, (await request.form()).get("csrf_token"))

    # جلب بيانات التعليق للتحقق والتسجيل
    comment = ArticleService.get_comment_owner(comment_id)
    if not comment: raise HTTPException(404, "التعليق غير موجود")
    
        
    # التحقق من الصلاحية
    allowed = (
        user.get("role") == "admin" or
        user.get("id") == comment["user_id"] or
        has_permission(user.get("id"), "delete_comment")
    )
    if not allowed: raise HTTPException(403, "غير مسموح لك بالحذف")

    # تنفيذ الحذف عبر السيرفس
    ArticleService.delete_comment(comment_id)

    # 🌟 تسجيل النشاط
    log_action(
        user_id=user["id"],
        action="حذف تعليق",
        details=f"قام {user['username']} بحذف تعليق في المقال ({article_id}). نص التعليق: {comment['content'][:30]}..."
    )

    return RedirectResponse(f"/articles/{article_id}#comments", status_code=303)

