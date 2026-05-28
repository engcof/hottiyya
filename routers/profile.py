import math

from fastapi import APIRouter, Request, HTTPException, Form, Query 
from fastapi.responses import HTMLResponse, RedirectResponse
from core.templates import templates
from security.session import SessionService
from services.profile_service import ProfileService
from services.auth_service import AuthService
from services.analytics_service import AnalyticsService
import html

router = APIRouter(prefix="/profile", tags=["Profile"])


@router.get("", response_class=HTMLResponse)
async def profile_page(request: Request, page: int = Query(1, ge=1)):
    # 1. تحديد قائمة الصلاحيات الحيوية التي نريد فحصها لبناء لوحة الأزرار السريعة
    required_quick_actions = [
        "view_login_logs",        # 💡 تم تصحيح الاسم هنا ليتطابق مع السجلات بدقة وبدون s زائدة
        "view_system_logs",  
        "view_tree",       
        "change_user_password", 
        "edit_users", 
        "grant_permissions", 
        "delete_users"
    ]
    
    # 2. جلب السياق الشامل مع فحص الصلاحيات المحددة أعلاه تلقائياً
    cxt = SessionService.get_page_context(
        request=request, 
        additional_perms=required_quick_actions
    )
    
    user = cxt["user"]
    if not user:
        return RedirectResponse(url="/auth/login/?error=unauthorized", status_code=303)

    PAGE_SIZE = 10
    initial_offset = (page - 1) * PAGE_SIZE
    inbox_data = ProfileService.get_inbox_data(user["id"], PAGE_SIZE, initial_offset)

    total_messages = inbox_data["total_count"]
    total_pages = math.ceil(total_messages / PAGE_SIZE) if total_messages > 0 else 1
    current_page = min(page, total_pages)

    all_users = []
    # 🔒 إذا كان الحساب يمتلك دور admin (الأساسي أو الاحتياطي) يتم جلب قائمة المستخدمين للمراسلة
    if user.get("role") == "admin":
        all_users = ProfileService.get_all_users_for_admin()

    # جلب السجل الأمني الشخصي للمستخدم العادي فقط
    security_logs = []
    if user.get("role") != "admin":
        security_logs = AnalyticsService.get_user_security_log(user["id"], limit=5)

    error_message = request.session.pop("profile_error", None)
    success_message = request.session.pop("profile_success", None)

    # 3. دمج وتحديث السياق الموجه للـ HTML
    context = {**cxt}
    context.update({
        "notifications": inbox_data["unread_count"],
        "inbox_messages": inbox_data["messages"],
        "all_users": all_users,
        "current_page": current_page,
        "total_pages": total_pages,
        "error": error_message,
        "success_msg": success_message,
        "security_logs": security_logs
    })
    response = templates.TemplateResponse("profile/profile.html", context)
    SessionService.set_cache_headers(response)
    return response


