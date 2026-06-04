from fastapi import APIRouter, Request, Form, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from core.templates import templates
from security.session import SessionService
from services.analytics_service import AnalyticsService
from services.auth_service import AuthService
import html

router = APIRouter(prefix="/admin", tags=["admin"])


# 1. لوحة التحكم الرئيسية (الأزرار فقط)
@router.get("/", response_class=HTMLResponse)
async def admin_dashboard(request: Request):
    cxt = SessionService.get_page_context(request)
    user = cxt["user"]
    
    # 🔒 حصن أمني: الدخول مسموح فقط لمن يملك دور "admin" مطلقاً
    if not user or user.get("role") != "admin":
        return RedirectResponse("/auth/login?error=unauthorized", status_code=303)

    context = {**cxt}
    context.update({
        "success_message": request.session.pop("success_message", None),
        "error_message": request.session.pop("error_message", None)
    })
    
    response = templates.TemplateResponse("/admin/admin.html", context)
    SessionService.set_cache_headers(response)
    return response


# 2. صفحة إدارة المستخدمين (الجدول المقسم حسب الحوجة والصلاحيات)
@router.get("/users", response_class=HTMLResponse)
async def admin_users_page(request: Request, page: int = 1, search: str = ""):
    from_page = request.query_params.get("from", "admin")
    
    required_table_perms = ["edit_users", "delete_users", "grant_permissions"]
    cxt = SessionService.get_page_context(request, additional_perms=required_table_perms)
    user = cxt["user"]
    
    if not user or (not cxt["is_admin"] and not cxt["perms"].get("grant_permissions") and not cxt["perms"].get("edit_users")):
        return RedirectResponse("/auth/login?error=unauthorized", status_code=303)
    
    dashboard_data = AuthService.get_admin_dashboard_data(page, search_query=search)
    users = dashboard_data['users']
    all_permissions = dashboard_data['permissions']
   
    # 🔒 الفلترة الذكية والعزل البصري في الجدول:
    if user["username"] == "admin":
        users = [u for u in users if u['username'] != "admin"]
    else:
        users = [u for u in users if u['username'] != "admin" and u['role'] != "admin"]
    
    filtered_permissions = []
    if cxt["is_admin"]:
        filtered_permissions = all_permissions
    else:
        current_manager_perms = AuthService.get_user_permissions_list(user["id"])
        forbidden_to_grant = ["view_tree", "add_users", "edit_users", "grant_permissions", "delete_member", "delete_users", "change_user_password"]
        
        for perm in all_permissions:
            if perm['name'] in current_manager_perms and perm['name'] not in forbidden_to_grant:
                filtered_permissions.append(perm)

    filtered_permissions = sorted(filtered_permissions, key=lambda x: x.get('category', 'عام'))
    current_page = min(page, dashboard_data['total_pages'] if dashboard_data['total_pages'] > 0 else 1)

    if from_page == "profile":
        back_url = "/profile"
        back_text = "العودة للصفحة الشخصية"
        back_icon = "fas fa-user"
    else:
        back_url = "/admin"
        back_text = "العودة للوحة الإدارة"
        back_icon = "fas fa-home"
    
    context = {**cxt} 
    context.update({
        "users": users,
        "permissions": filtered_permissions, 
        "permissionss": all_permissions, 
        "user_permissions": dashboard_data['user_permissions'],
        "current_page": current_page,
        "total_pages": dashboard_data['total_pages'],
        "search_query": search, 
        "from_page": from_page,
        "back_url": back_url,   
        "back_text": back_text, 
        "back_icon": back_icon,
        "success_message": request.session.pop("success_message", None),
        "error_message": request.session.pop("error_message", None)
    })
    response = templates.TemplateResponse("/admin/admin_users.html", context)
    SessionService.set_cache_headers(response)
    return response


# --- عمليات الأعضاء الحساسة (محمية بالصلاحيات الحية في السيرفر) ---

