import os
import logging
import bcrypt
import sqlite3
import secrets  # لحماية إضافية مع CSRF
from typing import Optional
from dotenv import load_dotenv
from datetime import timedelta
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi import FastAPI, Request, Depends, HTTPException, Form
from fastapi.middleware.cors import CORSMiddleware

load_dotenv()
SECRET_KEY = os.getenv("SECRET_KEY")
DB_PATH = os.getenv("DB_PATH", "/home/engcof/database/family_tree.db")

if not SECRET_KEY or not DB_PATH:
    raise RuntimeError("❌ SECRET_KEY or DB_PATH not set in .env file")
logging.basicConfig(level=logging.DEBUG)

# =========================================
#           إعداد FastAPI
# =========================================
app = FastAPI()

# إعداد Jinja2 لعرض HTML
templates = Jinja2Templates(directory="templates")

# إعداد الجلسات باستخدام SessionMiddleware من starlette
app.add_middleware(
    SessionMiddleware,
    secret_key=SECRET_KEY,
    session_cookie="session",
    max_age=int(timedelta(hours=1).total_seconds())
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # يجب تحديد المجالات المسموح بها في الإنتاج
    allow_methods=["*"],
    allow_headers=["*"],

)
# إعداد مسار ملفات Static
app.mount("/static", StaticFiles(directory="static"), name="static")


# =========================================
#              دوال مساعدة
# =========================================
def get_db():
    logging.debug(f"Attempting to connect to database at {DB_PATH}")
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def get_db_dep():
    conn = get_db()
    try:
        yield conn
    finally:
        conn.close()

def get_current_user(request: Request):
    username = request.session.get("username")
    role = request.session.get("role")
    if not username:
        raise HTTPException(status_code=401, detail="غير مسجل دخول")
    return {"username": username, "role": role}

# دالة للتحقق من كلمة المرور
def check_password(password, hashed):
    return bcrypt.checkpw(password.encode('utf-8'), hashed.encode('utf-8'))

def hash_password(password: str) -> str:
    """
    دالة لتشفير كلمة المرور باستخدام bcrypt.
    تأخذ كلمة المرور النصية وتعيد كلمة مرور مشفرة.
    """
    hashed = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt())
    return hashed.decode('utf-8')

def get_user(condition: str, param: tuple):
    conn = get_db()
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute(f"SELECT * FROM users WHERE {condition}", param)
    user = cursor.fetchone()
    conn.close()
    return user


# دالة لتوليد رمز CSRF
def generate_csrf_token():
    return secrets.token_urlsafe(32)

# دالة للتحقق من CSRF
def verify_csrf_token(request: Request, csrf_token: str):
    session_token = request.session.get("csrf_token")
    if not csrf_token or csrf_token != session_token:
        raise HTTPException(status_code=403, detail="رمز CSRF غير صالح أو مفقود")

def set_cache_headers(response: HTMLResponse):
    response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, proxy-revalidate'
    response.headers['Pragma'] = 'no-cache'
    response.headers['Expires'] = '0'
    return response

def error_response(status_code: int, detail: str):
    raise HTTPException(status_code=status_code, detail=detail)

# =========================================
#            صفحة الرئيسية
# =========================================
@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    user = request.session.get("user", None)
   
    if user:
        response = templates.TemplateResponse("index.html", {"request": request, "user": user})
        set_cache_headers(response)
        return response
    else:
        response = templates.TemplateResponse("index.html", {"request": request, "user": None})
        set_cache_headers(response)
        return response

# =========================================
#          إدارة الدخول والخروج 
# =========================================
@app.get("/login", response_class=HTMLResponse)
async def login(request: Request):
    csrf_token = generate_csrf_token()
    request.session["csrf_token"] = csrf_token  # تخزين رمز CSRF في الجلسة
    response = templates.TemplateResponse("login.html", {"request": request, "csrf_token": csrf_token})
    set_cache_headers(response)
    return response