@router.post("/change-password")
async def change_password(request: Request):
    cxt = SessionService.get_page_context(request)
    user = cxt["user"]
    if not user:
        return RedirectResponse(url="/auth/login/?error=unauthorized", status_code=303)

    # 🔒 لمنع التداخل الإداري: حسابات الأدمنية يغيرون كلماتهم من السيرفر أو لوحاتهم الخاصة وليس من البروفايل العام
    if user.get("role") == "admin":
        request.session["profile_error"] = "خطأ: غير مسموح للمسؤول بتغيير كلمة المرور من هذه الصفحة."
        return RedirectResponse("/profile", status_code=303)

    form = await request.form()
    try:
        SessionService.verify_csrf_token(request, form.get("csrf_token"))
    except HTTPException:
        request.session["profile_error"] = "خطأ أمني: رمز الجلسة غير صالح."
        return RedirectResponse("/profile", status_code=303)

    current_pwd = form.get("current_password")
    new_pwd = form.get("new_password")
    confirm_pwd = form.get("confirm_password")

    if not new_pwd or new_pwd != confirm_pwd:
        request.session["profile_error"] = "خطأ: كلمة المرور الجديدة وتأكيدها غير متطابقين."
        return RedirectResponse("/profile", status_code=303)

    success, message = AuthService.change_password(
        user_id=user["id"],
        new_password=new_pwd,
        current_password=current_pwd, 
        request=request
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
    cxt = SessionService.get_page_context(request)
    user = cxt["user"]
    if not user:
        return RedirectResponse(url="/auth/login/?error=unauthorized", status_code=303)

    try:
        SessionService.verify_csrf_token(request, csrf_token)
    except HTTPException:
        request.session["profile_error"] = "خطأ أمني: رمز الجلسة منتهٍ."
        return RedirectResponse("/profile", status_code=303)

    # 🔒 [الحماية الفولاذية باستخدام اسم المستخدم الحصري engcof]
    if user.get("role") != "admin":
        # المستخدم العادي يُجبر سراً على إرسال رسالته لحساب engcof تحديداً
        try:
            admin_user = AuthService.get_user_by_username("engcof")
            if admin_user:
                target_recipient = admin_user["id"]
            else:
                # خطة بديلة احتياطية (Fallback) في حال عدم العثور على الحساب لأي سبب
                target_recipient = recipient_id 
        except Exception:
            target_recipient = recipient_id
    else:
        # إذا كان المرسل أدمن (مثل engcof نفسه)، فيمكنه مراسلة أي ID مستخدم آخر برغبته
        target_recipient = recipient_id

    # تنظيف وتطهير نص الرسالة
    clean_message = html.escape(message.strip())
    if not clean_message:
        request.session["profile_error"] = "خطأ: لا يمكن إرسال رسالة فارغة."
        return RedirectResponse("/profile", status_code=303)

    success = ProfileService.send_message(user["id"], target_recipient, clean_message)
    
    if success:
        msg = "تم إرسال الرسالة بنجاح للمستخدم." if user.get("role") == "admin" else "تم إرسال رسالتك للإدارة بنجاح."
        request.session["profile_success"] = msg
    else:
        request.session["profile_error"] = "فشل في إرسال الرسالة، يرجى التحقق من صحة الحساب."
        
    return RedirectResponse("/profile", status_code=303)


@router.post("/mark-read/{notification_id}")
async def mark_read(request: Request, notification_id: int, csrf_token: str = Form(...)):
    # 🔒 تم إلزام فحص الـ CSRF هنا لحماية المسار من هجمات تزوير الطلبات عبر المواقع
    try:
        SessionService.verify_csrf_token(request, csrf_token)
    except HTTPException:
        return RedirectResponse("/profile", status_code=303)

    cxt = SessionService.get_page_context(request)
    user = cxt["user"]
    if user:
        # الدالة بالداخل يجب أن تحتوي على شرط: WHERE id = notification_id AND recipient_id = user_id لصد هجمات IDOR
        ProfileService.mark_as_read(notification_id, user["id"])
    return RedirectResponse("/profile", status_code=303)


@router.post("/delete-message/{notification_id}")
async def delete_msg(request: Request, notification_id: int, csrf_token: str = Form(...)):
    cxt = SessionService.get_page_context(request)
    user = cxt["user"]
    if not user:
        return RedirectResponse(url="/auth/login/?error=unauthorized", status_code=303)

    try:
        SessionService.verify_csrf_token(request, csrf_token)
        # 🔒 التحقق المزدوج: نمرر الـ user_id للسيرفر لمنع تلاعب مستخدم بحذف رسالة مستخدم آخر
        if ProfileService.delete_message(notification_id, user["id"]):
            request.session["profile_success"] = "تم حذف الرسالة بنجاح."
        else:
            request.session["profile_error"] = "فشل في عملية الحذف (غير مصرح لك أو الرسالة غير موجودة)."
    except HTTPException:
        request.session["profile_error"] = "خطأ أمني: كود التحقق منتهٍ."
        
    return RedirectResponse("/profile", status_code=303)