@router.post("/edit_user")
async def edit_user(request: Request, user_id: int = Form(...), username: str = Form(...), 
                    role: str = Form(...), current_page: int = Form(1), from_page: str = Form("admin", alias="from"), csrf_token: str = Form(...)):
    SessionService.verify_csrf_token(request, csrf_token)
    
    user = request.session.get("user")
    if not SessionService.can(user, "edit_users"):
        request.session["error_message"] = "خطأ أمني: لا تملك صلاحية تعديل بيانات الأعضاء!"
        return RedirectResponse(f"/admin/users?page={current_page}&from={from_page}", status_code=303)
    
    target_user = AuthService.get_user_by_id(user_id)
    
    try:
        SessionService.verify_manager_is_not_touching_admin(user, target_user, "تعديل بيانات")
    except HTTPException as e:
        request.session["error_message"] = e.detail
        return RedirectResponse(f"/admin/users?page={current_page}&from={from_page}", status_code=303)

    # 🔒 حماية إضافية: منع المشرفين من تغيير أدوار الحسابات إلى أدمن، أو التلاعب بأدوار الأدمنية القائمين
    if user["username"] != "admin":
        if role == "admin" or target_user.get("role") == "admin":
            request.session["error_message"] = "إجراء محظور: الصلاحية الحصرية لتعيين أو تعديل رتب المسؤولين تتبع للإدارة العليا فقط!"
            return RedirectResponse(f"/admin/users?page={current_page}&from={from_page}", status_code=303)

    success, message = AuthService.update_user(user_id, html.escape(username.strip()), role)
    request.session["success_message" if success else "error_message"] = message
    return RedirectResponse(f"/admin/users?page={current_page}&from={from_page}", status_code=303)


@router.post("/delete_user")
async def delete_user(request: Request, user_id: int = Form(...), 
                      current_page: int = Form(1), from_page: str = Form("admin", alias="from"), csrf_token: str = Form(...)):
    SessionService.verify_csrf_token(request, csrf_token)
    
    user = request.session.get("user")
    if not SessionService.can(user, "delete_users"):
        request.session["error_message"] = "خطأ أمني: لا تملك صلاحية حذف الحسابات!"
        return RedirectResponse(f"/admin/users?page={current_page}&from={from_page}", status_code=303)
        
    target_user = AuthService.get_user_by_id(user_id)
    try:
        SessionService.verify_manager_is_not_touching_admin(user, target_user, "حذف حساب مسؤول")
    except HTTPException as e:
        request.session["error_message"] = e.detail
        return RedirectResponse(f"/admin/users?page={current_page}&from={from_page}", status_code=303)
        
    if user and user.get("id") == user_id:
        request.session["error_message"] = "لا يمكنك حذف حسابك الشخصي وأنت متصل!"
        return RedirectResponse(f"/admin/users?page={current_page}&from={from_page}", status_code=303)

    success, message = AuthService.delete_user(user_id)
    request.session["success_message" if success else "error_message"] = message
    return RedirectResponse(f"/admin/users?page={current_page}&from={from_page}", status_code=303)


@router.post("/give_permission")
async def give_permission(request: Request, user_id: int = Form(...), permission_id: int = Form(...), 
                         current_page: int = Form(1), from_page: str = Form("admin", alias="from"), csrf_token: str = Form(...)):
    SessionService.verify_csrf_token(request, csrf_token)
    
    user = request.session.get("user")
    if not SessionService.can(user, "grant_permissions"):
        request.session["error_message"] = "خطأ أمني: غير مصرح لك بمنح صلاحيات للأعضاء."
        return RedirectResponse(f"/admin/users?page={current_page}&from={from_page}", status_code=303)

    target_user = AuthService.get_user_by_id(user_id)
    try:
        SessionService.verify_manager_is_not_touching_admin(user, target_user, "منح صلاحية لمسؤول")
    except HTTPException as e:
        request.session["error_message"] = e.detail
        return RedirectResponse(f"/admin/users?page={current_page}&from={from_page}", status_code=303)

    success, message = AuthService.give_permission(user_id, permission_id)
    request.session["success_message" if success else "error_message"] = message
    return RedirectResponse(f"/admin/users?page={current_page}&from={from_page}", status_code=303)


