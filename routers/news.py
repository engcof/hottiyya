
from fastapi import APIRouter, Request, Form, UploadFile, File, Depends, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from psycopg2.extras import RealDictCursor
from fastapi.templating import Jinja2Templates
from security.session import get_current_user
from postgresql import get_db_context
import shutil
import os


router = APIRouter(prefix="/news", tags=["news"])
templates = Jinja2Templates(directory="templates")

UPLOAD_DIR = "static/uploads/news"
os.makedirs(UPLOAD_DIR, exist_ok=True)

@router.get("/", response_class=HTMLResponse)
async def list_news(request: Request):
    user = request.session.get("user")
    with get_db_context() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("SELECT * FROM news ORDER BY created_at DESC")
            news = cur.fetchall()
    return templates.TemplateResponse("news/list.html", {
        "request": request, 
        "user": user,
        "news": news
        })

@router.get("/{id}", response_class=HTMLResponse)
async def view_news(request: Request, id: int):
    with get_db_context() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("SELECT * FROM news WHERE id = %s", (id,))
            item = cur.fetchone()
            if not item:
                raise HTTPException(404, "الخبر غير موجود")
    return templates.TemplateResponse("news/detail.html", {"request": request, "item": item})

@router.get("/add", response_class=HTMLResponse)
async def add_news_form(request: Request):
    user = request.session.get("user")
    if not user or user.get("role") != "admin":
        return RedirectResponse("/auth/login")
    return templates.TemplateResponse("news/add.html", {"request": request})

@router.post("/add")
async def add_news(
    request: Request,
    title: str = Form(...),
    content: str = Form(...),
    author: str = Form(...),
    image: UploadFile = File(None)
):
    user = request.session.get("user")
    if not user or user.get("role") != "admin":
        return RedirectResponse("/auth/login")

    image_path = None
    if image and image.filename:
        image_path = os.path.join(UPLOAD_DIR, image.filename)
        with open(image_path, "wb") as f:
            shutil.copyfileobj(image.file, f)

    with get_db_context() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO news (title, content, author, image_path)
                VALUES (%s, %s, %s, %s)
            """, (title, content, author, image_path))
            conn.commit()

    return RedirectResponse("/news", status_code=303)