from fastapi import APIRouter, Request, Form, HTTPException
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from security.hash import check_password
from security.session import set_cache_headers
from security.csrf import generate_csrf_token, verify_csrf_token
from services.auth_service import get_user


router = APIRouter(prefix="/auth")
templates = Jinja2Templates(directory="templates")  # الجذر

# ------------------------------
# GET /login
# ------------------------------
@router.get("/login")
async def login_page(request: Request):
    csrf_token = generate_csrf_token()
    request.session["csrf_token"] = csrf_token
    response = templates.TemplateResponse(
        "auth/login.html", 
        {"request": request, "csrf_token": csrf_token}
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
    verify_csrf_token(request, csrf_token)
    user_data = get_user("username = %s", (username,))
    if user_data and check_password(password, user_data["password"]):
         # تسجيل الدخول الصحيح
        request.session["user"] = {
            "username": user_data["username"],
            "role": user_data["role"],
            "id": user_data["id"]
        }
        
        return RedirectResponse(url="/", status_code=303)
    raise HTTPException(status_code=401, detail="اسم المستخدم أو كلمة المرور غير صحيحة")

# ------------------------------
# GET /logout
# ------------------------------
@router.get("/logout")
async def logout(request: Request):
    request.session.clear()
    response = RedirectResponse(url="/", status_code=303)
    set_cache_headers(response)
    return response


   