@router.post("/remove_permission")
async def remove_permission(request: Request, user_id: int = Form(...), permission_id: int = Form(...), 
                           current_page: int = Form(1), from_page: str = Form("admin", alias="from"), csrf_token: str = Form(...)):
    SessionService.verify_csrf_token(request, csrf_token)
    
    user = request.session.get("user")
    if not SessionService.can(user, "grant_permissions"):
        request.session["error_message"] = "خطأ أمني: غير مصرح لك بسحب صلاحيات الأعضاء."
        return RedirectResponse(f"/admin/users?page={current_page}&from={from_page}", status_code=303)
    
    target_user = AuthService.get_user_by_id(user_id)
    try:
        SessionService.verify_manager_is_not_touching_admin(user, target_user, "سحب صلاحية من مسؤول")
    except HTTPException as e:
        request.session["error_message"] = e.detail
        return RedirectResponse(f"/admin/users?page={current_page}&from={from_page}", status_code=303)
    
    success, message = AuthService.remove_permission(user_id, permission_id)
    request.session["success_message" if success else "error_message"] = message
    
    return RedirectResponse(f"/admin/users?page={current_page}&from={from_page}", status_code=303)

# --- صفحات الإضافة وتغيير كلمة المرور للمشرفين المخولين ---

@router.get("/add_user")
async def show_add_user_page(request: Request):
    from_page = request.query_params.get("from", "admin") 
    cxt = SessionService.get_page_context(request, additional_perms=["add_users"])
    user = cxt["user"]
    
    if not user :
        return RedirectResponse("/auth/login?error=unauthorized", status_code=303)
    
    # التحقق من الصلاحية
    added = cxt.get("perms", {}).get("add_users", False)
    if not added:
        return RedirectResponse("/auth/login?error=unauthorized2", status_code=303)

    if from_page == "profile":
        back_url = "/profile"
        back_text = "العودة للصفحة الشخصية"
        back_icon = "fas fa-user"
    else:
        back_url = "/admin"
        back_text = "العودة للوحة الإدارة"
        back_icon = "fas fa-home"

    context = {**cxt}
    context.update({
        "error": request.session.pop("error", None),
        "from_page": from_page,
        "back_url": back_url,   
        "back_text": back_text, 
        "back_icon": back_icon,
        })
    response = templates.TemplateResponse("admin/add_user.html", context)
    SessionService.set_cache_headers(response)
    return response


@router.post("/add_user")
async def process_add_user(request: Request, username: str = Form(...), password: str = Form(...), 
                          role: str = Form(...), from_page: str = Form("admin", alias="from"), csrf_token: str = Form(...)):
    SessionService.verify_csrf_token(request, csrf_token)
    
    user = request.session.get("user")
    if not SessionService.can(user, "add_users"):
        return RedirectResponse("/admin?error=Forbidden", status_code=303)
        
    if role == "admin" and user["username"] != "admin": 
        return RedirectResponse("/admin/add_user?error=Forbidden_Role", status_code=303)
        
    success, message = AuthService.add_new_user(html.escape(username.strip()), password, role)
    if success:
        request.session["success_message"] = message
        return RedirectResponse("/admin/add_user", status_code=303)
    request.session["error"] = message
    return RedirectResponse("/admin/add_user?from=" + from_page, status_code=303)


@router.get("/change_password")
async def show_change_password_page(request: Request):
    from_page = request.query_params.get("from", "admin")
    cxt = SessionService.get_page_context(request, additional_perms=["change_user_password"])
    user = cxt["user"]
    
    if not user or (not cxt["is_admin"] and not cxt["perms"].get("change_user_password")):
        return RedirectResponse("/auth/login?error=unauthorized", status_code=303)
    
    data = AuthService.get_admin_dashboard_data(page=1, users_per_page=1000)
    
    # 🔒 [الفصل البصري الفولاذي في الـ GET]
    if user["username"] == "admin":
        # 1. الأدمن الأساسي (admin) يرى كل الحسابات في النظام بما فيها حسابه وحسابات الأدمنية التنفيذيين
        users = data['users']
    elif user.get("role") == "admin":
        # 2. الأدمن التنفيذي (role == admin ولكن الاسم ليس admin) يرى الجميع ليعمل، ويُحجب عنه حساب الأدمن الأساسي فقط لحمايته
        users = [u for u in data['users'] if u['username'] != "admin"]
    else:
        # 3. المشرف العادي (Manager/User ذو صلاحية) يُحجب عنه حساب الأدمن الأساسي وجميع الحسابات التي تحمل رتبة أدمن
        users = [u for u in data['users'] if u['username'] != "admin" and u['role'] != "admin"]
    
    if from_page == "profile":
        back_url = "/profile"
        back_text = "العودة للصفحة الشخصية"
        back_icon = "fas fa-user"
    else:
        back_url = "/admin"
        back_text = "العودة للوحة الإدارة"
        back_icon = "fas fa-home"
    
    context = {**cxt}
    context.update({
        "users": users, 
        "from_page": from_page,
        "back_url": back_url,   
        "back_text": back_text, 
        "back_icon": back_icon,
        "error": request.session.pop("error", None)
    })
    response = templates.TemplateResponse("admin/change_password.html", context)
    SessionService.set_cache_headers(response)
    return response
   

