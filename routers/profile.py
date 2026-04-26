from fastapi import APIRouter, Request, HTTPException, status, Form, Query 
from fastapi.responses import HTMLResponse, RedirectResponse
from core.templates import templates, get_global_context
from security.csrf import generate_csrf_token, verify_csrf_token
from security.session import set_cache_headers
from services.profile_service import ProfileService
from dotenv import load_dotenv
import os
import math

router = APIRouter(prefix="/profile", tags=["Profile"])
load_dotenv()

PRIMARY_ADMIN_ID = os.getenv("PRIMARY_ADMIN_ID")

@router.get("", response_class=HTMLResponse)
async def profile_page(request: Request, page: int = Query(1, ge=1)):
    user = request.session.get("user")
    if not user:
        return RedirectResponse("/auth/login", status_code=status.HTTP_302_FOUND)
        
    # توليد توكن CSRF جديد
    csrf_token = generate_csrf_token()
    request.session["csrf_token"] = csrf_token
    
    PAGE_SIZE = 10
    
    # 1. جلب بيانات الصندوق كاملة (رسائل + إحصائيات) في استدعاء واحد
    # نحسب الـ offset هنا ونمرره للسيرفس
    initial_offset = (page - 1) * PAGE_SIZE
    inbox_data = ProfileService.get_inbox_data(user["id"], PAGE_SIZE, initial_offset)

    # 2. حساب الترقيم بناءً على البيانات العائدة
    total_messages = inbox_data["total_count"]
    total_pages = math.ceil(total_messages / PAGE_SIZE) if total_messages > 0 else 1
    current_page = min(page, total_pages)

    # 3. جلب قائمة المستخدمين للمدير فقط عبر السيرفس الموحد
    all_users = []
    if user.get("role") == "admin":
        all_users = ProfileService.get_all_users_for_admin()

    # جلب الرسائل المؤقتة (Flash Messages)
    error_message = request.session.pop("profile_error", None)
    success_message = request.session.pop("profile_success", None)

    
    # 2. تجهيز السياق الموحد (سيحتوي على user و can_view و unread_count)
    context = get_global_context(request)
    
    # 3. تحديث السياق بالبيانات الخاصة بالصفحة الرئيسية
    context.update({
        "csrf_token": csrf_token,
        "notifications": inbox_data["unread_count"],
        "inbox_messages": inbox_data["messages"],
        "all_users": all_users,
        "current_page": current_page,
        "total_pages": total_pages,
        "error": error_message,
        "success_msg": success_message,
        "admin_id": PRIMARY_ADMIN_ID if user.get("role") != "admin" else None
    })
    
    response = templates.TemplateResponse("profile/profile.html",context)
    set_cache_headers(response)
    return response

@router.post("/change-password")
async def change_password(request: Request):
    user = request.session.get("user")
    if not user: return RedirectResponse("/auth/login", status_code=303)

    form = await request.form()
    try:
        verify_csrf_token(request, form.get("csrf_token"))
    except HTTPException:
        request.session["profile_error"] = "خطأ أمني: رمز الجلسة غير صالح."
        return RedirectResponse("/profile", status_code=303)

    success, message = ProfileService.change_user_password(
        user_id=user["id"],
        current_password=form.get("current_password"),
        new_password=form.get("new_password")
    )

    request.session["profile_success" if success else "profile_error"] = message
    return RedirectResponse("/profile", status_code=303)

@router.post("/send-message")
async def send_message_route(
    request: Request, 
    recipient_id: int = Form(...), 
    message: str = Form(...), 
    csrf_token: str = Form(...)
):
    user = request.session.get("user")
    if not user: return RedirectResponse("/auth/login", status_code=303)
        
    try:
        verify_csrf_token(request, csrf_token)
        success = ProfileService.send_message(user["id"], recipient_id, message)
        
        if success:
            msg = "تم إرسال الرسالة بنجاح." if user.get("role") == "admin" else "تم إرسال رسالتك للإدارة."
            request.session["profile_success"] = msg
        else:
            request.session["profile_error"] = "فشل الإرسال."
    except HTTPException:
        request.session["profile_error"] = "جلسة منتهية."
        
    return RedirectResponse("/profile", status_code=303)

@router.post("/mark-read/{notification_id}")
async def mark_read(request: Request, notification_id: int):
    user = request.session.get("user")
    if user:
        ProfileService.mark_as_read(notification_id, user["id"])
    return RedirectResponse("/profile", status_code=303)

@router.post("/delete-message/{notification_id}")
async def delete_msg(request: Request, notification_id: int, csrf_token: str = Form(...)):
    user = request.session.get("user")
    if not user: return RedirectResponse("/auth/login", status_code=303)
    
    try:
        verify_csrf_token(request, csrf_token)
        if ProfileService.delete_message(notification_id, user["id"]):
            request.session["profile_success"] = "تم الحذف."
        else:
            request.session["profile_error"] = "فشل الحذف."
    except HTTPException:
        request.session["profile_error"] = "خطأ أمني."
        
    return RedirectResponse("/profile", status_code=303)