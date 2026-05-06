from fastapi import APIRouter, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from core.templates import templates
from security.csrf import  verify_csrf_token
from security.session import set_cache_headers, get_admin_context,get_page_context
from services.analytics import  get_activity_logs_paginated, get_login_logs_paginated
from services.auth_service import AuthService

router = APIRouter(prefix="/admin", tags=["admin"])


# 1. لوحة التحكم الرئيسية (الأزرار فقط)
@router.get("/", response_class=HTMLResponse)
async def admin_dashboard(request: Request):
    cxt = get_page_context(request)
    user = cxt["user"]
    isad = cxt["is_admin"]      
    if not isad: return RedirectResponse("/auth/login", status_code=303)

    # 2. تجهيز السياق الموحد (سيحتوي على user و can_view و unread_count)
    context =   {**cxt}
    
    # 3. تحديث السياق بالبيانات الخاصة بالصفحة الرئيسية
    context.update({
        "success_message": request.session.pop("success_message", None),
        "error_message": request.session.pop("error_message", None)
    })
    
    response = templates.TemplateResponse("/admin/admin.html", context)
    set_cache_headers(response)
    return response

# 2. صفحة إدارة المستخدمين (الجدول فقط)
@router.get("/users", response_class=HTMLResponse)
async def admin_users_page(request: Request, page: int = 1):
    cxt = get_page_context(request)
    user = cxt["user"]
    isad = cxt["is_admin"]
    if not isad: return RedirectResponse("/auth/login", status_code=303)
    
    dashboard_data = AuthService.get_admin_dashboard_data(page)
    users = dashboard_data['users']
    
    # حماية حساب الأدمن الرئيسي
    if user["username"] != "admin":
        users = [u for u in users if u['username'] != "admin"]

   # 2. تجهيز السياق الموحد (سيحتوي على user و can_view و unread_count)
    context = {**cxt}
    
    # 3. تحديث السياق بالبيانات الخاصة بالصفحة الرئيسية
    context.update({
        "users": users,
        "permissions": dashboard_data['permissions'],
        "user_permissions": dashboard_data['user_permissions'],
        "current_page": page,
        "total_pages": dashboard_data['total_pages'],
        "success_message": request.session.pop("success_message", None),
        "error_message": request.session.pop("error_message", None)
    })
    response = templates.TemplateResponse("/admin/admin_users.html", context)
    set_cache_headers(response)
    return response

# --- عمليات المستخدمين (توجيه دائماً لـ /admin/users) ---

@router.post("/edit_user")
async def edit_user(request: Request, user_id: int = Form(...), username: str = Form(...), 
                    role: str = Form(...), current_page: int = Form(1), csrf_token: str = Form(...)):
    verify_csrf_token(request, csrf_token)
    
    # حماية إضافية: منع تعديل حساب الأدمن الرئيسي من هذه الواجهة
    target_user = AuthService.get_user_by_id(user_id)
    if target_user and target_user['username'] == "admin":
        request.session["error_message"] = "لا يمكن تعديل بيانات الحساب الرئيسي من هنا!"
        return RedirectResponse(f"/admin/users?page={current_page}", status_code=303)

    success, message = AuthService.update_user(user_id, username, role)
    request.session["success_message" if success else "error_message"] = message
    return RedirectResponse(f"/admin/users?page={current_page}", status_code=303)

@router.post("/delete_user")
async def delete_user(request: Request, user_id: int = Form(...), 
                      current_page: int = Form(1), csrf_token: str = Form(...)):
    verify_csrf_token(request, csrf_token)
    
    # جلب بيانات المستخدم المستهدف للتحقق
    target_user = AuthService.get_user_by_id(user_id)
    
    # 1. منع حذف حساب الأدمن الرئيسي (admin)
    if target_user and target_user['username'] == "admin":
        request.session["error_message"] = "خطأ أمني: لا يمكن حذف الحساب الرئيسي للمنظمة!"
        return RedirectResponse(f"/admin/users?page={current_page}", status_code=303)
        
    # 2. منع المستخدم من حذف حسابه الشخصي بنفسه (اختياري ولكن ينصح به)
    current_admin = request.session.get("user")
    if current_admin and current_admin.get("id") == user_id:
        request.session["error_message"] = "لا يمكنك حذف حسابك الشخصي وأنت متصل!"
        return RedirectResponse(f"/admin/users?page={current_page}", status_code=303)

    success, message = AuthService.delete_user(user_id)
    request.session["success_message" if success else "error_message"] = message
    return RedirectResponse(f"/admin/users?page={current_page}", status_code=303)

@router.post("/give_permission")
async def give_permission(request: Request, user_id: int = Form(...), permission_id: int = Form(...), 
                         current_page: int = Form(1), csrf_token: str = Form(...)):
    verify_csrf_token(request, csrf_token)
    success, message = AuthService.give_permission(user_id, permission_id)
    request.session["success_message" if success else "error_message"] = message
    return RedirectResponse(f"/admin/users?page={current_page}", status_code=303)

