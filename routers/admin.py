# routers/admin.py
from fastapi import APIRouter, Request
from fastapi.templating import Jinja2Templates
from postgresql import get_db_context
from services.auth_service import get_current_user
from security.csrf import generate_csrf_token
from fastapi.responses import HTMLResponse, RedirectResponse
from security.session import set_cache_headers

# routers/admin.py


router = APIRouter(prefix="/admin", tags=["admin"])
templates = Jinja2Templates(directory="templates")

@router.get("/", response_class=HTMLResponse)
async def admin_page(request: Request, page: int = 1):
    user = get_current_user(request)
    if not user or user.get("role") != "admin":
        return RedirectResponse("/auth/login", status_code=303)
    """
    user = بيانات الجلسة بعد التحقق (username, role, csrf)
    """
    csrf_token = generate_csrf_token()
    request.session["csrf_token"] = csrf_token
     
    with get_db_context() as conn:
        with conn.cursor() as cursor:
            users_per_page = 10
            offset = (page - 1) * users_per_page
            cursor.execute("SELECT id, username, role FROM users LIMIT %s OFFSET %s", (users_per_page, offset))
            users = cursor.fetchall()
            if user["username"] != "admin":
                users = [u for u in users if u[1] != "admin"]
            cursor.execute("SELECT id, name, category FROM permissions")
            permissions = cursor.fetchall()
            user_permissions = {}
            for u in users:
                cursor.execute("""
                    SELECT permissions.name
                    FROM permissions
                    JOIN user_permissions ON permissions.id = user_permissions.permission_id
                    WHERE user_permissions.user_id = %s
                """, (u[0],))
                user_permissions[u[0]] = [p[0] for p in cursor.fetchall()]
            cursor.execute("SELECT COUNT(*) FROM users")
            total_users = cursor.fetchone()[0]
            total_pages = (total_users + users_per_page - 1) // users_per_page

    response = templates.TemplateResponse("/admin/admin.html", {
        "request": request,
        "csrf_token": csrf_token,
        "users": users,
        "permissions": permissions,
        "user_permissions": user_permissions,
        "current_page": page,
        "total_pages": total_pages
    })
    set_cache_headers(response)
    return response