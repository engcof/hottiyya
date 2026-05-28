
from fastapi import APIRouter, Request, Form, HTTPException
from fastapi.responses import RedirectResponse
from security.hash import check_password
from security.session import SessionService
from services.auth_service import AuthService
from core.templates import templates
import re  
from security.rate_limit import RateLimitService
router = APIRouter(prefix="/auth")

# التعبير النمطي: لا تبدأ بـ: مسافة، أو أحد الرموز [ - _ . @ # ! $ % ^ & * ( ) ]
SYMBOL_START_PATTERN = r"^[-\s_\.\@\#\!\$\%\^\&\*\(\)]"


# ------------------------------
# GET /login
# ------------------------------
@router.get("/login")
async def login_page(request: Request, error: str = None, success: str = None):
    # 2. تجهيز السياق الموحد (سيحتوي على user و can_view و unread_count)
    context = SessionService.get_page_context(request)
    
    # 3. تحديث السياق بالبيانات الخاصة بالصفحة الرئيسية
    context.update({
          "error": error,
           "success": success
    })
    response = templates.TemplateResponse("auth/login.html",context)
    SessionService.set_cache_headers(response)
    return response
  

# ------------------------------
# POST /login
# ------------------------------
@router.post("/login")
async def login(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    csrf_token: str = Form(...),
):
    # 🚨 1. تقييد المعدل (الخطوة الجديدة)
    RateLimitService.rate_limit_attempt(RateLimitService.get_client_ip(request))
    # 1. الأمان أولاً: التحقق من CSRF
    SessionService.verify_csrf_token(request, csrf_token)
    
    error = None

    # 2. التحقق من المدخلات (Input Validation)
    # ----------------------------------------
    
    ### التحقق من اسم المستخدم (Username Validation) ###
    if len(username) < 3:
        error = "اسم المستخدم قصير جدًا (الحد الأدنى 3 أحرف)"
    elif re.match(SYMBOL_START_PATTERN, username):
        error = "اسم المستخدم لا يمكن أن يبدأ برمز أو مسافة"

    ### التحقق من كلمة المرور (Password Validation) ###
    elif len(password) < 6:
        error = "كلمة المرور قصيرة جدًا (الحد الأدنى 6 أحرف)"
    elif re.match(SYMBOL_START_PATTERN, password):
        error = "كلمة المرور لا يمكن أن تبدأ برمز أو مسافة"
        
    # 3. لو وجد خطأ في التحقق الأولي → نرجع نفس الصفحة برسالة الخطأ المناسبة
    if error:
        return await login_page(
            request=request,
            error=error
        )
    # ----------------------------------------
      # 4. محاولة تسجيل الدخول (بعد نجاح التحقق الأولي)
    username_input = username.strip().lower()

    # نطلب من قاعدة البيانات تحويل الحقل المخزن مؤقتاً لحروف صغيرة للمقارنة فقط
    user_data = AuthService.get_user("LOWER(username) = %s", (username_input,))
  
    if user_data and check_password(password, user_data["password"]):
        # 💡 إعادة تعيين العداد عند النجاح
        RateLimitService.reset_attempts(RateLimitService.get_client_ip(request))
        # تسجيل الدخول الصحيح
        request.session["user"] = {
            "username": user_data["username"],
            "role": user_data["role"],
            "id": user_data["id"]
        }
        
        return RedirectResponse(url="/", status_code=303)
        
    # 5. لو فشلت بيانات الاعتماد (اسم مستخدم/كلمة مرور خاطئة)
    return await login_page(
        request=request,
        # رسالة عامة للأمان (لتجنب كشف وجود اسم مستخدم معين)
        error="اسم المستخدم أو كلمة المرور غير صحيحة"
    )

# ------------------------------
# GET /logout
# ------------------------------
@router.get("/logout")
async def logout(request: Request):
    request.session.clear()
    response = RedirectResponse(url="/", status_code=303)
    SessionService.set_cache_headers(response)
    return response
   
# ------------------------------
# GET /register
# ------------------------------
@router.get("/register")
async def register_page(request: Request, error: str = None, success: str = None):
    # 2. تجهيز السياق الموحد (سيحتوي على user و can_view و unread_count)
    context = SessionService.get_page_context(request)
    
    # 3. تحديث السياق بالبيانات الخاصة بالصفحة الرئيسية
    context.update({
        "error": error,
        "success": success
    })
    response = templates.TemplateResponse( "auth/register.html", context)
    SessionService.set_cache_headers(response)
    return response
    
# ------------------------------
# POST /register
# ------------------------------
@router.post("/register")
async def register(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    confirm_password: str = Form(...),
    csrf_token: str = Form(...),
):
    # 1. التحقق من CSRF
    SessionService.verify_csrf_token(request, csrf_token)
    
    # 2. التحقق من تطابق كلمات المرور قبل الذهاب للسيرفس
    if password != confirm_password:
        return await register_page(request, error="كلمات المرور غير متطابقة")

    # 3. استدعاء السيرفس (الذي يحتوي على التحقق من الـ Regex والتكرار)
    # ملاحظة: نرسل دور 'user' تلقائياً للمسجلين الجدد
    success, message = AuthService.add_new_user(username, password, role="user")
    
    if not success:
        return await register_page(request, error=message)
    
    # 4. في حال النجاح، يمكن توجيهه لصفحة اللوجن مع رسالة نجاح
    return await login_page(request, success="تم التسجيل بنجاح! يمكنك الآن تسجيل الدخول.")