@app.post("/login")
async def login_post(request: Request, username: str = Form(...), password: str = Form(...), csrf_token: str = Form(...)):
    # التحقق من CSRF token
    try:
        verify_csrf_token(request, csrf_token)
    except HTTPException as e:
        raise e

    # جلب بيانات المستخدم من قاعدة البيانات
    user_data = get_user("username = ?", (username,))

    # التحقق من كلمة المرور
    if user_data:
        password_valid = check_password(password, user_data["password"])
    else:
        password_valid = False

    if user_data and password_valid:
        # تخزين اسم المستخدم في الجلسة
        request.session["user"] = username
        request.session["username"] = username
        request.session["role"] = user_data["role"]
        request.session["message"] = "تم تسجيل الدخول بنجاح ✅"

        # إعادة التوجيه إلى الصفحة الرئيسية
        response = RedirectResponse(url="/", status_code=303)
        return response
    else:
        raise HTTPException(status_code=401, detail="اسم المستخدم أو كلمة المرور غير صحيحة")


# 4. تسجيل الخروج
@app.get("/logout")
async def logout(request: Request):
    request.session.clear()  # مسح جميع البيانات من الجلسة
    response = RedirectResponse(url="/", status_code=303)  # إعادة توجيه المستخدم إلى الصفحة الرئيسية بعد الخروج
    set_cache_headers(response)
    return response

# =========================================
#             إدارة المستخدمين 
# =========================================
@app.get("/admin")
async def admin(request: Request, page: int = 1, user=Depends(get_current_user)):
    if not user or user.get("role") != "admin":
        return RedirectResponse("/", status_code=303)
    
    # توليد CSRF token وتخزينه في الجلسة
    csrf_token = generate_csrf_token()
    request.session["csrf_token"] = csrf_token

    # فتح قاعدة البيانات
    conn = get_db()
    cursor = conn.cursor()

    # تحديد عدد المستخدمين لكل صفحة
    users_per_page = 10
    offset = (page - 1) * users_per_page

    # جلب المستخدمين
    cursor.execute("SELECT id, username, role FROM users LIMIT ? OFFSET ?", (users_per_page, offset))
    users = cursor.fetchall()
    
    # اسم المدير الأساسي
    MASTER_ADMIN_USERNAME = "admin"

    # إذا كان المدير هو المدير الاحتياطي، قم بإخفاء المدير الأساسي
    if user["username"] != MASTER_ADMIN_USERNAME:
        users = [u for u in users if u["username"] != MASTER_ADMIN_USERNAME]


    # جلب جميع الصلاحيات
    cursor.execute("SELECT id, name, category FROM permissions")
    permissions = cursor.fetchall()

    # جلب صلاحيات كل مستخدم
    user_permissions = {}
    for u in users:
        cursor.execute("""
            SELECT permissions.name
            FROM permissions
            JOIN user_permissions ON permissions.id = user_permissions.permission_id
            WHERE user_permissions.user_id = ?
        """, (u[0],))
        user_permissions[u[0]] = [p[0] for p in cursor.fetchall()]

    # حساب عدد الصفحات
    cursor.execute("SELECT COUNT(*) FROM users")
    total_users = cursor.fetchone()[0]
    total_pages = (total_users + users_per_page - 1) // users_per_page

    # إنشاء الاستجابة
    response = templates.TemplateResponse("admin.html", {
        "request": request,
        "csrf_token": csrf_token,
        "users": users,
        "permissions": permissions,
        "user_permissions": user_permissions,
        "current_page": page,
        "total_pages": total_pages
    })

    set_cache_headers(response)
    return response


