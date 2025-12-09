from fastapi import APIRouter, Request, Form, UploadFile, File, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from postgresql import get_db_context
from psycopg2.extras import RealDictCursor
from security.csrf import generate_csrf_token, verify_csrf_token
from utils.permission import has_permission
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


def check_permission(request: Request, perm: str) -> bool:
    user = request.session.get("user")
    if not user:
        return False
    
    # الأدمن عنده كل الصلاحيات تلقائيًا
    if user.get("role") == "admin":
        return True
    
    # تأكد من وجود id قبل الاستخدام
    user_id = user.get("id")
    if not user_id:
        return False  # لو ما فيه id → ما نعطيه صلاحية
    
    return has_permission(user_id, perm)

# === عرض الأخبار ===
@router.get("/", response_class=HTMLResponse)
async def list_news(request: Request):
    user = request.session.get("user")
    user_id = user.get("id") if user else None
    can_add = user_id and (user.get("role") == "admin" or has_permission(user_id, "add_news"))
    
    with get_db_context() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("SELECT * FROM news ORDER BY created_at DESC")
            news = cur.fetchall()
    
    response = templates.TemplateResponse("news/list.html", {
        "request": request,
        "user": user,
        "news": news,
        "can_add": can_add
    })
    set_cache_headers(response)
    return response

# routers/news.py → أضف أو استبدل المسار ده
@router.get("/{id:int}", response_class=HTMLResponse)
async def view_news(request: Request, id: int):
    user = request.session.get("user")
    # === الحل السحري: حدد الصلاحيات هنا ===
    can_edit = check_permission(request, "edit_news")
    can_delete = check_permission(request, "delete_news")        

    with get_db_context() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("SELECT * FROM news WHERE id = %s", (id,))
            item = cur.fetchone()
            if not item:
                raise HTTPException(404, "الخبر غير موجود")
            
    

    # أضف CSRF للحذف
    csrf_token = request.session.get("csrf_token")
    if not csrf_token:
        csrf_token = generate_csrf_token()
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
    if not check_permission(request, "add_news"):
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
    image: UploadFile = File(None)
):
    if not check_permission(request, "add_news"):
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

    image_url = None
    if image and image.filename:
        # ملاحظة: من الأفضل استخدام UUID في اسم الملف لتجنب التكرار
        filename = f"{os.path.basename(image.filename)}" # استخدام اسم الملف مباشرةً
        image_path = os.path.join(UPLOAD_DIR, filename)
        with open(image_path, "wb") as f:
            shutil.copyfileobj(image.file, f)
        image_url = f"/static/uploads/news/{filename}"


    with get_db_context() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO news (title, content, author, image_url)
                VALUES (%s, %s, %s, %s)
            """, (title_safe, content_safe, author_safe, image_url))
            conn.commit()

    return RedirectResponse("/news", status_code=303)

# === تعديل الخبر ===
@router.get("/edit/{id:int}", response_class=HTMLResponse)
async def edit_news_form(request: Request, id: int):
    user = request.session.get("user")
    if not check_permission(request, "edit_news"):
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
    
    if not check_permission(request, "edit_news"):
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


    # تنظيف البيانات باستخدام html.escape لمنع XSS
    title_safe = html.escape(title_stripped)
    content_safe = html.escape(content_stripped)
    author_safe = html.escape(author_stripped)


    image_url = None
    # الحصول على رابط الصورة القديم في حال عدم رفع صورة جديدة
    with get_db_context() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("SELECT image_url FROM news WHERE id = %s", (id,))
            old_image = cur.fetchone()
            if old_image:
                image_url = old_image["image_url"]

    # التعامل مع رفع صورة جديدة
    if image and image.filename:
        filename = f"{os.path.basename(image.filename)}"
        image_path = os.path.join(UPLOAD_DIR, filename)
        with open(image_path, "wb") as f:
            shutil.copyfileobj(image.file, f)
        image_url = f"/static/uploads/news/{filename}"


    with get_db_context() as conn:
        with conn.cursor() as cur:
            if image_url:
                cur.execute("""
                    UPDATE news SET title=%s, content=%s, author=%s, image_url=%s
                    WHERE id=%s
                """, (title_safe, content_safe, author_safe, image_url, id))
            else:
                cur.execute("""
                    UPDATE news SET title=%s, content=%s, author=%s
                    WHERE id=%s
                """, (title_safe, content_safe, author_safe, id))
            conn.commit()

    return RedirectResponse(f"/news/{id}", status_code=303)


# === حذف الخبر ===
@router.post("/delete/{id:int}")
async def delete_news(request: Request, id: int):
    if not check_permission(request, "delete_news"):
        return RedirectResponse("/news")

    # تحقق من CSRF
    form = await request.form()
    verify_csrf_token(request, form.get("csrf_token"))

    # احذف الصورة إذا وجدت
    with get_db_context() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("SELECT image_url FROM news WHERE id = %s", (id,))
            item = cur.fetchone()
            if item and item["image_url"]:
                image_path = os.path.join("static", item["image_url"].lstrip("/"))
                if os.path.exists(image_path):
                    os.remove(image_path)

            cur.execute("DELETE FROM news WHERE id = %s", (id,))
            conn.commit()

    return RedirectResponse("/news", status_code=303)