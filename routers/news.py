from fastapi import APIRouter, Request, Form, UploadFile, File, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from postgresql import get_db_context
from psycopg2.extras import RealDictCursor
from security.csrf import generate_csrf_token, verify_csrf_token
from utils.permissions import has_permission  # ← أضف هذا
import shutil
import os

router = APIRouter(prefix="/news", tags=["news"])
templates = Jinja2Templates(directory="templates")
UPLOAD_DIR = "static/uploads/news"
os.makedirs(UPLOAD_DIR, exist_ok=True)

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
    
    return templates.TemplateResponse("news/list.html", {
        "request": request,
        "user": user,
        "news": news,
        "can_add": can_add
    })

# routers/news.py → أضف أو استبدل المسار ده
@router.get("/{id:int}", response_class=HTMLResponse)
async def view_news(request: Request, id: int):
    user = request.session.get("user")
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

    return templates.TemplateResponse("news/detail.html", {
        "request": request,
        "user": user,
        "item": item,
        "csrf_token": csrf_token
    })

# === إضافة خبر ===
@router.get("/add", response_class=HTMLResponse)
async def add_news_form(request: Request):
    if not check_permission(request, "add_news"):
        return RedirectResponse("/auth/login", status_code=303)

    csrf_token = generate_csrf_token()
    request.session["csrf_token"] = csrf_token
    return templates.TemplateResponse("news/add.html", {
        "request": request,
        "user": request.session.get("user"),
        "csrf_token": csrf_token
    })

@router.post("/add")
async def add_news(
    request: Request,
    form_data = Form(...),
    title: str = Form(...),
    content: str = Form(...),
    author: str = Form(...),
    image: UploadFile = File(None)
):
    if not check_permission(request, "add_news"):
        return RedirectResponse("/auth/login")

    form = await request.form()
    verify_csrf_token(request, form.get("csrf_token"))

    image_url = None
    if image and image.filename:
        image_url = f"/static/uploads/news/{image.filename}"
        image_path = os.path.join(UPLOAD_DIR, image.filename)
        with open(image_path, "wb") as f:
            shutil.copyfileobj(image.file, f)

    with get_db_context() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO news (title, content, author, image_url)
                VALUES (%s, %s, %s, %s)
            """, (title, content, author, image_url))
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

    return templates.TemplateResponse("news/edit.html", {
        "request": request,
        "user": user,
        "item": item,
        "csrf_token": csrf_token
    })


@router.post("/edit/{id:int}")
async def update_news(
    request: Request,
    id: int,
    form_data = Form(...),
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

    image_url = None
    if image and image.filename:
        image_url = f"/static/uploads/news/{image.filename}"
        image_path = os.path.join(UPLOAD_DIR, image.filename)
        with open(image_path, "wb") as f:
            shutil.copyfileobj(image.file, f)

    with get_db_context() as conn:
        with conn.cursor() as cur:
            if image_url:
                cur.execute("""
                    UPDATE news SET title=%s, content=%s, author=%s, image_url=%s
                    WHERE id=%s
                """, (title, content, author, image_url, id))
            else:
                cur.execute("""
                    UPDATE news SET title=%s, content=%s, author=%s
                    WHERE id=%s
                """, (title, content, author, id))
            conn.commit()

    return RedirectResponse("/news", status_code=303)


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