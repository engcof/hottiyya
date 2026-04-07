# routers/profile.py
from fastapi import APIRouter, Request, HTTPException, status, Form, Query 
from fastapi.responses import HTMLResponse, RedirectResponse
from core.templates import templates
# ... (بقية الإستيرادات) ...
from security.rate_limit import rate_limit_attempt, reset_attempts
from security.csrf import generate_csrf_token, verify_csrf_token
from security.hash import check_password, hash_password
from security.session import set_cache_headers
from postgresql import get_db_context
from dotenv import load_dotenv
import re
import os
import math
# استيراد دوال الإشعارات والخدمات
from services.notification import get_unread_notification_count, get_all_users_for_admin, get_total_inbox_messages_count
from services.notification import send_notification, mark_notification_as_read, get_inbox_messages, delete_notification

router = APIRouter(prefix="/profile",tags=["Profile"],)
load_dotenv()
# نطاق رموز أوسع للمطابقة (تم نقله من main.py)
SYMBOL_START_PATTERN = r"^[-\s_\.\@\#\!\$\%\^\&\*\(\)\{\}\[\]\<\>]" 

PRIMARY_ADMIN_ID = os.getenv("PRIMARY_ADMIN_ID")

@router.get("", response_class=HTMLResponse)
async def profile_page(request: Request, page: int = Query(1, ge=1)): # 💡 تم تعديل (page: int = 1) إلى استخدام Query
    user = request.session.get("user")
    if not user:
        return RedirectResponse("/auth/login", status_code=status.HTTP_302_FOUND)
        
    csrf_token = generate_csrf_token()
    request.session["csrf_token"] = csrf_token
    
    # تعريف القيم الافتراضية
    PAGE_SIZE = 10
    inbox_messages = []
    unread_count = 0
    total_pages = 1
    current_page = 1
    admin_id = None
    all_users = []
    
    try:
        # 1. حساب الترقيم
        total_messages_count = get_total_inbox_messages_count(user["id"]) 
        total_pages = math.ceil(total_messages_count / PAGE_SIZE) if total_messages_count > 0 else 1
        current_page = min(page, total_pages) if total_pages > 0 else 1
        offset = (current_page - 1) * PAGE_SIZE
        
        # 2. جلب الرسائل (استدعاء واحد فقط)
        inbox_messages = get_inbox_messages(user_id=user["id"], limit=PAGE_SIZE, offset=offset)

        # 3. جلب عدد التنبيهات للهيدر
        unread_count = get_unread_notification_count(user["id"])

        # 4. جلب المستخدمين للمدير فقط
        if user.get("role") == "admin":
            all_users = get_all_users_for_admin()

    except Exception as e:
        print(f"Error fetching profile data: {e}")

    
   
    # 1. جلب الإشعارات غير المقروءة للمستخدم الحالي
    notifications = get_unread_notification_count(user["id"])

    # 2. جلب قائمة المستخدمين إذا كان المدير يريد الإرسال
    all_users = []
    if user.get("role") == "admin":
        all_users = get_all_users_for_admin()
    
    admin_id = None
    if user.get("role") != "admin":
        # 💡 استخدم القيمة من متغير البيئة
        try:
             admin_id = PRIMARY_ADMIN_ID
        except (TypeError, ValueError):
             admin_id = None

    # جلب الرسائل المؤقتة (Flash Messages)
    error_message = request.session.pop("profile_error", None)
    success_message = request.session.pop("profile_success", None)

    response = templates.TemplateResponse("profile/profile.html", {
       "request": request,
        "user": user,
        "csrf_token": csrf_token,
        "notifications": unread_count, # 💡 يفضل تمرير unread_count هنا
        "inbox_messages": inbox_messages,
        "all_users": all_users,
        "current_page": current_page,    # 💡 تم تمرير القيمة المحسوبة
        "total_pages": total_pages,      # 💡 تم تمرير القيمة المحسوبة
        "error": error_message,
        "success_msg": success_message,
        "admin_id": admin_id
    })
    set_cache_headers(response)
    return response

