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
# 1. عرض صفحة الإضافة (تأكد من وجود هذا المسار)
@router.get("/add_user")
async def show_add_user_page(request: Request, error: str = None, success: str = None):
    user = request.session.get("user")
    if not user or user.get("role") != "admin":
        return RedirectResponse(url="/403", status_code=303)
    
    csrf_token = generate_csrf_token()
    request.session["csrf_token"] = csrf_token
    
    response = templates.TemplateResponse("admin/add_user.html", 
        {
            "request": request, 
            "csrf_token": request.session["csrf_token"],
            "error": error,
            "success": success,
            "user": user
        }
    )
    set_cache_headers(response)
    return response
 
# 2. معالجة البيانات (POST)
@router.post("/add_user")
async def process_add_user(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    role: str = Form(...),
    csrf_token: str = Form(...)
):
    # التحقق من الـ CSRF
    verify_csrf_token(request, csrf_token)

    # منع إضافة أدمن من الواجهة
    if role == "admin":
         return RedirectResponse("/admin/add_user?error=Forbidden+Role", status_code=303)

    success, message = AuthService.add_new_user(username, password, role)
    
    if success:
        # التوجيه للوحة الإدارة مع رسالة نجاح
        request.session["success_message"] = message
        return RedirectResponse("/admin", status_code=303)
    else:
        # البقاء في نفس الصفحة لإظهار الخطأ
        return RedirectResponse(f"/admin/add_user?error={message}", status_code=303)


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
# 1. عرض صفحة تغيير كلمة المرور
@router.get("/change_password")
async def show_change_password_page(request: Request):
    user = request.session.get("user")
    if not user or user.get("role") != "admin":
        return RedirectResponse(url="/403", status_code=303)
    
    # جلب البيانات عبر السيرفس
    dashboard_data = AuthService.get_admin_dashboard_data(page=1, users_per_page=1000)
    
    # تصفية حساب الأدمن الرئيسي للحماية
    users = dashboard_data['users']
    if user["username"] != "admin":
        users = [u for u in users if u['username'] != "admin"]
    
    return templates.TemplateResponse("admin/change_password.html", {
        "request": request,
        "users": users,
        "csrf_token": request.session.get("csrf_token"),
        "user": user
    })

# 2. معالجة التغيير
@router.post("/change_password")
async def process_change_password(
    request: Request, 
    user_id: int = Form(...), 
    new_password: str = Form(...),
    csrf_token: str = Form(...)
):
    verify_csrf_token(request, csrf_token)
    
    # تنفيذ التغيير عبر السيرفس
    success, message = AuthService.change_password(user_id, new_password)
    
    if success:
        request.session["success_message"] = f"تم تحديث كلمة المرور بنجاح للمستخدم."
        return RedirectResponse("/admin", status_code=303)
    else:
        # في حال الفشل نعود لصفحة التغيير مع رسالة الخطأ
        return RedirectResponse(f"/admin/change_password?error={message}", status_code=303)



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

# 1. مسار سجلات الدخول
@router.get("/login-logs")
async def view_login_logs(request: Request):
    user = request.session.get("user")
    if not user or user.get("role") != "admin":
        return RedirectResponse("/403")
    
    # جلب آخر 50 سجل من قاعدة البيانات
    logss = get_logged_in_users_history(limit=50) 
    
    return templates.TemplateResponse("admin/login_logs.html", {
        "request": request, 
        "login_history": logss,  # تأكد أن الاسم هنا يطابق ما تستخدمه في HTML
        "user": user
    })