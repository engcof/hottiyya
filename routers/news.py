from fastapi import APIRouter, Request, Form, UploadFile, File, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from psycopg2.extras import RealDictCursor
from services.news_service import NewsService
from services.analytics import log_action
from postgresql import get_db_context

from security.csrf import generate_csrf_token, verify_csrf_token
from utils.permission import can
from security.session import set_cache_headers
from core.templates import templates
import shutil
import os
import html # تم إضافة استيراد html
import re   # تم إضافة استيراد re

router = APIRouter(prefix="/news", tags=["news"])

UPLOAD_DIR = "static/uploads/news"
os.makedirs(UPLOAD_DIR, exist_ok=True)

# التعبيرات النمطية للتحقق من نظافة المحتوى (عربي، إنجليزي، أرقام، علامات ترقيم شائعة)
VALID_TITLE_REGEX = r"[\u0600-\u06FFa-zA-Z\s\d\.\,\!\؟\-\(\)]+"
VALID_CONTENT_REGEX = r"[\u0600-\u06FFa-zA-Z\s\d\.\,\!\؟\-\(\)\n\r]+"
VALID_AUTHOR_REGEX = r"[\u0600-\u06FFa-zA-Z\s\d\.\,\!\؟\-\(\)]+"



# === عرض الأخبار (القائمة) ===
@router.get("/", response_class=HTMLResponse)
async def list_news(request: Request):
    user = request.session.get("user")
    # التحقق من صلاحية الإضافة لغرض عرض الزر في القالب
    can_add = can(user, "add_news")
    
    # استخدام السيرفس لجلب الأخبار
    news = NewsService.get_all_news()
    
    response = templates.TemplateResponse("news/list.html", {
        "request": request,
        "user": user,
        "news": news,
        "can_add": can_add
    })
    set_cache_headers(response)
    return response

# === عرض تفاصيل الخبر ===
@router.get("/{id:int}", response_class=HTMLResponse)
async def view_news(request: Request, id: int):
    user = request.session.get("user")
    
    # جلب الخبر من السيرفس
    item = NewsService.get_news_by_id(id)
    if not item:
        raise HTTPException(404, "الخبر غير موجود")
            
    # تحديد صلاحيات التعديل والحذف لهذا المستخدم
    can_edit = can(user, "edit_news")
    can_delete = can(user,  "delete_news")

    # إدارة توكن CSRF للحذف الآمن
    csrf_token = request.session.get("csrf_token") or generate_csrf_token()
    request.session["csrf_token"] = csrf_token

    response = templates.TemplateResponse("news/detail.html", {
        "request": request,
        "user": user,
        "item": item,
        "can_edit": can_edit,      
        "can_delete": can_delete,  
        "csrf_token": csrf_token
    })
    set_cache_headers(response)
    return response

# === إضافة خبر ===
@router.get("/add", response_class=HTMLResponse)
async def add_news_form(request: Request):
    user = request.session.get("user")
    if not can(user, "add_news"):
        return RedirectResponse("/auth/login", status_code=303)

    csrf_token = generate_csrf_token()
    request.session["csrf_token"] = csrf_token
    response = templates.TemplateResponse("news/add.html", {
        "request": request,
        "user": request.session.get("user"),
        "csrf_token": csrf_token,
        "form_data": {} # إضافة form_data فارغة
    })
    set_cache_headers(response)
    return response

@router.post("/add")
async def add_news(
    request: Request,
    title: str = Form(...),
    content: str = Form(...),
    author: str = Form(...),
    image: UploadFile = File(None) # هذا الحقل سيستقبل الصورة أو الفيديو
):
    user = request.session.get("user")
    if not can(user,  "add_news"):
        return RedirectResponse("/auth/login")

    form = await request.form()
    verify_csrf_token(request, form.get("csrf_token"))

    # التنظيف والتحقق
    title_stripped = title.strip()
    content_stripped = content.strip()
    author_stripped = author.strip()
    
    error = None

    if not title_stripped:
        error = "عنوان الخبر مطلوب."
    elif not content_stripped:
        error = "محتوى الخبر مطلوب."
    elif not author_stripped:
        error = "اسم الكاتب مطلوب."
    
    # التحقق من نظافة العنوان
    elif not re.fullmatch(VALID_TITLE_REGEX, title_stripped):
        error = "العنوان يحتوي على رموز غير مسموح بها. يُسمح بالعربية والإنجليزية والأرقام وعلامات الترقيم الشائعة فقط."
    # التحقق من نظافة المحتوى
    elif not re.fullmatch(VALID_CONTENT_REGEX, content_stripped):
        error = "المحتوى يحتوي على رموز غير مسموح بها. يُسمح بالعربية والإنجليزية والأرقام وعلامات الترقيم الشائعة فقط."
    # التحقق من نظافة الكاتب
    elif not re.fullmatch(VALID_AUTHOR_REGEX, author_stripped):
        error = "اسم الكاتب يحتوي على رموز غير مسموح بها."

    # في حال وجود خطأ، نعيد المستخدم إلى نموذج الإضافة مع رسالة الخطأ وبياناته
    if error:
        csrf_token = generate_csrf_token()
        request.session["csrf_token"] = csrf_token
        return templates.TemplateResponse("news/add.html", {
            "request": request,
            "user": request.session.get("user"),
            "csrf_token": csrf_token,
            "error": error,
            "form_data": {"title": title, "content": content, "author": author}
        })


    # تنظيف البيانات باستخدام html.escape لمنع XSS
    title_safe = html.escape(title_stripped)
    content_safe = html.escape(content_stripped)
    author_safe = html.escape(author_stripped)
    try:
        # استخدام السيرفس للحفظ والرفع للسحابة
        news_id = NewsService.create_news(
            title=title_safe,
            content=content_safe,
            author=author_safe,
            media_file=image.file if image and image.filename else None
        )

        # تسجيل النشاط في السجل الشامل
        log_action(
            user_id=user["id"],
            action="إضافة خبر",
            details=f"قام {user['username']} بنشر خبر جديد بعنوان: {title[:50]}..."
        )

        return RedirectResponse(f"/news/{news_id}", status_code=303)
    except Exception as e:
        print(f"❌ Error: {e}")
        raise HTTPException(500, "حدث خطأ أثناء حفظ الخبر")
    