@router.post("/remove_permission")
async def remove_permission(request: Request, user_id: int = Form(...), permission_id: int = Form(...), 
                           current_page: int = Form(1), csrf_token: str = Form(...)):
    verify_csrf_token(request, csrf_token)
    # 🔒 حماية إضافية لحساب الأدمن الرئيسي
    target_user = AuthService.get_user_by_id(user_id)
    if target_user and target_user['username'] == "admin":
        request.session["error_message"] = "لا يمكن تعديل أو إزالة صلاحيات الحساب الرئيسي."
        return RedirectResponse(f"/admin/users?page={current_page}", status_code=303)
    
    success, message = AuthService.remove_permission(user_id, permission_id)
    request.session["success_message" if success else "error_message"] = message
    return RedirectResponse(f"/admin/users?page={current_page}", status_code=303)

# --- صفحات الإضافة والتغيير (توجيه لـ /admin عند النجاح) ---
@router.get("/add_user")
async def show_add_user_page(request: Request ):
    cxt = get_page_context(request)
    user = cxt["user"]
    isad = cxt["is_admin"]
    if not isad: return RedirectResponse("/403")
    # 2. تجهيز السياق الموحد (سيحتوي على user و can_view و unread_count)
    context = {**cxt}
    
    # 3. تحديث السياق بالبيانات الخاصة بالصفحة الرئيسية
    context.update({
        "error": request.session.pop("error", None)
    })
    response = templates.TemplateResponse( "admin/add_user.html",   context)
    set_cache_headers(response)
    return response
   
@router.post("/add_user")
async def process_add_user(request: Request, username: str = Form(...), password: str = Form(...), 
                          role: str = Form(...), csrf_token: str = Form(...)):
    verify_csrf_token(request, csrf_token)
    if role == "admin": return RedirectResponse("/admin/add_user?error=Forbidden", status_code=303)
    success, message = AuthService.add_new_user(username, password, role)
    if success:
        request.session["success_message"] = message
        return RedirectResponse("/admin", status_code=303)
    request.session["error"] = message
    return RedirectResponse(f"/admin/add_user", status_code=303)

@router.get("/change_password")
async def show_change_password_page(request: Request):
    cxt = get_page_context(request)
    user = cxt["user"]
    isad = cxt["is_admin"]
    if not isad: return RedirectResponse("/403")
    
    
    data = AuthService.get_admin_dashboard_data(page=1, users_per_page=1000)
    users = [u for u in data['users'] if u['username'] != "admin"] if user["username"] != "admin" else data['users']
    
    # 2. تجهيز السياق الموحد (سيحتوي على user و can_view و unread_count)
    context = {**cxt}
    
    # 3. تحديث السياق بالبيانات الخاصة بالصفحة الرئيسية
    context.update({
       "users": users, 
        "error": request.session.pop("error", None)
    })
    response = templates.TemplateResponse( "admin/change_password.html",   context)
    set_cache_headers(response)
    return response
   
@router.post("/change_password")
async def process_change_password(request: Request, user_id: int = Form(...), new_password: str = Form(...), csrf_token: str = Form(...)):
    verify_csrf_token(request, csrf_token)
    success, message = AuthService.change_password(user_id, new_password)
    if success:
        request.session["success_message"] = "تم تحديث كلمة المرور بنجاح."
        return RedirectResponse("/admin", status_code=303)
    request.session["error"] = message
    return RedirectResponse(f"/admin/change_password?", status_code=303)

   

# --- السجلات ---

@router.get("/logs")
async def view_logs(request: Request, page: int = 1):
    cxt = get_page_context(request)
    user = cxt["user"]
    isad = cxt["is_admin"]
    if not isad: return RedirectResponse("/403")
    logs, total_pages = get_activity_logs_paginated(page=page, per_page=30)
  
    # 2. تجهيز السياق الموحد (سيحتوي على user و can_view و unread_count)
    context = {**cxt}
    # 3. تحديث السياق بالبيانات الخاصة بالصفحة الرئيسية
    context.update({
       "logs": logs, "current_page": page, "total_pages": total_pages
    })
    response = templates.TemplateResponse("admin/logs.html",  context)
    set_cache_headers(response)
    return response



@router.get("/login-logs")
async def view_login_logs(request: Request, page: int = 1):
    cxt = get_page_context(request)
    user = cxt["user"]
    isad = cxt["is_admin"]
    if not isad: return RedirectResponse("/403")
    
    # استدعاء الدالة الجديدة التي تدعم الترقيم (Paginated)
    # نمرر رقم الصفحة (page) ونحدد العدد بـ 20 سجل
    login_history, total_pages = get_login_logs_paginated(page=page, per_page=20) 
    
    
    # 2. تجهيز السياق الموحد (سيحتوي على user و can_view و unread_count)
    context = {**cxt}
    
    # 3. تحديث السياق بالبيانات الخاصة بالصفحة الرئيسية
    context.update({
        "login_history": login_history, # السجلات الخاصة بالصفحة الحالية فقط
        "current_page": page,           # رقم الصفحة الحالية للتحكم في أزرار التنقل
        "total_pages": total_pages,    
    })
    response = templates.TemplateResponse("admin/login_logs.html", context)
    set_cache_headers(response)
    return response 