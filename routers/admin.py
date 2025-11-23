# routers/admin.py
from fastapi import APIRouter, Request, Depends, HTTPException, Form
from fastapi.templating import Jinja2Templates
from postgresql import get_db_context
from services.auth_service import get_current_user
from security.csrf import generate_csrf_token, verify_csrf_token
from fastapi.responses import HTMLResponse, RedirectResponse
from security.session import set_cache_headers
from psycopg2.extras import RealDictCursor
from security.hash import hash_password
from postgresql import get_db_context
from core.templates import templates

# routers/admin.py

router = APIRouter(prefix="/admin", tags=["admin"])

@router.get("/", response_class=HTMLResponse)
async def admin_page(request: Request, page: int = 1):
    usr = request.session.get("user")
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
        "user": usr,
        "permissions": permissions,
        "user_permissions": user_permissions,
        "current_page": page,
        "total_pages": total_pages
    })
    set_cache_headers(response)
    return response

@router.get("/permissions")
async def permissions_page(request: Request):
    user = get_current_user(request)
    if not user or user.get("role") != "admin":
        return RedirectResponse("/auth/login")

    with get_db_context() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("SELECT * FROM permissions")
            perms = cur.fetchall()
            cur.execute("""
                SELECT up.*, u.username, p.name 
                FROM user_permissions up
                JOIN users u ON up.user_id = u.id
                JOIN permissions p ON up.permission_id = p.id
            """)
            assignments = cur.fetchall()

    return templates.TemplateResponse("admin/permissions.html", {
        "request": request, 
        "user": user, 
        "perms": perms, 
        "assignments": assignments
    })

@router.get("/add_user", response_class=HTMLResponse)
async def add_user_form(request: Request):
    user = get_current_user(request)
    if not user or user.get("role") != "admin":
        return RedirectResponse("/auth/login", status_code=303)

    csrf_token = generate_csrf_token()
    request.session["csrf_token"] = csrf_token

    return templates.TemplateResponse("admin/add_user.html", {
        "request": request,
        "user": user,
        "csrf_token": csrf_token
    })

@router.post("/add_user")
async def add_user(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    role: str = Form(...),
    csrf_token: str = Form(...)
):
    verify_csrf_token(request, csrf_token)
    if role == "admin":
        raise HTTPException(
            status_code=403,
            detail="غير مسموح بإضافة مستخدم بدور إدمن. هذا الدور محجوز للإدارة العليا فقط."
        )
    try:
        with get_db_context() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT id FROM users WHERE username = %s", (username,))
                if cur.fetchone():
                    raise HTTPException(400, "المستخدم موجود بالفعل")
                cur.execute(
                    "INSERT INTO users (username, password, role) VALUES (%s, %s, %s)",
                    (username, hash_password(password), role)
                )
                conn.commit()
        return RedirectResponse("/admin", status_code=303)
    except Exception as e:
        return templates.TemplateResponse("admin/add_user.html", {
            "request": request,
            "user": get_current_user(request),
            "csrf_token": request.session.get("csrf_token"),
            "error": str(e)
        })
    

  # دالة لتغيير كلمة مرور مستخدم

# تعديل مستخدم
@router.post("/edit_user")
async def edit_user(
    request: Request, 
    user_id: int = Form(...), 
    username: str = Form(...), 
    role: str = Form(...), 
    csrf_token: str = Form(...)
):
    verify_csrf_token(request, csrf_token)
    if role == "admin":
        raise HTTPException(
            status_code=403,
            detail="غير مسموح بإضافة مستخدم بدور إدمن. هذا الدور محجوز للإدارة العليا فقط."
        )

    try:
        with get_db_context() as conn:
            with conn.cursor() as cur:
                # التحقق من وجود المستخدم
                cur.execute("SELECT id FROM users WHERE id = %s", (user_id,))
                if not cur.fetchone():
                    raise HTTPException(status_code=404, detail="المستخدم غير موجود")

                cur.execute("UPDATE users SET username = %s, role = %s WHERE id = %s", 
                            (username, role, user_id))
                conn.commit()

                # إعادة توجيه إلى صفحة الإدارة بعد التحديث
                return RedirectResponse(url="/admin", status_code=303)  
    except Exception as e:
        return templates.TemplateResponse("/admin/edit_user", {
            "request": request,
            "user": get_current_user(request),
            "csrf_token": request.session.get("csrf_token"),
            "error": str(e)
        })

    

    return RedirectResponse(url="/admin", status_code=303)

