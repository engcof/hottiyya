from fastapi import APIRouter, Request, Form, HTTPException
from fastapi.responses import RedirectResponse
import re
from security.hash import check_password
from security.session import SessionService
from services.auth_service import AuthService
from core.templates import templates
from security.rate_limit import RateLimitService

router = APIRouter(prefix="/auth")

# النمط الصارم لأسماء المستخدمين: حروف وأرقام وشرطة هجائية وسفلية فقط، ويبدأ بحرف أو رقم (من 3 إلى 30 حرفاً)
STRICT_USERNAME_PATTERN = r"^[a-zA-Z0-9][a-zA-Z0-9_-]{2,29}$"

@router.get("/login")
async def login_page(request: Request, error: str = None, success: str = None):
    context = SessionService.get_page_context(request)
    context.update({
        "error": error,
        "success": success
    })
    response = templates.TemplateResponse("auth/login.html", context)
    SessionService.set_cache_headers(response)
    return response

@router.post("/login")
async def login(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    csrf_token: str = Form(...),
):
    # 🚨 1. حد معدل الطلبات لمنع هجمات التخمين والـ Brute Force
    RateLimitService.rate_limit_attempt(RateLimitService.get_client_ip(request))
    
    # 2. التحقق من CSRF
    SessionService.verify_csrf_token(request, csrf_token)
    
    username_input = username.strip()

    # 3. التحقق الأولي من المدخلات
    if not re.match(STRICT_USERNAME_PATTERN, username_input):
        return await login_page(request, error="اسم المستخدم غير صالح أو يحتوي على رموز غير مسموحة.")
        
    if len(password) < 6:
        return await login_page(request, error="كلمة المرور قصيرة جدًا (الحد الأدنى 6 أحرف)")

    # 4. محاولة جلب المستخدم والمصادقة (بالحروف الصغيرة لتجنب الازدواجية)
    user_data = AuthService.get_user("LOWER(username) = %s", (username_input.lower(),))
  
    if user_data and check_password(password, user_data["password"]):
        # إعادة تعيين عداد محاولات التخمين عند النجاح
        RateLimitService.reset_attempts(RateLimitService.get_client_ip(request))
        
        # تسجيل بيانات الجلسة بأمان
        request.session["user"] = {
            "username": user_data["username"],
            "role": user_data["role"],
            "id": user_data["id"]
        }
        return RedirectResponse(url="/", status_code=303)
        
    # رسالة عامة وموحدة لحماية النظام من استكشاف أسماء المستخدمين (User Enumeration)
    return await login_page(request, error="اسم المستخدم أو كلمة المرور غير صحيحة")

@router.get("/logout")
async def logout(request: Request):
    request.session.clear()
    response = RedirectResponse(url="/", status_code=303)
    SessionService.set_cache_headers(response)
    return response

@router.get("/register")
async def register_page(request: Request, error: str = None, success: str = None):
    context = SessionService.get_page_context(request)
    context.update({
        "error": error,
        "success": success
    })
    response = templates.TemplateResponse("auth/register.html", context)
    SessionService.set_cache_headers(response)
    return response
    
@router.post("/register")
async def register(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    confirm_password: str = Form(...),
    csrf_token: str = Form(...),
):
    SessionService.verify_csrf_token(request, csrf_token)
    
    username_input = username.strip()

    # التحقق من نمط الحساب وقواعد كلمة المرور في الواجهة الأمامية قبل السيرفس
    if not re.match(STRICT_USERNAME_PATTERN, username_input):
        return await register_page(request, error="اسم المستخدم غير صالح. يجب أن يبدأ بحرف أو رقم، ويحتوي على حروف إنجليزية، أرقام، (_) أو (-) فقط وبطول 3-30 حرفاً.")

    if len(password) < 6:
        return await register_page(request, error="كلمة المرور يجب ألا تقل عن 6 أحرف.")

    if password != confirm_password:
        return await register_page(request, error="كلمات المرور غير متطابقة")

    # استدعاء السيرفس الآمن لإنشاء الحساب
    success, message = AuthService.add_new_user(username_input, password, role="user")
    
    if not success:
        return await register_page(request, error=message)
    
    return await login_page(request, success="تم التسجيل بنجاح! يمكنك الآن تسجيل الدخول.")