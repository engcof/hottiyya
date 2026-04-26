from datetime import datetime
import os
import uuid
from urllib.parse import urlparse
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, Response
from fastapi.responses import HTMLResponse,PlainTextResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.sessions import SessionMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
from core.templates import templates, get_global_context
from psycopg2.extras import RealDictCursor
from postgresql import init_database, get_db_context

# استيراد الدوال الأمنية والمساعدة
from security.session import set_cache_headers
from security.rate_limit import initialize_rate_limiter
from utils.has_permissions import can

# استيراد الخدمات والراوترات
from services.analytics import log_visit, get_total_visitors, get_today_visitors, get_online_count, get_online_users
from services.notification import get_unread_notification_count
from utils.has_permissions import can
from services.google_service import GoogleService
from services.home_service import HomeService
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
# Lifespan: تشغيل init_database و تنظيف المكتبة
# =========================================
@asynccontextmanager
async def lifespan(app: FastAPI):
    print("🚀 جاري بدء تشغيل النظام...")
    
    # 1. تهيئة قاعدة البيانات
    print("📦 جاري تهيئة قاعدة البيانات...")
    init_database()
    
    # 2. تهيئة مقيد المعدل
    initialize_rate_limiter()
    
    # 3. 🧹 تشغيل التنظيف التلقائي للمكتبة (سجلات pending و error)
    # هذا سيحذف السجلات العالقة وينظف السحاب (Cloudinary/Drive)
    try:
        from services.library_service import LibraryService
        print("🧹 جاري فحص وتنظيف سجلات المكتبة العالقة...")
        cleaned_count = LibraryService.cleanup_stuck_uploads()
        if cleaned_count > 0:
            print(f"✅ تم تنظيف {cleaned_count} سجلات وملفات يتيمة بنجاح.")
        else:
            print("✨ لا توجد سجلات عالقة لتنظيفها.")
    except Exception as e:
        print(f"⚠️ تحذير: فشل تنفيذ التنظيف التلقائي: {e}")

    print("🏁 تم الإقلاع بنجاح!")

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

templates.env.globals.update(can=can)

# =========================================
# Middleware Logic - تحليلات الزوار
# =========================================
async def analytics_middleware(request: Request, call_next):
    # تجاهل الملفات الثابتة
    if request.url.path.startswith("/static") or request.url.path in ("/favicon.ico", "/robots.txt", "/sitemap.xml"):
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
    allow_origins=["*"] if not IS_PROD else ["https://hottiyya.onrender.com"], 
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
    # لا نحتاج لتعريف user أو unread_count هنا، فالسياق الموحد سيتكفل بهما
    home_data = HomeService.get_homepage_data()
    
    # 2. تجهيز السياق الموحد (سيحتوي على user و can_view و unread_count)
    context = get_global_context(request)
    
    # 3. تحديث السياق بالبيانات الخاصة بالصفحة الرئيسية
    context.update({
        "today_visitors": get_today_visitors(),
        "total_visitors": get_total_visitors(),
        "online_count": get_online_count(),
        "online_users": get_online_users()[:18],
        "latest_article": home_data['latest_article'],
        "latest_book": home_data['latest_book']
    })
    
    response = templates.TemplateResponse("index.html", context)
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
    context = get_global_context(request)
    return templates.TemplateResponse("404.html", context, status_code=404)

@app.get("/googlea84e43178e487f63.html", response_class=HTMLResponse)
async def google_verification():
    # المحتوى يجب أن يكون بالضبط ما بداخل ملف جوجل
    return "google-site-verification: googlea84e43178e487f63.html"

@app.get("/sitemap.xml")
async def sitemap():
    base_url = "https://hottiyya.onrender.com"
    static_pages = [
        {"loc": f"{base_url}/", "changefreq": "daily", "priority": "1.0"},
        {"loc": f"{base_url}/articles", "changefreq": "daily", "priority": "0.8"},
        {"loc": f"{base_url}/news", "changefreq": "daily", "priority": "0.8"},
    ]
    
    dynamic_pages = GoogleService.get_all_sitemap_urls(base_url)
    all_pages = static_pages + dynamic_pages

    # بناء XML نظيف جداً وبدون مسافات بادئة
    xml_lines = ['<?xml version="1.0" encoding="UTF-8"?>']
    xml_lines.append('<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">')
    
    for page in all_pages:
        xml_lines.append(f'<url><loc>{page["loc"]}</loc><changefreq>{page["changefreq"]}</changefreq><priority>{page["priority"]}</priority></url>')
    
    xml_lines.append('</urlset>')
    
    return Response(content="".join(xml_lines), media_type="application/xml")


@app.get("/robots.txt", response_class=PlainTextResponse)
async def robots():
    content = "User-agent: *\nAllow: /\nSitemap: https://hottiyya.onrender.com/sitemap.xml"
    return content.strip() # استخدام strip لضمان عدم وجود سطر فارغ في البداية
# =========================================
# تشغيل التطبيق
# =========================================
if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)

# uvicorn main:app --reload 


