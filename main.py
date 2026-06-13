
import os
import uuid
import mimetypes
import logging
from urllib.parse import urlparse
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, Response
from fastapi.responses import HTMLResponse, PlainTextResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.sessions import SessionMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
from core.templates import templates

from postgresql import init_database

# استيراد الدوال الأمنية والمساعدة
from security.session import SessionService
from security.rate_limit import RateLimitService

# استيراد الخدمات والراوترات
from services.analytics_service import AnalyticsService
from services.google_service import GoogleService
from services.home_service import HomeService
from routers import auth, admin, family, articles, news, permissions, data, profile, gallery, video, library, about
from dotenv import load_dotenv

load_dotenv()

# إعداد السجلات الأمنية
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("MainApp")

# =========================================
# إعدادات البيئة والتكوين
# =========================================
SESSION_SECRET = os.getenv("SECRET_KEY")
if not SESSION_SECRET:
    if os.getenv("RENDER_EXTERNAL_URL"): 
         raise ValueError("🔥 ثغرة أمنية: SECRET_KEY مفقود! يجب تعيينه فوراً في بيئة الإنتاج على Render.")
    SESSION_SECRET = "super-secret-key-for-development-only" 

IS_PROD = os.getenv("RENDER_EXTERNAL_URL") is not None or os.getenv("ENVIRONMENT") == "production"

if os.getenv("DATABASE_URL"):
    db = urlparse(os.getenv("DATABASE_URL"))
    os.environ["DB_HOST"] = db.hostname
    os.environ["DB_NAME"] = db.path[1:]
    os.environ["DB_USER"] = db.username
    os.environ["DB_PASSWORD"] = db.password
    os.environ["DB_PORT"] = str(db.port or 5432)

# =========================================
# Lifespan: التشغيل الآمن والتهيئة
# =========================================
@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("🚀 جاري بدء تشغيل النظام ...")
    
    # 1. تهيئة قاعدة البيانات
    init_database()
    
    # 2. تهيئة مقيد المعدل لمنع هجمات DOS
    RateLimitService.initialize_rate_limiter()
    
    # 3. 🧹 تنظيف سجلات المكتبة العالقة لتوفير المساحة السحابية
    try:
        from services.library_service import LibraryService
        cleaned_count = LibraryService.cleanup_stuck_uploads()
        if cleaned_count > 0:
            logger.info(f"✅ تم تنظيف {cleaned_count} سجلات وملفات يتيمة من السحاب بنجاح.")
    except Exception as e:
        logger.error(f"⚠️ تفادي فشل أثناء التنظيف التلقائي: {e}")

    yield
    logger.info("🛑 جاري إغلاق السيرفر بسلام...")

# =========================================
# إنشاء التطبيق
# =========================================
app = FastAPI(
    title=" منصة الحوطية الرقمية",
    description="منصة رقمية متكاملة ومؤمنة",
    version="1.0.0",
    lifespan=lifespan,
)

# حقن دوال الصلاحيات وحالة البيئة مباشرة لقوالب جينجا
templates.env.globals.update(can=SessionService.can, is_prod=IS_PROD)

# =========================================
# البرمجيات الوسيطة (Middleware Logic)
# =========================================
async def analytics_middleware(request: Request, call_next):
    # مسارات الفحص السريع والتجاهل الفوري لحماية أداء السيرفر
    if request.url.path.startswith("/static") or request.url.path in ("/favicon.ico", "/robots.txt", "/sitemap.xml"):
        return await call_next(request)
    
    # تأمين معرف الجلسة الفريد للزائر
    if "session_id" not in request.session:
        request.session["session_id"] = str(uuid.uuid4())
        
    user = request.session.get("user")

    try:
        AnalyticsService.log_visit(request, user)
    except Exception as e:
        logger.warning(f"خطأ غير معطل في log_visit: {e}")

    return await call_next(request)

# 🚨 الترتيب الذهبي لحقن الـ Middlewares في FastAPI (من الأسفل للأعلى في التنفيذ للـ Request)
app.add_middleware(BaseHTTPMiddleware, dispatch=analytics_middleware)

