from fastapi import APIRouter, Request, Depends, HTTPException, Form
from postgresql import get_db_context
from security.csrf import generate_csrf_token, verify_csrf_token
from fastapi.responses import HTMLResponse, RedirectResponse
from security.session import set_cache_headers,get_current_user
from psycopg2.extras import RealDictCursor
from security.hash import hash_password
# استيراد الخدمات والراوترات
from core.templates import templates
from services.analytics import get_logged_in_users_history ,get_activity_logs_paginated
from services.notification import send_notification
from services.auth_service import AuthService
import html
import re

# === ثوابت التحقق ===
VALID_USERNAME_REGEX = r"^[a-zA-Z0-9_\-\u0600-\u06FF]{2,30}$" 
PASSWORD_MIN_LENGTH = 4

router = APIRouter(prefix="/admin", tags=["admin"])

@router.get("/", response_class=HTMLResponse)
async def admin_page(request: Request, page: int = 1):
    user = get_current_user(request)
    if not user or user.get("role") != "admin":
        return RedirectResponse("/auth/login", status_code=303)
    # توليد التوكن وتخزينه في الجلسة
    csrf_token = generate_csrf_token()
    request.session["csrf_token"] = csrf_token
    # جلب البيانات عبر السيرفس
    dashboard_data = AuthService.get_admin_dashboard_data(page)
    
    # تصفية حساب الأدمن الرئيسي للحماية
    users = dashboard_data['users']
    if user["username"] != "admin":
        users = [u for u in users if u['username'] != "admin"]

    response = templates.TemplateResponse("/admin/admin.html", {
        "request": request,
        "csrf_token": csrf_token,
        "users": users,
        "user": user, 
        "permissions": dashboard_data['permissions'],
        "user_permissions": dashboard_data['user_permissions'],
        "current_page": page,
        "total_pages": dashboard_data['total_pages'],
        "login_history": get_logged_in_users_history(limit=50),
        "error_message": request.session.pop("error_message", None),
        "success_message": request.session.pop("success_message", None)
    })
    set_cache_headers(response)
    return response

@router.get("/permissions")
async def permissions_page(request: Request):
    user = get_current_user(request)
    if not user or user.get("role") != "admin":
        return RedirectResponse("/auth/login")

    perms, assignments = AuthService.get_permissions_page_data()

    return templates.TemplateResponse("admin/permissions.html", {
        "request": request, 
        "user": user, 
        "perms": perms, 
        "assignments": assignments
    })


# تم حذف دالة GET /admin/add_user لأن النموذج موجود ضمن admin.html
@router.post("/add_user")
async def add_user(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    role: str = Form(...),
    current_page: int = Form(1),
    csrf_token: str = Form(...)
):
    verify_csrf_token(request, csrf_token)
    
    # منع إضافة إدمن من هذه الواجهة (حماية إضافية)
    if role == "admin":
         request.session["error_message"] = "غير مسموح بإضافة مستخدم بدور إدمن."
         return RedirectResponse(f"/admin?page={current_page}", status_code=303)

    # استدعاء السيرفس الموحد
    success, message = AuthService.add_new_user(username, password, role)
    
    if success:
        request.session["success_message"] = message
    else:
        request.session["error_message"] = message
        
    return RedirectResponse(f"/admin?page={current_page}", status_code=303)

# --- تعديل مستخدم ---
@router.post("/edit_user")
async def edit_user(request: Request, user_id: int = Form(...), username: str = Form(...), 
                    role: str = Form(...), current_page: int = Form(1), csrf_token: str = Form(...)):
    verify_csrf_token(request, csrf_token)
    
    success, message = AuthService.update_user(user_id, username, role)
    key = "success_message" if success else "error_message"
    request.session[key] = message
    
    return RedirectResponse(f"/admin?page={current_page}", status_code=303)

# --- حذف مستخدم ---
@router.post("/delete_user")
async def delete_user(request: Request, user_id: int = Form(...), 
                      current_page: int = Form(1), csrf_token: str = Form(...)):
    verify_csrf_token(request, csrf_token)
    
    success, message = AuthService.delete_user(user_id)
    key = "success_message" if success else "error_message"
    request.session[key] = message
    
    return RedirectResponse(f"/admin?page={current_page}", status_code=303)

# --- تغيير كلمة المرور ---
@router.post("/change_password")
async def change_password(request: Request, user_id: int = Form(...), new_password: str = Form(...), 
                          current_page: int = Form(1), csrf_token: str = Form(...)):
    verify_csrf_token(request, csrf_token)
    
    # التحقق من صلاحيات الأدمن الحالي
    current_admin = get_current_user(request)
    if not current_admin or current_admin.get("role") != "admin":
        request.session["error_message"] = "صلاحيات غير كافية"
        return RedirectResponse(f"/admin?page={current_page}", status_code=303)
    
    success, message = AuthService.change_password(user_id, new_password)
    key = "success_message" if success else "error_message"
    request.session[key] = message
    
    return RedirectResponse(f"/admin?page={current_page}", status_code=303)    


# منح صلاحية لمستخدم
# منح صلاحية لمستخدم
@router.post("/give_permission")
async def give_permission(
    request: Request, 
    user_id: int = Form(...), 
    permission_id: int = Form(...), 
    current_page: int = Form(1),
    csrf_token: str = Form(...)
):
    verify_csrf_token(request, csrf_token)
    
    success, message = AuthService.give_permission(user_id, permission_id)
    key = "success_message" if success else "error_message"
    request.session[key] = message
    
    return RedirectResponse(f"/admin?page={current_page}", status_code=303)

# إزالة صلاحية من مستخدم
@router.post("/remove_permission")
async def remove_permission(
    request: Request, 
    user_id: int = Form(...), 
    permission_id: int = Form(...), 
    current_page: int = Form(1),
    csrf_token: str = Form(...)
):
    verify_csrf_token(request, csrf_token)
    
    success, message = AuthService.remove_permission(user_id, permission_id)
    key = "success_message" if success else "error_message"
    request.session[key] = message
    
    return RedirectResponse(f"/admin?page={current_page}", status_code=303)

@router.get("/logs")
async def view_all_activity_logs(request: Request, page: int = 1):
    user = request.session.get("user")
    # التأكد من رتبة الإدمن (كما في الصورة)
    if not user or user.get("role") != "admin":
         return RedirectResponse(url="/403", status_code=303)
    
   
    logs, total_pages = get_activity_logs_paginated(page=page, per_page=30)
    
    response = templates.TemplateResponse("admin/logs.html", {
        "request": request,
        "logs": logs,
        "current_page": page,
        "total_pages": total_pages,
        "user": user
    })
    set_cache_headers(response)
    return response