@router.post("/change-password")
async def change_password(request: Request):
    # ... (ضع كامل منطق دالة change_password هنا) ...
    # (استخدم form = await request.form() بدلاً من form = await request.form() لتبسيط الأمر)
    
    # ... (بقية منطق تغيير كلمة المرور الذي كان في main.py) ...
    user = request.session.get("user")
    if not user:
        return RedirectResponse("/auth/login", status_code=status.HTTP_302_FOUND)
    
    # 🚨 1. تطبيق تقييد المعدل باستخدام معرف المستخدم (User ID)
    user_id_key = str(user["id"])
    try:
        rate_limit_attempt(user_id_key)
    except HTTPException as e:
        new_csrf = generate_csrf_token()
        request.session["csrf_token"] = new_csrf
        return templates.TemplateResponse("profile.html", {
            "request": request,
            "user": user,
            "error": e.detail, 
            "success": False,
            "csrf_token": new_csrf
        })

    form = await request.form()
    current_password = form.get("current_password")
    new_password = form.get("new_password")
    confirm_password = form.get("confirm_password")
    csrf_token = form.get("csrf_token")

    # ... (بقية المنطق بما في ذلك التحقق من CSRF وكلمات السر وتحديث قاعدة البيانات) ...
    
    stored_csrf_token = request.session.get("csrf_token")
    error = None
    success = False

    # 2. التحقق من CSRF
    try:
        verify_csrf_token(request, csrf_token)
    except HTTPException:
        error = "جلسة منتهية، أعد تسجيل الدخول"

    # 3. التحقق من مدخلات كلمة السر الجديدة
    if not error:
        if len(new_password) < 6: 
            error = "كلمة السر الجديدة يجب أن تكون 6 أحرف على الأقل"
        elif re.match(SYMBOL_START_PATTERN, new_password):
            error = "كلمة السر الجديدة لا يجب أن تبدأ برمز أو مسافة"
        elif new_password != confirm_password: 
            error = "كلمتا السر الجديدتان غير متطابقتين"
        # 4. التحقق من كلمة السر الحالية
        else:
            try:
                with get_db_context() as conn:
                    with conn.cursor() as cur:
                        cur.execute("SELECT password FROM users WHERE id = %s", (user["id"],))
                        db_pass_row = cur.fetchone()
                        
                        if not db_pass_row:
                             error = "حدث خطأ غير متوقع في قاعدة البيانات (المستخدم مفقود)"
                        else:
                            db_pass = db_pass_row[0]
                            if not check_password(current_password, db_pass):
                                error = "كلمة السر الحالية غير صحيحة"
                            else:
                                hashed = hash_password(new_password)
                                cur.execute("UPDATE users SET password = %s WHERE id = %s", (hashed, user["id"]))
                                conn.commit()
                                success = True
            except Exception as e:
                print(f"خطأ في تحديث كلمة السر: {e}") 
                error = "حدث خطأ غير متوقع أثناء تحديث كلمة السر."

    # 5. إدارة عداد تقييد المعدل
    if success:
        reset_attempts(user_id_key)
        
    # تجديد الـ CSRF
    new_csrf = generate_csrf_token()
    request.session["csrf_token"] = new_csrf
    
    # رسالة النجاح أو الخطأ
    if success:
        request.session["profile_success"] = "تم تغيير كلمة السر بنجاح!"
        return RedirectResponse("/profile", status_code=status.HTTP_303_SEE_OTHER)
    
    # إعادة العرض في حالة الخطأ
    # بما أننا نستخدم RedirectResponse للنجاح، يمكن استخدام TemplateResponse للخطأ
    return templates.TemplateResponse("profile.html", {
        "request": request,
        "user": user,
        "error": error,
        "success": success,
        "csrf_token": new_csrf
    })

