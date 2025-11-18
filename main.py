from fastapi.middleware.cors import CORSMiddleware
from fastapi import FastAPI, Request, Form
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse, RedirectResponse
from starlette.middleware.sessions import SessionMiddleware
from security.hash import check_password, hash_password
from postgresql import get_db_context
from routers import auth, admin, family, articles, news, permissions
import os



# =========================================
#           إعداد FastAPI
# =========================================
app = FastAPI()
templates = Jinja2Templates(directory="templates")

# Middleware
app.add_middleware(
    SessionMiddleware, 
    secret_key=os.getenv("SECRET_KEY"), 
    https_only=True
)

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

# === صفحة الملف الشخصي وتغيير كلمة السر ===
@app.get("/profile")
async def profile_page(request: Request):
    user = request.session.get("user")
    if not user:
        return RedirectResponse("/auth/login")
    return templates.TemplateResponse("profile.html", {
        "request": request,
        "user": user
    })

@app.post("/profile/change-password")
async def change_password(
    request: Request,
    current_password: str = Form(...),
    new_password: str = Form(...),
    confirm_password: str = Form(...)
):
    user = request.session.get("user")
    if not user:
        return RedirectResponse("/auth/login")

    error = None
    success = False

    if new_password != confirm_password:
        error = "كلمتا السر الجديدتان غير متطابقتين!"
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

    return templates.TemplateResponse("profile.html", {
        "request": request,
        "user": user,
        "error": error,
        "success": success
    })
# uvicorn main:app --reload


