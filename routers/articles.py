# routers/articles.py
from fastapi import APIRouter, Request, Form, UploadFile, File, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from psycopg2.extras import RealDictCursor
from fastapi.templating import Jinja2Templates
from postgresql import get_db_context
from security.csrf import generate_csrf_token, verify_csrf_token
from utils.permissions import has_permission
import shutil
import os

router = APIRouter(prefix="/articles", tags=["articles"])
templates = Jinja2Templates(directory="templates")

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

    return templates.TemplateResponse("articles/list.html", {
        "request": request,
        "user": user,
        "articles": articles,
        "can_add": can_add,
        "page": page,
        "total_pages": total_pages,
        "has_prev": page > 1,
        "has_next": page < total_pages
    })

# === عرض مقال + التعليقات ===
@router.get("/{id:int}", response_class=HTMLResponse)
async def view_article(request: Request, id: int):
    user = request.session.get("user")
    can_edit = can(user, "edit_article")
    can_delete = can(user, "delete_article")
    can_comment = user is not None  # أي مستخدم مسجل دخول يقدر يعلق

    with get_db_context() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            # جلب المقال
            cur.execute("""
                SELECT a.*, u.username 
                FROM articles a 
                JOIN users u ON a.author_id = u.id 
                WHERE a.id = %s
            """, (id,))
            article = cur.fetchone()
            if not article:
                raise HTTPException(404, "المقال غير موجود")

            # جلب التعليقات
            cur.execute("""
                SELECT c.*, u.username 
                FROM comments c 
                JOIN users u ON c.user_id = u.id 
                WHERE c.article_id = %s 
                ORDER BY c.created_at DESC
            """, (id,))
            comments = cur.fetchall()

    # CSRF للتعليق والحذف
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
    return templates.TemplateResponse("articles/add.html", {
        "request": request, "user": user, "csrf_token": csrf_token
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

    image_url = None
    if image and image.filename:
        filename = f"article_{id}_{image.filename}" if 'id' in locals() else image.filename
        path = f"static/uploads/articles/{filename}"
        os.makedirs("static/uploads/articles", exist_ok=True)
        with open(path, "wb") as f:
            shutil.copyfileobj(image.file, f)
        image_url = f"/{path}"

    with get_db_context() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO articles (title, content, author_id, image_url)
                VALUES (%s, %s, %s, %s) RETURNING id
            """, (title, content, user["id"], image_url))
            article_id = cur.fetchone()[0]
            conn.commit()

    return RedirectResponse(f"/articles/{article_id}", status_code=303)

# === تعديل مقال ===
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

    image_url = form.get("image")
    image_url = None

    if image and image.filename:
        filename = f"article_{id}_{image.filename}"
        path = f"static/uploads/articles/{filename}"
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "wb") as f:
            shutil.copyfileobj(image.file, f)
        image_url = f"/{path}"

    with get_db_context() as conn:
        with conn.cursor() as cur:
            if image_url:
                cur.execute("""
                    UPDATE articles 
                    SET title = %s, content = %s, image_url = %s 
                    WHERE id = %s
                """, (title, content, image_url, id))
            else:
                cur.execute("""
                    UPDATE articles 
                    SET title = %s, content = %s 
                    WHERE id = %s
                """, (title, content, id))
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

    with get_db_context() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO comments (article_id, user_id, content)
                VALUES (%s, %s, %s)
            """, (id, user["id"], content))
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


