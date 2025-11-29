from datetime import datetime
import os
import uuid
from urllib.parse import urlparse
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.sessions import SessionMiddleware
from core.templates import templates
from postgresql import init_database
from psycopg2.extras import RealDictCursor
from services.analytics import log_visit, get_total_visitors, get_today_visitors, get_online_count, get_online_users

# استيراد الراوترات
from routers import auth, admin, family, articles, news, permissions
from dotenv import load_dotenv
from postgresql import get_db_context
# استيراد الدوال المهمة
from security.session import set_cache_headers
from security.csrf import generate_csrf_token

load_dotenv()
# إضافة هذا الكود بعد load_dotenv()
if os.getenv("DATABASE_URL"):
    # Render يبعت DATABASE_URL → نحوله للمتغيرات اللي postgresql.py بيفهمها
    db = urlparse(os.getenv("DATABASE_URL"))
    os.environ["DB_HOST"] = db.hostname
    os.environ["DB_NAME"] = db.path[1:]
    os.environ["DB_USER"] = db.username
    os.environ["DB_PASSWORD"] = db.password
    os.environ["DB_PORT"] = str(db.port or 5432)

# =========================================
# Lifespan: تشغيل init_database مرة واحدة
# =========================================
@asynccontextmanager
async def lifespan(app: FastAPI):
    print("جاري تهيئة قاعدة البيانات...")
    init_database()
    print("تم الإقلاع بنجاح!")
    yield

# =========================================
# إعداد التطبيق
# =========================================
app = FastAPI(
    title="عائلة الحوطية الرقمية",
    description="منصة عائلية متكاملة",
    version="1.0.0",
    lifespan=lifespan,
)
# Middleware التحليلات (محدث)
@app.middleware("http")
async def analytics_middleware(request: Request, call_next):
    if request.url.path.startswith("/static") or request.url.path in ("/favicon.ico", "/robots.txt"):
        return await call_next(request)

    user = request.session.get("user")

    if "session_id" not in request.session:
        request.session["session_id"] = str(uuid.uuid4())

    try:
        log_visit(request, user)
    except Exception as e:
        print(f"تحذير مؤقت في log_visit: {e}")

    response = await call_next(request)
    return response
# =========================================
# Middleware - الترتيب مهم جدًا!
# =========================================
# 1. SessionMiddleware (لازم يكون الأول)
app.add_middleware(
    SessionMiddleware,
    secret_key=os.getenv("SECRET_KEY", "super-secret-key-change-in-production"),
    session_cookie="family_session",
    max_age=60 * 60 * 24 * 30,  # 30 يوم
    same_site="lax",
    https_only=False  # ← مهم: False على المحلي، True على Render (نحلها بطريقة ذكية تحت)
)

# 2. CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # أو حط دومينك الحقيقي: ["https://hottiyya.onrender.com"]
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
app.include_router(family.router)
app.include_router(articles.router)
app.include_router(news.router)
app.include_router(permissions.router)

# =========================================
# الصفحة الرئيسية
# =========================================
@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    user = request.session.get("user")
    response = templates.TemplateResponse("index.html", {
        "request": request,
        "user": user,
        "today_visitors": get_today_visitors(),
        "total_visitors": get_total_visitors(),
        "online_count": get_online_count(),
        "online_users": get_online_users()[:8],
    })
    set_cache_headers(response)
    return response

@app.get("/about", response_class=HTMLResponse)
async def about_page(request: Request):
    user = request.session.get("user")
    response = templates.TemplateResponse("about.html", {
        "request": request,
        "user": user
    })
    set_cache_headers(response)
    return response

# =========================================
# الملف الشخصي
# =========================================
@app.get("/profile", response_class=HTMLResponse)
async def profile_page(request: Request):
    user = request.session.get("user")
    if not user:
        return RedirectResponse("/auth/login")
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

    new_csrf = generate_csrf_token()
    request.session["csrf_token"] = new_csrf

    return templates.TemplateResponse("profile.html", {
        "request": request,
        "user": user,
        "error": error,
        "success": success,
        "csrf_token": new_csrf
    })



@app.get("/debug/db-count")
async def debug_db_count():
    try:
        with get_db_context() as conn:
            # نستخدم RealDictCursor عشان يشتغل dict مباشرة
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("SELECT COUNT(*) AS total FROM family_name")
                total = cur.fetchone()["total"]

                cur.execute("""
                    SELECT  code, name     
                    FROM family_name 
                    ORDER BY name DESC 
                    LIMIT 15
                """)
                latest = cur.fetchall()  # هنا كل row هو dict جاهز

        return {
            "status": "success",
            "total_names_in_database": total,
            "latest_15_names": latest,
            "checked_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }
    except Exception as e:
        return {"status": "error", "message": str(e)}
# =========================================
# 404
# =========================================
@app.exception_handler(404)
async def not_found(request: Request, exc):
    return templates.TemplateResponse("404.html", {"request": request}, status_code=404)

# =========================================
# تشغيل التطبيق
# =========================================
if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)


# uvicorn main:app --reload