# حذف مستخدم
@router.post("/delete_user")
async def delete_user(
    request: Request, 
    user_id: int = Form(...), 
    csrf_token: str = Form(...)
):
    verify_csrf_token(request, csrf_token)

    try:
        with get_db_context() as conn:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM users WHERE id = %s", (user_id,))
                conn.commit()
                # إعادة توجيه إلى صفحة الإدارة بعد التحديث
                return RedirectResponse(url="/admin", status_code=303)  
    except Exception as e:
        return templates.TemplateResponse("/admin/delete_user", {
            "request": request,
            "user": get_current_user(request),
            "csrf_token": request.session.get("csrf_token"),
            "error": str(e)
        })
    
    
    
   

    return RedirectResponse(url="/admin", status_code=303)

@router.post("/change_password")
async def change_password(
    request: Request, 
    user_id: int = Form(...), 
    new_password: str = Form(...), 
    csrf_token: str = Form(...)
):
    # التحقق من رمز CSRF
    verify_csrf_token(request, csrf_token)
    
    # التحقق من صلاحيات المستخدم
    user = get_current_user(request)
    if not user or user == "engcof":
        raise HTTPException(status_code=403, detail="أنت بحاجة إلى صلاحيات إدارية للوصول إلى هذه الصفحة")
    # تشفير كلمة المرور الجديدة
    hashed_password = hash_password(new_password)

    # تحديث كلمة المرور في قاعدة البيانات
    try:
        with get_db_context() as conn:
            with conn.cursor() as cur:
                # التحقق من وجود المستخدم
                cur.execute("SELECT id FROM users WHERE id = %s", (user_id,))
                if not cur.fetchone():
                    raise HTTPException(status_code=404, detail="المستخدم غير موجود")

                # تحديث كلمة المرور
                cur.execute("UPDATE users SET password = %s WHERE id = %s", (hashed_password, user_id))
                conn.commit()

                # إعادة توجيه إلى صفحة الإدارة بعد التحديث
                return RedirectResponse(url="/admin", status_code=303)  
    except Exception as e:
        return templates.TemplateResponse("/admin/change_password", {
            "request": request,
            "user": get_current_user(request),
            "csrf_token": request.session.get("csrf_token"),
            "error": str(e)
        })
    
# منح صلاحية لمستخدم
@router.post("/give_permission")
async def give_permission(
    request: Request, 
    user_id: int = Form(...), 
    permission_id: int = Form(...), 
    csrf_token: str = Form(...)
):
    verify_csrf_token(request, csrf_token)

    try:
        with get_db_context() as conn:
            with conn.cursor() as cur:
                cur.execute("INSERT INTO user_permissions (user_id, permission_id) VALUES (%s, %s)", 
                            (user_id, permission_id))
                conn.commit()

                # إعادة توجيه إلى صفحة الإدارة بعد التحديث
                return RedirectResponse(url="/admin", status_code=303)  
    except Exception as e:
        return templates.TemplateResponse("/admin/give_permission", {
            "request": request,
            "user": get_current_user(request),
            "csrf_token": request.session.get("csrf_token"),
            "error": str(e)
        })
    
# إزالة صلاحية من مستخدم
@router.post("/remove_permission")
async def remove_permission(
    request: Request, 
    user_id: int = Form(...), 
    permission_id: int = Form(...), 
    csrf_token: str = Form(...)
):
    verify_csrf_token(request, csrf_token)

    try:
        with get_db_context() as conn:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM user_permissions WHERE user_id = %s AND permission_id = %s", 
                            (user_id, permission_id))
                conn.commit()

                # إعادة توجيه إلى صفحة الإدارة بعد التحديث
                return RedirectResponse(url="/admin", status_code=303)  
    except Exception as e:
        return templates.TemplateResponse("/admin/remove_permission", {
            "request": request,
            "user": get_current_user(request),
            "csrf_token": request.session.get("csrf_token"),
            "error": str(e)
        })
    
    

    