# إضافة مستخدم جديد
@app.post("/admin/add_user")
async def add_user(request: Request, username: str = Form(...), password: str = Form(...), role: str = Form(...), csrf_token: str = Form(...)):
    verify_csrf_token(request, csrf_token)

    conn = get_db()
    cursor = conn.cursor()

    # تحقق من وجود المستخدم
    cursor.execute("SELECT id FROM users WHERE username = ?", (username,))
    if cursor.fetchone():
        raise HTTPException(status_code=400, detail="المستخدم موجود بالفعل")

    cursor.execute("INSERT INTO users (username, password, role) VALUES (?, ?, ?)",
                   (username, hash_password(password), role))
    conn.commit()
    
    return RedirectResponse(url="/admin", status_code=303)

# حذف مستخدم
@app.post("/admin/delete_user")
async def delete_user(request: Request, user_id: int = Form(...), csrf_token: str = Form(...)):
    verify_csrf_token(request, csrf_token)

    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute("DELETE FROM users WHERE id = ?", (user_id,))
    conn.commit()

    return RedirectResponse(url="/admin", status_code=303)

# تعديل مستخدم
@app.post("/admin/edit_user")
async def edit_user(request: Request, user_id: int = Form(...), username: str = Form(...), role: str = Form(...), csrf_token: str = Form(...)):
    verify_csrf_token(request, csrf_token)

    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("UPDATE users SET username = ?, role = ? WHERE id = ?", (username, role, user_id))
    conn.commit()

    return RedirectResponse(url="/admin", status_code=303)

# دالة لتغيير كلمة مرور مستخدم
@app.post("/admin/change_password")
async def change_password(request: Request, user_id: int = Form(...), new_password: str = Form(...), csrf_token: str = Form(...)):
    # التحقق من رمز CSRF
    verify_csrf_token(request, csrf_token)

    # التحقق من صلاحيات المستخدم
    user = request.session.get("user", None)
    if not user or user != "admin":
        raise HTTPException(status_code=403, detail="أنت بحاجة إلى صلاحيات إدارية للوصول إلى هذه الصفحة")

    # تشفير كلمة المرور الجديدة
    hashed_password = hash_password(new_password)

    # تحديث كلمة المرور في قاعدة البيانات
    conn = get_db()
    cursor = conn.cursor()
    
    # التحقق من وجود المستخدم
    cursor.execute("SELECT id FROM users WHERE id = ?", (user_id,))
    if not cursor.fetchone():
        raise HTTPException(status_code=404, detail="المستخدم غير موجود")

    # تحديث كلمة المرور
    cursor.execute("UPDATE users SET password = ? WHERE id = ?", (hashed_password, user_id))
    conn.commit()

    # إعادة توجيه إلى صفحة الإدارة بعد التحديث
    return RedirectResponse(url="/admin", status_code=303)

# منح صلاحية لمستخدم
@app.post("/admin/give_permission")
async def give_permission(request: Request, user_id: int = Form(...), permission_id: int = Form(...), csrf_token: str = Form(...)):
    verify_csrf_token(request, csrf_token)

    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("INSERT OR IGNORE INTO user_permissions (user_id, permission_id) VALUES (?, ?)", (user_id, permission_id))
    conn.commit()

    return RedirectResponse(url="/admin", status_code=303)

# إزالة صلاحية من مستخدم
@app.post("/admin/remove_permission")
async def remove_permission(request: Request, user_id: int = Form(...), permission_id: int = Form(...), csrf_token: str = Form(...)):
    verify_csrf_token(request, csrf_token)

    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("DELETE FROM user_permissions WHERE user_id = ? AND permission_id = ?", (user_id, permission_id))
    conn.commit()

    return RedirectResponse(url="/admin", status_code=303)


# 5. صفحة غير موجودة (خطأ 404)
@app.get("/404")
async def not_found(request: Request):
    return {"message": "الصفحة غير موجودة"}

@app.get("/session_test")
async def session_test(request: Request):
    """
    دالة مؤقتة لاختبار الجلسة.
    تعرض اسم المستخدم المخزن في الجلسة حالياً.
    """
    user = request.session.get("user", None)
    print("Session user:", user)  # سيتم طباعتها في الـ console
    return {"session_user": user}









#uvicorn main:app --reload