# === تعديل الخبر ===
@router.get("/edit/{id:int}", response_class=HTMLResponse)
async def edit_news_form(request: Request, id: int):
    user = request.session.get("user")
    if not can(user,  "edit_news"):
        return RedirectResponse("/news")

    with get_db_context() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("SELECT * FROM news WHERE id = %s", (id,))
            item = cur.fetchone()
            if not item:
                raise HTTPException(404, "الخبر غير موجود")

    csrf_token = generate_csrf_token()
    request.session["csrf_token"] = csrf_token

    response = templates.TemplateResponse("news/edit.html", {
        "request": request,
        "user": user,
        "item": item,
        "csrf_token": csrf_token
    })
    set_cache_headers(response)
    return response

@router.post("/edit/{id:int}")
async def update_news(
    request: Request,
    id: int,
    title: str = Form(...),
    content: str = Form(...),
    author: str = Form(...),
    image: UploadFile = File(None)
):
    user = request.session.get("user")
    if not can(user, "edit_news"):
        return RedirectResponse("/news")

    # تحقق من CSRF
    form = await request.form()
    verify_csrf_token(request, form.get("csrf_token"))

    # التنظيف والتحقق
    title_stripped = title.strip()
    content_stripped = content.strip()
    author_stripped = author.strip()
    
    error = None

    if not title_stripped:
        error = "عنوان الخبر مطلوب."
    elif not content_stripped:
        error = "محتوى الخبر مطلوب."
    elif not author_stripped:
        error = "اسم الكاتب مطلوب."
    
    # التحقق من نظافة العنوان
    elif not re.fullmatch(VALID_TITLE_REGEX, title_stripped):
        error = "العنوان يحتوي على رموز غير مسموح بها. يُسمح بالعربية والإنجليزية والأرقام وعلامات الترقيم الشائعة فقط."
    # التحقق من نظافة المحتوى
    elif not re.fullmatch(VALID_CONTENT_REGEX, content_stripped):
        error = "المحتوى يحتوي على رموز غير مسموح بها. يُسمح بالعربية والإنجليزية والأرقام وعلامات الترقيم الشائعة فقط."
    # التحقق من نظافة الكاتب
    elif not re.fullmatch(VALID_AUTHOR_REGEX, author_stripped):
        error = "اسم الكاتب يحتوي على رموز غير مسموح بها."

    # في حال وجود خطأ، نعيد المستخدم إلى نموذج التعديل مع رسالة الخطأ وبياناته
    if error:
        csrf_token = generate_csrf_token()
        request.session["csrf_token"] = csrf_token
        
        with get_db_context() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("SELECT * FROM news WHERE id = %s", (id,))
                item = cur.fetchone()
                if not item:
                    raise HTTPException(404, "الخبر غير موجود أثناء التعديل.")
        
        # تحديث الحقول بقيم الـ Form الجديدة لعرضها للمستخدم
        item['title'] = title
        item['content'] = content
        item['author'] = author

        return templates.TemplateResponse("news/edit.html", {
            "request": request,
            "user": request.session.get("user"),
            "item": item,
            "csrf_token": csrf_token,
            "error": error
        })


    
    try:
        # استخدام السيرفس المحدث
        success = NewsService.update_news(
            news_id=id,
            title=html.escape(title.strip()),
            content=html.escape(content.strip()),
            author=html.escape(author.strip()),
            media_file=image.file if image and image.filename else None
        )
        
        if success:
            # تسجيل النشاط في السجل الشامل
            log_action(
                user_id=user["id"],
                action="تعديل خبر",
                details=f"قام {user['username']} بتعديل الخبر رقم ({id}) بعنوان: {title_stripped[:30]}..."
            ) 
            return RedirectResponse(f"/news/{id}", status_code=303)
        raise HTTPException(404, "الخبر غير موجود")
    except Exception as e:
        print(f"❌ Error during update: {e}")
        raise HTTPException(500, "حدث خطأ داخلي أثناء التحديث")

@router.post("/delete/{id:int}")
async def delete_news(request: Request, id: int):
    user = request.session.get("user")
    if not can(user, "delete_news"):
        return RedirectResponse("/news")

    # التحقق من CSRF
    form = await request.form()
    verify_csrf_token(request, form.get("csrf_token"))

    try:
        # تنفيذ الحذف عبر السيرفس
        success = NewsService.delete_news(id)
        
        if success:
            # تسجيل العملية في السجل الشامل
            log_action(
                user_id=user["id"],
                action="حذف خبر",
                details=f"قام {user['username']} بحذف الخبر رقم ({id}) نهائياً مع ملفاته."
            )
            return RedirectResponse("/news", status_code=303)
        else:
            raise HTTPException(404, "الخبر غير موجود")
            
    except Exception as e:
        print(f"❌ Error during deletion: {e}")
        raise HTTPException(500, "حدث خطأ أثناء محاولة حذف الخبر")