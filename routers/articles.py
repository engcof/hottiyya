from fastapi import APIRouter, Request, Form, UploadFile, File, Depends, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from psycopg2.extras import RealDictCursor
from fastapi.templating import Jinja2Templates
from security.session import get_current_user
from postgresql import get_db_context

router = APIRouter(prefix="/articles", tags=["articles"])
templates = Jinja2Templates(directory="templates")

@router.get("/", response_class=HTMLResponse)
async def list_articles(request: Request):
    user = request.session.get("user")
    with get_db_context() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("SELECT a.*, u.username FROM articles a JOIN users u ON a.author_id = u.id ORDER BY created_at DESC")
            articles = cur.fetchall()
    return templates.TemplateResponse("articles/list.html", {
        "request": request, 
        "articles": articles,
        "user": user,
        })
