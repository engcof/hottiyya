from fastapi import APIRouter, Request, Form, UploadFile, File, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from psycopg2.extras import RealDictCursor
from security.session import set_cache_headers
from postgresql import get_db_context
from security.csrf import generate_csrf_token, verify_csrf_token
from utils.permission import has_permission
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

# === عرض قائمة المقالات ===
@router.get("/", response_class=HTMLResponse)
async def list_articles(request: Request, page: int = 1):
    user = request.session.get("user")
    can_add = can(user, "add_article")
    
    per_page = 12
    offset = (page - 1) * per_page

    with get_db_context() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            # جلب المقالات مع عدد التعليقات
            cur.execute("""
                SELECT 
                    a.*,
                    u.username,
                    COUNT(c.id) as comments_count
                FROM articles a
                JOIN users u ON a.author_id = u.id
                LEFT JOIN comments c ON c.article_id = a.id
                GROUP BY a.id, u.username
                ORDER BY a.created_at DESC
                LIMIT %s OFFSET %s
            """, (per_page, offset))
            articles = cur.fetchall()

            # عدد الصفحات الكلي
            cur.execute("SELECT COUNT(*) FROM articles")
            total = cur.fetchone()["count"]
            total_pages = (total + per_page - 1) // per_page

    response = templates.TemplateResponse("articles/list.html", {
        "request": request,
        "user": user,
        "articles": articles,
        "can_add": can_add,
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
    
    # الصلاحيات أولاً
    can_edit = can(user, "edit_article")
    can_delete = can(user, "delete_article")
    can_comment = user is not None

    with get_db_context() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            # جيب المقال مع كل الحقول بوضوح
            cur.execute("""
                SELECT 
                    a.id,
                    a.title,
                    COALESCE(a.content, '') as content,
                    a.image_url,
                    a.created_at,
                    u.username
                FROM articles a
                JOIN users u ON a.author_id = u.id
                WHERE a.id = %s
            """, (id,))
            article = cur.fetchone()

            if not article:
                raise HTTPException(404, "المقال غير موجود")

            # جيب التعليقات
            cur.execute("""
                SELECT c.*, u.username
                FROM comments c
                JOIN users u ON c.user_id = u.id
                WHERE c.article_id = %s
                ORDER BY c.created_at DESC
            """, (id,))
            comments = cur.fetchall()

            # تأكد من الـ CSRF
            csrf_token = request.session.get("csrf_token") or generate_csrf_token()
            request.session["csrf_token"] = csrf_token

            return templates.TemplateResponse("articles/detail.html", {
                "request": request,
                "user": user,
                "article": article,
                "comments": comments,
                "csrf_token": csrf_token,
                "can_edit": can_edit,
                "can_delete": can_delete,
                "can_comment": can_comment
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
        # إرجاع الخطأ مع البيانات المدخلة سابقاً
        csrf_token = generate_csrf_token()
        request.session["csrf_token"] = csrf_token
        return templates.TemplateResponse("articles/add.html", {
            "request": request, "user": user, "csrf_token": csrf_token,
            "error": error,
            "form_data": {"title": title, "content": content} # تمرير البيانات غير النظيفة ليراها المستخدم
        })
        
    # استكمال عملية الرفع والحفظ
    if image and image.filename:
        try:
            with get_db_context() as conn:
                with conn.cursor() as cur:
                    # حفظ المقال أولاً للحصول على الـ id
                    cur.execute("""
                        INSERT INTO articles (title, content, author_id, image_url)
                        VALUES (%s, %s, %s, %s) RETURNING id
                    """, (title_safe, content_safe, user["id"], None)) # image_url = None مؤقتا
                    article_id = cur.fetchone()[0]
                    
                    # حفظ الصورة الآن
                    filename = f"article_{article_id}_{image.filename}"
                    path = f"static/uploads/articles/{filename}"
                    os.makedirs("static/uploads/articles", exist_ok=True)
                    with open(path, "wb") as f:
                        shutil.copyfileobj(image.file, f)
                    image_url = f"/{path}"
                    
                    # تحديث رابط الصورة بعد الحفظ
                    cur.execute("UPDATE articles SET image_url = %s WHERE id = %s", (image_url, article_id))
                    conn.commit()
        except Exception:
            # معالجة فشل الحفظ
            raise HTTPException(500, "فشل في حفظ المقال في قاعدة البيانات.")

    else:
        # حفظ المقال بدون صورة
        with get_db_context() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO articles (title, content, author_id, image_url)
                    VALUES (%s, %s, %s, %s) RETURNING id
                """, (title_safe, content_safe, user["id"], None))
                article_id = cur.fetchone()[0]
                conn.commit()

    return RedirectResponse(f"/articles/{article_id}", status_code=303)

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
        "article": article,      # صحيح
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
    if not can(user, "edit_article"):
        return RedirectResponse("/articles")

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
    
    image_url = None
    # محاولة الحصول على image_url القديمة أولاً في حال عدم وجود صورة جديدة
    with get_db_context() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("SELECT image_url FROM articles WHERE id = %s", (id,))
            old_image = cur.fetchone()
            if old_image:
                image_url = old_image["image_url"]

    if image and image.filename:
        filename = f"article_{id}_{image.filename}"
        path = f"static/uploads/articles/{filename}"
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "wb") as f:
            shutil.copyfileobj(image.file, f)
        image_url = f"/{path}" # تحديث الرابط الجديد

    with get_db_context() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                UPDATE articles 
                SET title = %s, content = %s, image_url = %s 
                WHERE id = %s
            """, (title_safe, content_safe, image_url, id))
            conn.commit()

    return RedirectResponse(f"/articles/{id}", status_code=303)

# === حذف مقال ===
@router.post("/delete/{id:int}")
async def delete_article(request: Request, id: int):
    if not can(request.session.get("user"), "delete_article"):
        return RedirectResponse("/articles")

    form = await request.form()
    verify_csrf_token(request, form.get("csrf_token"))

    with get_db_context() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM articles WHERE id = %s", (id,))
            conn.commit()
    return RedirectResponse("/articles", status_code=303)

# === إضافة تعليق ===
@router.post("/{id:int}/comment")
async def add_comment(request: Request, id: int, content: str = Form(...)):
    user = request.session.get("user")
    if not user:
        return RedirectResponse("/auth/login")

    form = await request.form()
    verify_csrf_token(request, form.get("csrf_token"))

    # تطبيق html.escape لمنع XSS قبل الحفظ
    content_safe = html.escape(content)

    with get_db_context() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO comments (article_id, user_id, content)
                VALUES (%s, %s, %s)
            """, (id, user["id"], content_safe)) # استخدام المتغير النظيف
            conn.commit()

    return RedirectResponse(f"/articles/{id}#comments", status_code=303)

# === حذف تعليق ===
@router.post("/{article_id:int}/comment/{comment_id:int}/delete")
async def delete_comment(request: Request, article_id: int, comment_id: int):
    user = request.session.get("user")
    if not user:
        return RedirectResponse("/auth/login")

    # تحقق من CSRF
    form = await request.form()
    verify_csrf_token(request, form.get("csrf_token"))

    # جلب معلومات التعليق للتحقق من الصلاحية
    with get_db_context() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("SELECT user_id FROM comments WHERE id = %s", (comment_id,))
            comment = cur.fetchone()
            if not comment:
                raise HTTPException(404, "التعليق غير موجود")

            # الشروط المسموح لها بالحذف:
            allowed = (
                user.get("role") == "admin" or
                user.get("id") == comment["user_id"] or
                has_permission(user.get("id"), "delete_comment")
            )

            if not allowed:
                raise HTTPException(403, "غير مسموح لك بحذف هذا التعليق")

            # حذف التعليق
            cur.execute("DELETE FROM comments WHERE id = %s", (comment_id,))
            conn.commit()

    return RedirectResponse(f"/articles/{article_id}#comments", status_code=303)