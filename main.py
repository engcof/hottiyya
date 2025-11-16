from fastapi.middleware.cors import CORSMiddleware
from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware
from routers import auth, admin, family, permissions
import os

# =========================================
#           إعداد FastAPI
# =========================================
app = FastAPI()
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
app.include_router(auth.router)
app.include_router(admin.router)
app.include_router(family.router)
#app.include_router(permissions.router)

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