# إضافة مسارات الإشعارات والإرسال التي أنشأناها مسبقاً
@router.post("/send-message")
async def send_message_from_admin(
    request: Request, 
    recipient_id: int = Form(...), 
    message: str = Form(...), csrf_token: str = Form(...)):
    user = request.session.get("user")
    
    # 1. التحقق من الصلاحيات (التعديل هنا)
    if not user:
        # إذا لم يكن المستخدم مسجلاً دخوله على الإطلاق، يتم رفض طلبه
        raise HTTPException(status_code=403, detail="يجب عليك تسجيل الدخول للإرسال")
        
    # 🛑 تم حذف الشرط: (user.get("role") != "admin") 
    
    # 2. التحقق من CSRF
    try:
        verify_csrf_token(request, csrf_token)
    except HTTPException:
        request.session["profile_error"] = "جلسة منتهية. أعد إرسال النموذج."
        return RedirectResponse("/profile", status_code=status.HTTP_303_SEE_OTHER)
    
    # 3. إرسال الإشعار (سيستخدم sender_id: user["id"] و recipient_id المحدد)
    try:
        send_notification(recipient_id=recipient_id, message=message, sender_id=user["id"])
        # تعديل رسائل النجاح لتكون عامة بناءً على الدور
        if user.get("role") == "admin":
             request.session["profile_success"] = f"تم إرسال الرسالة إلى المستخدم ID: {recipient_id} بنجاح."
        else:
             request.session["profile_success"] = "تم إرسال رسالتك إلى الإدارة بنجاح."

    except Exception as e:
        print(f"Error sending message: {e}")
        request.session["profile_error"] = "فشل الإرسال: خطأ في قاعدة البيانات."
        
    return RedirectResponse("/profile", status_code=status.HTTP_303_SEE_OTHER)
    
@router.post("/mark-read/{notification_id}")
async def mark_notification(request: Request, notification_id: int):
    # ... (ضع منطق وضع علامة "مقروء" هنا) ...
    user = request.session.get("user")
    if not user:
        return RedirectResponse("/auth/login", status_code=status.HTTP_303_SEE_OTHER)
        
    try:
        mark_notification_as_read(notification_id, user["id"])
    except Exception as e:
        print(f"Error marking as read: {e}")

    return RedirectResponse("/profile", status_code=status.HTTP_303_SEE_OTHER)


@router.post("/delete-message/{notification_id}")
async def delete_message_route(
    request: Request, 
    notification_id: int,
    # 💡 استقبال توكن CSRF من حقل النموذج المخفي
    csrf_token: str = Form(...) 
):
    user = request.session.get("user")
    if not user:
        return RedirectResponse("/auth/login", status_code=status.HTTP_302_FOUND)
    
    # 💡 الخطوة 1: التحقق من صحة توكن CSRF
    session_csrf_token = request.session.get("csrf_token") 
    
    if not session_csrf_token or session_csrf_token != csrf_token:
        # تسجيل خطأ أمني وإعادة توجيه المستخدم
        request.session["profile_error"] = "خطأ أمني: فشل التحقق من رمز CSRF."
        # يُفضل استخدام status.HTTP_302_FOUND بدلاً من 302
        return RedirectResponse("/profile", status_code=status.HTTP_302_FOUND) 
        # ملاحظة: يمكنك بدلاً من ذلك رفع استثناء HTTPException(403) إذا كنت تفضل

    # 💡 الخطوة 2: تنفيذ عملية الحذف بعد التأكد من الأمان
    try:
        delete_notification(notification_id=notification_id, user_id=user["id"])
        request.session["profile_success"] = "تم حذف الرسالة بنجاح."
    except Exception as e:
        # تسجيل الخطأ
        print(f"Delete Error: {e}")
        request.session["profile_error"] = "حدث خطأ أثناء حذف الرسالة."
        
    return RedirectResponse("/profile", status_code=status.HTTP_302_FOUND)