from fastapi import APIRouter, Request, Depends, HTTPException, Form
from postgresql import get_db_context
from services.auth_service import get_current_user
from security.csrf import generate_csrf_token, verify_csrf_token
from fastapi.responses import HTMLResponse, RedirectResponse
from security.session import set_cache_headers
from psycopg2.extras import RealDictCursor
from core.templates import templates


router = APIRouter(prefix="/permissions", tags=["permissions"])

@router.get("/", response_class=HTMLResponse)
async def permissions_page(request: Request, page: int = 1):
    usr = request.session.get("user")
    user = get_current_user(request)
    if not user or user.get("role") != "admin":
        return RedirectResponse("/auth/login", status_code=303)

    csrf_token = generate_csrf_token()
    request.session["csrf_token"] = csrf_token
        
    with get_db_context() as conn:
        with conn.cursor() as cursor:
            # جلب الصلاحيات مع الترقيم
            perms_per_page = 10
            offset = (page - 1) * perms_per_page
            cursor.execute("""
                SELECT id, name, category 
                FROM permissions 
                ORDER BY name 
                LIMIT %s OFFSET %s
            """, (perms_per_page, offset))
            perms = cursor.fetchall()

          
            
            cursor.execute("SELECT id, username, role FROM users")
            users = cursor.fetchall()
            cursor.execute("""
                    SELECT up.*, u.username, p.name 
                    FROM user_permissions up
                    JOIN users u ON up.user_id = u.id
                    JOIN permissions p ON up.permission_id = p.id
                """)
            assignments = cursor.fetchall()    
            cursor.execute("SELECT COUNT(*) FROM permissions")
            total_perms = cursor.fetchone()[0]
            total_pages = (total_perms + perms_per_page - 1) // perms_per_page

    with get_db_context() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cursor:   
            # جلب كل الصلاحيات (للقائمة المنسدلة في التعديل)
            cursor.execute("SELECT id, name, category FROM permissions ORDER BY name")
            all_permissions = cursor.fetchall()

    response = templates.TemplateResponse("/permissions/permissions.html", {
        "request": request,
        "csrf_token": csrf_token,
        "users": users,
        "user": usr,
        "perms": perms,
        "all_permissions": all_permissions,
        "assignments": assignments,
        "current_page": page,
        "total_pages": total_pages
    })
    set_cache_headers(response)
    return response

@router.post("/add_permission")
async def add_user(
    request: Request,
    name: str = Form(...),
    category: str = Form(...),
    csrf_token: str = Form(...)
):
    verify_csrf_token(request, csrf_token)
    try:
        with get_db_context() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT id FROM permissions WHERE name = %s", (name,))
                if cur.fetchone():
                    raise HTTPException(400, "الصلاحية موجودة بالفعل")
                cur.execute(
                    "INSERT INTO permissions (name, category) VALUES (%s, %s)",
                    (name, category)
                )
                conn.commit()
        return RedirectResponse("/permissions", status_code=303)
    except Exception as e:
        return templates.TemplateResponse("permissions/add_permission.html", {
            "request": request,
            "user": get_current_user(request),
            "csrf_token": request.session.get("csrf_token"),
            "error": str(e)
        })
    

# تعديل مستخدم
@router.post("/edit_permission")
async def edit_user(
    request: Request, 
    perm_id: int = Form(...), 
    name: str = Form(...), 
    category: str = Form(...), 
    csrf_token: str = Form(...)
):
    verify_csrf_token(request, csrf_token)
    
    try:
        with get_db_context() as conn:
            with conn.cursor() as cur:
                # التحقق من وجود المستخدم
                cur.execute("SELECT id FROM permissions WHERE id = %s", (perm_id,))
                if not cur.fetchone():
                    raise HTTPException(status_code=404, detail="المستخدم غير موجود")

                cur.execute("UPDATE permissions SET name = %s, category = %s WHERE id = %s", 
                            (name, category, perm_id))
                conn.commit()

                # إعادة توجيه إلى صفحة الإدارة بعد التحديث
                return RedirectResponse(url="/permissions", status_code=303)  
    except Exception as e:
        return templates.TemplateResponse("/permissions/edit_permission", {
            "request": request,
            "user": get_current_user(request),
            "csrf_token": request.session.get("csrf_token"),
            "error": str(e)
        })
    

# إزالة صلاحية من مستخدم
@router.post("/delete_permission")
async def delete_permission(
    request: Request, 
    perm_id: int = Form(...), 
    csrf_token: str = Form(...)
):
    verify_csrf_token(request, csrf_token)

    try:
        with get_db_context() as conn:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM permissions WHERE id = %s", (perm_id,))
                conn.commit()
                # إعادة توجيه إلى صفحة الإدارة بعد التحديث
                return RedirectResponse(url="/permissions", status_code=303)  
    except Exception as e:
        return templates.TemplateResponse("/permissions/delete_permission", {
            "request": request,
            "user": get_current_user(request),
            "csrf_token": request.session.get("csrf_token"),
            "error": str(e)
        })
    return RedirectResponse(url="/permissions", status_code=303)
    
