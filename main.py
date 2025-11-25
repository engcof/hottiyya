import os
import markupsafe
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.sessions import SessionMiddleware
from core.templates import templates

# استيراد الراوترات
from routers import auth, admin, family, articles, news, permissions

# استيراد الدوال المهمة
from security.session import set_cache_headers
from security.csrf import generate_csrf_token


# =========================================
# Lifespan: تشغيل init_database مرة واحدة عند بدء التطبيق
# =========================================

# =========================================
# # إعداد التطبيق        
# =========================================
app = FastAPI(
    title="عائلة الحوطية الرقمية",
    description="منصة عائلية متكاملة",
    version="1.0.0"
)


# =========================================
# Middleware
# =========================================
app.add_middleware(
    SessionMiddleware,
    secret_key=os.getenv("SECRET_KEY", "super-secret-key-change-in-production"),
    session_cookie="family_session",
    max_age=60 * 60 * 24 * 30,  # 30 يوم
    same_site="lax",
    https_only=True
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://render.com"],  # في الإنتاج غيّرها للدومين الحقيقي
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# =========================================
# Static Files
# =========================================
app.mount("/static", StaticFiles(directory="static"), name="static")


# =========================================
# تضمين الراوترات
# =========================================
app.include_router(auth.router)
app.include_router(admin.router)
app.include_router(family.router)      # /names
app.include_router(articles.router)    # /articles
app.include_router(news.router)
app.include_router(permissions.router)  # إذا كان عندك راوتر للصلاحيات


# =========================================
# الصفحة الرئيسية
# =========================================
@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    user = request.session.get("user")
    response = templates.TemplateResponse("index.html", {
        "request": request,
        "user": user
    })
    set_cache_headers(response)
    return response

@app.get("/about", response_class=HTMLResponse)
async def about_page(request: Request):
    user = request.session.get("user")
    response = templates.TemplateResponse("/about.html", {
        "request": request,
        "user": user
    })
    set_cache_headers(response)
    return response


# =========================================
# صفحة الملف الشخصي + تغيير كلمة السر
# =========================================
@app.get("/profile", response_class=HTMLResponse)
async def profile_page(request: Request):
    user = request.session.get("user")
    if not user:
        return RedirectResponse("/auth/login")

    # توليد CSRF لتغيير كلمة السر
    csrf_token = generate_csrf_token()
    request.session["csrf_token"] = csrf_token

    response = templates.TemplateResponse("profile.html", {
        "request": request,
        "user": user,
        "csrf_token": csrf_token
    })
    set_cache_headers(response)
    return response


@app.post("/profile/change-password")
async def change_password(request: Request):
    from security.hash import check_password, hash_password
    from postgresql import get_db_context

    user = request.session.get("user")
    if not user:
        return RedirectResponse("/auth/login")

    form = await request.form()
    current_password = form.get("current_password")
    new_password = form.get("new_password")
    confirm_password = form.get("confirm_password")
    csrf_token = form.get("csrf_token")

    error = None
    success = False

    if csrf_token != request.session.get("csrf_token"):
        error = "جلسة منتهية، أعد تسجيل الدخول"
    elif new_password != confirm_password:
        error = "كلمتا السر الجديدتان غير متطابقتين"
    elif len(new_password) < 6:
        error = "كلمة السر يجب أن تكون 6 أحرف على الأقل"
    else:
        with get_db_context() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT password FROM users WHERE id = %s", (user["id"],))
                db_pass = cur.fetchone()[0]
                if not check_password(current_password, db_pass):
                    error = "كلمة السر الحالية غير صحيحة"
                else:
                    hashed = hash_password(new_password)
                    cur.execute("UPDATE users SET password = %s WHERE id = %s", (hashed, user["id"]))
                    conn.commit()
                    success = True

    # تحديث CSRF بعد الإرسال
    new_csrf = generate_csrf_token()
    request.session["csrf_token"] = new_csrf

    return templates.TemplateResponse("profile.html", {
        "request": request,
        "user": user,
        "error": error,
        "success": success,
        "csrf_token": new_csrf
    })


# =========================================
# صفحة 404 مخصصة (اختياري)
# =========================================
@app.exception_handler(404)
async def not_found(request: Request, exc):
    return templates.TemplateResponse("404.html", {"request": request}, status_code=404)


# =========================================
# تشغيل التطبيق (للتطوير فقط)
# =========================================
if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)

# uvicorn main:app --reload


