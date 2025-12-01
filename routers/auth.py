
from fastapi import APIRouter, Request, Form, HTTPException
from fastapi.responses import RedirectResponse
from security.hash import check_password
from security.session import set_cache_headers
from security.csrf import generate_csrf_token, verify_csrf_token
from services.auth_service import get_user
from core.templates import templates
import re  # 💡 تم استيراد مكتبة re
from security.rate_limit import rate_limit_attempt, reset_attempts # 💡 استيراد جديد
router = APIRouter(prefix="/auth")

# التعبير النمطي: لا تبدأ بـ: مسافة، أو أحد الرموز [ - _ . @ # ! $ % ^ & * ( ) ]
SYMBOL_START_PATTERN = r"^[-\s_\.\@\#\!\$\%\^\&\*\(\)]"


# ------------------------------
# GET /login
# ------------------------------
@router.get("/login")
async def login_page(request: Request, error: str = None):
    csrf_token = generate_csrf_token()
    request.session["csrf_token"] = csrf_token
    response = templates.TemplateResponse(
        "auth/login.html", 
        {"request": request, 
         "csrf_token": csrf_token,
         "error": error
        }
    )
    set_cache_headers(response)
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
    rate_limit_attempt(request)
    # 1. الأمان أولاً: التحقق من CSRF
    verify_csrf_token(request, csrf_token)
    
    error = None

    # 2. التحقق من المدخلات (Input Validation)
    # ----------------------------------------
    
    ### التحقق من اسم المستخدم (Username Validation) ###
    if len(username) < 3:
        error = "اسم المستخدم قصير جدًا (الحد الأدنى 3 أحرف)"
    elif re.match(SYMBOL_START_PATTERN, username):
        error = "اسم المستخدم لا يمكن أن يبدأ برمز أو مسافة"

    ### التحقق من كلمة المرور (Password Validation) ###
    elif len(password) < 4:
        error = "كلمة المرور قصيرة جدًا (الحد الأدنى 4 أحرف)"
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
    user_data = get_user("username = %s", (username,))
    
    if user_data and check_password(password, user_data["password"]):
        # 💡 إعادة تعيين العداد عند النجاح
        reset_attempts(request)
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
    set_cache_headers(response)
    return response
   