app.add_middleware(
    SessionMiddleware,
    secret_key=SESSION_SECRET,
    session_cookie="family_session",
    max_age=60 * 60 * 24 * 30,  # 30 يوم
    same_site="lax",
    https_only=IS_PROD, # تفعيل التشفير الإجباري في الإنتاج
)

# سد ثغرة حظر النجمة الكونية مع الـ Credentials في CORS
allowed_origins = ["https://hottiyya.onrender.com"] if IS_PROD else ["http://localhost:8000", "http://127.0.0.1:8000"]
app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# =========================================
# أصول ملفات النظام (Static Files)
# =========================================
mimetypes.add_type('font/woff2', '.woff2')
mimetypes.add_type('font/woff', '.woff')
mimetypes.add_type('text/css', '.css')

app.mount("/static", StaticFiles(directory="static"), name="static")

@app.get("/favicon.ico", include_in_schema=False)
async def favicon():
    # منع استهلاك موارد السيرفر وإرجاع الأيقونة مباشرة من مجلدها
    fav_path = "static/icon/favicon.ico"
    if os.path.exists(fav_path):
        return FileResponse(fav_path)
    return Response(status_code=204)

# =========================================
# تضمين الراوترات الرسمية للمنصة
# =========================================
app.include_router(auth.router)
app.include_router(admin.router)
app.include_router(articles.router)
app.include_router(news.router)
app.include_router(permissions.router)
app.include_router(data.router)
app.include_router(profile.router)
app.include_router(gallery.router)
app.include_router(video.router)
app.include_router(library.router)
app.include_router(about.router)
# 🔒 حماية بيانات العائلة: تشغيل الشجرة والبيانات فقط في السيرفر المحلي
if not IS_PROD:
    app.include_router(family.router)
# =========================================
# المتحكمات والصفحات الرئيسية
# =========================================
@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    context = SessionService.get_page_context(request)
    home_data = HomeService.get_homepage_data()
    
    context.update({
        "today_visitors": AnalyticsService.get_today_visitors(),
        "total_visitors": AnalyticsService.get_total_visitors(),
        "online_count": AnalyticsService.get_online_count(),
        "online_users": AnalyticsService.get_online_users()[:18],
        "latest_article": home_data.get('latest_article'),
        "latest_book": home_data.get('latest_book'),
        # ✅ سد نقص المتغير الأساسي لعرض الكروت في الواجهة
        "articles_for_homepage": home_data.get('articles_for_homepage', []) 
    })
    
    response = templates.TemplateResponse("index.html", context)
    SessionService.set_cache_headers(response)
    return response

# =========================================
# محركات الأرشفة والخرائط (SEO & Handlers)
# =========================================
@app.exception_handler(404)
async def not_found(request: Request, exc):
    context = SessionService.get_page_context(request)
    return templates.TemplateResponse("404.html", context, status_code=404)

@app.get("/googlea84e43178e487f63.html", response_class=HTMLResponse)
async def google_verification():
    return "google-site-verification: googlea84e43178e487f63.html"

@app.get("/sitemap.xml")
async def sitemap():
    base_url = "https://hottiyya.onrender.com"
    static_pages = [
        {"loc": f"{base_url}/", "changefreq": "daily", "priority": "1.0"},
        {"loc": f"{base_url}/articles", "changefreq": "daily", "priority": "0.8"},
        {"loc": f"{base_url}/news", "changefreq": "daily", "priority": "0.8"},
    ]
    
    try:
        dynamic_pages = GoogleService.get_all_sitemap_urls(base_url)
    except Exception:
        dynamic_pages = []
        
    all_pages = static_pages + dynamic_pages

    xml_lines = ['<?xml version="1.0" encoding="UTF-8"?>']
    xml_lines.append('<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">')
    for page in all_pages:
        xml_lines.append(f'<url><loc>{page["loc"]}</loc><changefreq>{page["changefreq"]}</changefreq><priority>{page["priority"]}</priority></url>')
    xml_lines.append('</urlset>')
    
    return Response(content="".join(xml_lines), media_type="application/xml")

@app.get("/robots.txt", response_class=PlainTextResponse)
async def robots():
    content = "User-agent: *\nAllow: /\nSitemap: https://hottiyya.onrender.com/sitemap.xml"
    return content.strip()

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)

# uvicorn main:app --reload 