@router.post("/change_password")
async def process_change_password(
    request: Request, 
    user_id: int = Form(...), 
    new_password: str = Form(...), 
    from_page: str = Form("admin", alias="from"), 
    csrf_token: str = Form(...)
):
    SessionService.verify_csrf_token(request, csrf_token)
    
    user = request.session.get("user")
    if not SessionService.can(user, "change_user_password"):
        return RedirectResponse("/admin?error=Forbidden", status_code=303)
        
    target_user = AuthService.get_user_by_id(user_id)
    
    # 🔒 [الحماية الفولاذية في الـ POST في الخلفية لمنع أي تلاعب]
    if target_user and target_user["username"] == "admin":
        # إذا كان الحساب المستهدف هو الأدمن الأساسي (admin)، نتحقق: هل الذي يحاول التعديل هو الأدمن الأساسي نفسه؟
        if user["username"] != "admin":
            # إذا كان أدمن تنفيذي أو أي دور آخر، يتم حظره وطرده فوراً
            request.session["error"] = "خطأ أمني صارم: لا يحق للأدمن التنفيذي أو المشرفين تغيير كلمة مرور الأدمن الأساسي للموقع."
            return RedirectResponse("/admin/change_password?from=" + from_page, status_code=303)
            
    # الفحص الافتراضي المعتاد لبقية الأدوار لمنع التداخل والتعارض
    try:
        SessionService.verify_manager_is_not_touching_admin(user, target_user, "تعديل كلمة مرور مسؤول")
    except HTTPException as e:
        request.session["error"] = e.detail
        return RedirectResponse("/admin/change_password?from=" + from_page, status_code=303)
   
    # تنفيذ عملية التحديث الفعلي في قاعدة البيانات
    success, message = AuthService.change_password(user_id, new_password, request=request)
    if success:
        request.session["success_message"] = "تم تحديث كلمة المرور بنجاح."
        return RedirectResponse("/admin/change_password?from=" + from_page, status_code=303)
        
    request.session["error"] = message
    return RedirectResponse("/admin/change_password?from=" + from_page, status_code=303)

# --- صفحات السجلات والرقابة المفتوحة ---

@router.get("/logs")
async def view_logs(request: Request, page: int = 1):
    cxt = SessionService.get_page_context(request, additional_perms=["view_system_logs"])
    user = cxt["user"]
    if not user or (not cxt["is_admin"] and not cxt["perms"].get("view_system_logs")):
        return RedirectResponse("/auth/login?error=unauthorized", status_code=303)
        
    logs, total_pages = AnalyticsService.get_activity_logs_paginated(page=page, per_page=30)
    context = {**cxt}
    context.update({"logs": logs, "current_page": page, "total_pages": total_pages})
    response = templates.TemplateResponse("admin/logs.html", context)
    SessionService.set_cache_headers(response)
    return response


@router.get("/login-logs")
async def view_login_logs(request: Request, page: int = 1):
    # 💡 تم التأكد من ضبط اسم الصلاحية "view_login_logs" لتطابق قاعدة البيانات بدقة
    cxt = SessionService.get_page_context(request, additional_perms=["view_logins_logs"])
    user = cxt["user"]
    if not user or (not cxt["is_admin"] and not cxt["perms"].get("view_logins_logs")):
        return RedirectResponse("/auth/login?error=unauthorized", status_code=303)
    
    login_history, total_pages = AnalyticsService.get_login_logs_paginated(page=page, per_page=20) 
    context = {**cxt}
    context.update({"login_history": login_history, "current_page": page, "total_pages": total_pages})
    response = templates.TemplateResponse("admin/login_logs.html", context)
    SessionService.set_cache_headers(response)
    return response