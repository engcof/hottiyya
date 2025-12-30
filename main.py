from datetime import datetime
import os
import uuid
from urllib.parse import urlparse
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.sessions import SessionMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
from core.templates import templates
from psycopg2.extras import RealDictCursor
from postgresql import init_database, get_db_context

# استيراد الدوال الأمنية والمساعدة
from security.session import set_cache_headers
from security.rate_limit import initialize_rate_limiter

# استيراد الخدمات والراوترات
from services.analytics import log_visit, get_total_visitors, get_today_visitors, get_online_count, get_online_users
from services.notification import get_unread_notification_count
from routers import auth, admin, family, articles, news, permissions, data, profile,gallery,video,library
from dotenv import load_dotenv

load_dotenv()

# =========================================
# إعدادات البيئة والتكوين
# =========================================
# 1. التحقق من مفتاح الجلسة السري (SECRET KEY)
SESSION_SECRET = os.getenv("SECRET_KEY")
if not SESSION_SECRET:
    if os.getenv("RENDER_EXTERNAL_URL"): 
         raise ValueError("SECRET_KEY مفقود! يجب تعيينه في بيئة الإنتاج.")
    SESSION_SECRET = "super-secret-key-for-development-only" 

# 2. تحديد وضع HTTPS للإنتاج
IS_PROD = os.getenv("RENDER_EXTERNAL_URL") is not None or os.getenv("ENVIRONMENT") == "production"

# 3. تكوين متغيرات قاعدة البيانات من DATABASE_URL (مهم لـ Render)
if os.getenv("DATABASE_URL"):
    db = urlparse(os.getenv("DATABASE_URL"))
    os.environ["DB_HOST"] = db.hostname
    os.environ["DB_NAME"] = db.path[1:]
    os.environ["DB_USER"] = db.username
    os.environ["DB_PASSWORD"] = db.password
    os.environ["DB_PORT"] = str(db.port or 5432)

# =========================================
# Lifespan: تشغيل init_database و تهيئة مقيد المعدل
# =========================================
@asynccontextmanager
async def lifespan(app: FastAPI):
    print("جاري تهيئة قاعدة البيانات...")
    init_database()
    initialize_rate_limiter()
    print("تم الإقلاع بنجاح!")
    yield

# =========================================
# إعداد التطبيق
# =========================================
app = FastAPI(
    title="عائلة الحوطية الرقمية",
    description="منصة عائلية متكاملة",
    version="1.0.0",
    lifespan=lifespan, # 💡 تم إضافة lifespan لتهيئة قاعدة البيانات
)

# =========================================
# Middleware Logic - تحليلات الزوار
# =========================================
async def analytics_middleware(request: Request, call_next):
    # تجاهل الملفات الثابتة
    if request.url.path.startswith("/static") or request.url.path in ("/favicon.ico", "/robots.txt"):
        return await call_next(request)

    # الوصول إلى الجلسة آمن هنا بسبب ترتيب الإضافة
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
# Middleware 
# =========================================
# 1. Analytics Middleware (يجب أن يعمل بعد SessionMiddleware)
app.add_middleware(
    BaseHTTPMiddleware,
    dispatch=analytics_middleware
)

# 2. SessionMiddleware (يجب أن يكون أعمق طبقة لمعالجة الجلسة)
app.add_middleware(
    SessionMiddleware,
    secret_key=SESSION_SECRET,
    session_cookie="family_session",
    max_age=60 * 60 * 24 * 30,  # 30 يوم
    same_site="lax",
    https_only=IS_PROD, 
)

# 3. CORS (الطبقة الخارجية)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"] if not IS_PROD else ["https://yourdomain.com", "https://hottiyya.onrender.com"], 
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
app.include_router(data.router)
app.include_router(profile.router)
app.include_router(gallery.router)
app.include_router(video.router)
app.include_router(library.router)
# =========================================
#         الصفحة الرئيسية
# =========================================
@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    user = request.session.get("user")
    unread_count = 0 # القيمة الافتراضية
    with get_db_context() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:

            # 💡 جلب عدد الرسائل غير المقروءة إذا كان المستخدم مسجلاً
            if user:
                unread_count = get_unread_notification_count(user["id"]) # 💡 استخدام الدالة الجديدة
            # جلب العنوان لأحدث مقال لعرضه في الشريط المتحرك
            cur.execute("SELECT title FROM articles ORDER BY created_at DESC LIMIT 1")
            latest_article_title = cur.fetchone()
    response = templates.TemplateResponse("index.html", {
        "request": request,
        "user": user,
        "unread_count": unread_count,
        "today_visitors": get_today_visitors(),
        "total_visitors": get_total_visitors(),
        "online_count": get_online_count(),
        "online_users": get_online_users()[:18],
        "latest_article_title": latest_article_title['title'] if latest_article_title else 'لا توجد مقالات بعد',
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

@app.get("/debug/db-count")
async def debug_db_count():
    try:
        with get_db_context() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("SELECT COUNT(*) AS total FROM family_name")
                total = cur.fetchone()["total"]

                cur.execute("""
                    SELECT  code, name     
                    FROM family_name 
                    ORDER BY name DESC 
                    LIMIT 15
                """)
                latest = cur.fetchall()

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


