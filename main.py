from fastapi.middleware.cors import CORSMiddleware
from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware
from routers import auth, admin, family, articles, news, permissions
import os
from contextlib import asynccontextmanager
from postgresql import init_database

@asynccontextmanager
async def lifespan(app: FastAPI):
    print("جاري تهيئة قاعدة البيانات...")
    init_database()   # ← هنا الدالة تشتغل مرة واحدة عند الإقلاع
    print("تم الإقلاع بنجاح!")
    yield


# =========================================
#           إعداد FastAPI
# =========================================
app = FastAPI(lifespan=lifespan)
templates = Jinja2Templates(directory="templates")

# Middleware
app.add_middleware(SessionMiddleware, secret_key=os.getenv("SECRET_KEY"), https_only=True)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://render.com"],
    allow_methods=["*"],
    allow_headers=["*"],
)
app.mount("/static", StaticFiles(directory="static"), name="static")

# Routers
app.include_router(news.router)
app.include_router(auth.router)
app.include_router(admin.router)
app.include_router(family.router)
app.include_router(articles.router)

# =========================================
# الصفحة الرئيسية
# =========================================
@app.get("/")
async def home(request: Request):
    user = request.session.get("user")  # ← أضف هذا
    return templates.TemplateResponse(
        "index.html",
        {
            "request": request,
            "user": user  # ← أضف هذا
        }
    )


# uvicorn main:app --reload


