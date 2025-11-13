import os
import logging
import bcrypt
import psycopg2
import secrets  # لحماية إضافية مع CSRF
from typing import Optional
from dotenv import load_dotenv
from datetime import timedelta
from contextlib import contextmanager
from psycopg2.extras import RealDictCursor
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi import FastAPI, Request, Depends, HTTPException, Form
from fastapi.middleware.cors import CORSMiddleware

load_dotenv()
SECRET_KEY = os.getenv("SECRET_KEY")
DB_HOST = os.getenv("DB_HOST")  # أو يمكنك تخصيص عنوان الـHost
DB_NAME = os.getenv("DB_NAME")
DB_USER = os.getenv("DB_USER")
DB_PASSWORD = os.getenv("DB_PASSWORD")

if not SECRET_KEY:
    raise RuntimeError("❌ SECRET_KEY or DB_PATH not set in .env file")

# إعداد الـ logger في بداية الملف
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("app.log"),      # يخزن في ملف
        logging.StreamHandler()              # يطبع في الـ console
    ]
)
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)  # اسم الـ logger هو اسم الملف

# دالة للتحقق من وجود جدول وإنشاؤه إذا لم يكن موجودًا
def init_database():
    conn = None
    try:
        conn = psycopg2.connect(
            host=os.getenv("DB_HOST"),
            dbname=os.getenv("DB_NAME"),
            user=os.getenv("DB_USER"),
            password=os.getenv("DB_PASSWORD"),
            port="5432",
            sslmode="require"
        )
        conn.autocommit = True
        cur = conn.cursor()

        # تحقق من وجود جدول users
        cur.execute("SELECT to_regclass('public.users');")
        if cur.fetchone()[0] is not None:
            logger.info("جدول users موجود بالفعل.")
            cur.close()
            conn.close()
            return

        logger.info("إنشاء جدول users وإضافة المستخدم admin...")

        # إنشاء جدول users
        cur.execute("""
            CREATE TABLE users (
                id SERIAL PRIMARY KEY,
                username TEXT UNIQUE NOT NULL,
                password TEXT NOT NULL,
                role TEXT CHECK(role IN ('admin', 'manager', 'user')) DEFAULT 'user'
            );
        """)

        # إضافة admin
        hashed = bcrypt.hashpw("admin123".encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
        cur.execute("""
            INSERT INTO users (username, password, role) 
            VALUES (%s, %s, %s) ON CONFLICT (username) DO NOTHING
        """, ("admin", hashed, "admin"))

        logger.info("تم إنشاء جدول users وإضافة admin بنجاح!")

          # إنشاء الجداول
        cur.execute('''
            CREATE TABLE IF NOT EXISTS family_name (
                code TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                f_code TEXT,
                m_code TEXT,
                w_code TEXT,
                h_code TEXT,
                type TEXT CHECK(type IN ('ابن', 'ابنة', 'زوج', 'زوجة', 'ابن زوج', 'ابنة زوج', 'ابن زوجة', 'ابنة زوجة')),
                level INTEGER,
                FOREIGN KEY(f_code) REFERENCES family_name(code) ON DELETE SET NULL,
                FOREIGN KEY(m_code) REFERENCES family_name(code) ON DELETE SET NULL,
                FOREIGN KEY(w_code) REFERENCES family_name(code) ON DELETE SET NULL,
                FOREIGN KEY(h_code) REFERENCES family_name(code) ON DELETE SET NULL
            );
        ''')
        conn.commit()
        
        cur.execute('''
            CREATE TABLE IF NOT EXISTS family_info (
                id SERIAL PRIMARY KEY,       
                code_info TEXT,
                gender TEXT,
                d_o_b TEXT,
                d_o_d TEXT,
                email TEXT,
                phone TEXT,
                address TEXT,
                p_o_b TEXT,
                FOREIGN KEY(code_info) REFERENCES family_name(code)       
            );
        ''')
        conn.commit()
        
        cur.execute('''
            CREATE TABLE IF NOT EXISTS family_picture (
                id SERIAL PRIMARY KEY,       
                code_pic TEXT,
                pic_path TEXT,
                picture BYTEA,
                FOREIGN KEY(code_pic) REFERENCES family_name(code)       
            );
        ''')
        conn.commit()
        
        cur.execute('''
            CREATE TABLE IF NOT EXISTS articles (
                id SERIAL PRIMARY KEY,
                title TEXT NOT NULL,
                content TEXT NOT NULL,
                author TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        ''')
        conn.commit()
        
        cur.execute('''
            CREATE TABLE IF NOT EXISTS comments (
                id SERIAL PRIMARY KEY,
                article_id INTEGER,
                username TEXT,
                content TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(article_id) REFERENCES articles(id)
            );
        ''')
        conn.commit()
        
        cur.execute('''
        CREATE TABLE IF NOT EXISTS logs (
            id SERIAL PRIMARY KEY,
            username TEXT NOT NULL,
            action TEXT NOT NULL,
            target TEXT,
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        ''')
        conn.commit()
        
        cur.execute('''
            CREATE TABLE IF NOT EXISTS news (
                id SERIAL PRIMARY KEY,
                title TEXT NOT NULL,
                content TEXT NOT NULL,
                image_url TEXT,
                video_url TEXT,
                author TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        ''')
        conn.commit()

        # جدول الصلاحيات
        cur.execute("""
            CREATE TABLE IF NOT EXISTS permissions (
                id SERIAL PRIMARY KEY,
                name TEXT UNIQUE NOT NULL,
                description TEXT,
                category TEXT DEFAULT 'عام'          
            );
            """)
        conn.commit()
        
        # جدول ربط المستخدمين بالصلاحيات (many-to-many)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS user_permissions (
                user_id INTEGER,
                permission_id INTEGER,
                FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE,
                FOREIGN KEY(permission_id) REFERENCES permissions(id) ON DELETE CASCADE,
                PRIMARY KEY (user_id, permission_id)
            );
            """)
        conn.commit()
        
       # --------------------------------------
        # 4️⃣ إضافة الصلاحيات الأساسية
        # --------------------------------------
        permissions_list = [
            # شجرة العائلة
            ("add_member", "إضافة عضو جديد في شجرة العائلة", 'الشجرة'),
            ("edit_member", "تعديل بيانات الأعضاء", 'الشجرة'),
            ("delete_member", "حذف الأعضاء من الشجرة", 'الشجرة'),

            # المقالات
            ("add_article", "إضافة مقال جديد", 'المقالات'),
            ("edit_article", "تعديل المقالات", 'المقالات'),
            ("delete_article", "حذف المقالات", 'المقالات'),

            # الأخبار
            ("add_news", "إضافة خبر جديد", 'الأخبار'),
            ("edit_news", "تعديل الأخبار", 'الأخبار'),
            ("delete_news", "حذف الأخبار", 'الأخبار'),

            # التعليقات
            ("add_comment", "إضافة تعليق", 'عام'),
            ("delete_comment", "حذف تعليق", 'عام'),

            # السجل
            ("view_logs", "عرض سجل النشاطات", 'عام'),
        ]

        # إدخال الصلاحيات مع تجاهل التكرار
        for name, desc, categ in permissions_list:
            cur.execute("""
                INSERT INTO permissions (name, description, category)
                VALUES (%s, %s, %s)
                ON CONFLICT (name) DO NOTHING
            """, (name, desc, categ))

        conn.commit()

        cur.close()
        conn.close()

    except Exception as e:
        logger.error(f"فشل في تهيئة قاعدة البيانات: {e}")
        if conn:
            conn.close()
        # لا نوقف التطبيق – فقط نسجل الخطأ

# استدعِ الدالة عند بدء التطبيق
init_database()

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
    allow_origins=["https://render.com"],  # يجب تحديد المجالات المسموح بها في الإنتاج
    allow_methods=["*"],
    allow_headers=["*"],

)

# إعداد مسار ملفات Static
app.mount("/static", StaticFiles(directory="static"), name="static")

# =========================================
#              دوال مساعدة
# =========================================
# context manager للاتصال
@contextmanager
def get_db_context():
    conn = None
    try:
        host = os.getenv("DB_HOST")
        dbname = os.getenv("DB_NAME")
        user = os.getenv("DB_USER")
        password = os.getenv("DB_PASSWORD")

        # تحقق من وجود القيم
        if not all([host, dbname, user, password]):
            raise ValueError("متغيرات قاعدة البيانات مفقودة! أضفها في Render Environment.")

        logger.info(f"الاتصال بقاعدة البيانات: {user}@{host}/{dbname}")

        conn = psycopg2.connect(
            host=host,
            dbname=dbname,
            user=user,
            password=password,
            port="5432",
            sslmode="require"  # إجبار SSL
        )
        yield conn
    except Exception as e:
        logger.error(f"خطأ في الاتصال بقاعدة البيانات: {e}")
        if conn:
            conn.rollback()
        raise
    finally:
        if conn and not conn.closed:
            conn.close()

# Dependency لـ FastAPI
def get_db():
    with get_db_context() as conn:
        yield conn

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

def get_user(condition: str, param: tuple, db=None):
    with get_db_context() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cursor:
            cursor.execute(f"SELECT * FROM users WHERE {condition}", param)
            user = cursor.fetchone()
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
async def login_post(
    request: Request, 
    username: str = Form(...), 
    password: str = Form(...), 
    csrf_token: str = Form(...),
    db=Depends(get_db)):
    # التحقق من CSRF token
    try:
        verify_csrf_token(request, csrf_token)
    except HTTPException as e:
        raise e
    
    # جلب بيانات المستخدم من قاعدة البيانات
    user_data = get_user("username = %s", (username,), db)

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
    
    csrf_token = generate_csrf_token()
    request.session["csrf_token"] = csrf_token

    with get_db_context() as conn:
        with conn.cursor() as cursor:
            users_per_page = 10
            offset = (page - 1) * users_per_page

            cursor.execute("SELECT id, username, role FROM users LIMIT %s OFFSET %s", (users_per_page, offset))
            users = cursor.fetchall()

            MASTER_ADMIN_USERNAME = "admin"
            if user["username"] != MASTER_ADMIN_USERNAME:
                users = [u for u in users if u[1] != MASTER_ADMIN_USERNAME]

            # جلب الصلاحيات
            cursor.execute("SELECT id, name, category FROM permissions")
            permissions = cursor.fetchall()

            # جلب صلاحيات كل مستخدم
            user_permissions = {}
            for u in users:
                cursor.execute("""
                    SELECT permissions.name
                    FROM permissions
                    JOIN user_permissions ON permissions.id = user_permissions.permission_id
                    WHERE user_permissions.user_id = %s
                """, (u[0],))
                user_permissions[u[0]] = [p[0] for p in cursor.fetchall()]

            cursor.execute("SELECT COUNT(*) FROM users")
            total_users = cursor.fetchone()[0]
            total_pages = (total_users + users_per_page - 1) // users_per_page

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

@app.post("/admin/add_user")
async def add_user(request: Request, username: str = Form(...), password: str = Form(...), role: str = Form(...), csrf_token: str = Form(...)):
    verify_csrf_token(request, csrf_token)

    with get_db_context() as conn:
        with conn.cursor() as cursor:
            cursor.execute("SELECT id FROM users WHERE username = %s", (username,))
            if cursor.fetchone():
                raise HTTPException(status_code=400, detail="المستخدم موجود بالفعل")

            cursor.execute(
                "INSERT INTO users (username, password, role) VALUES (%s, %s, %s)",
                (username, hash_password(password), role)
            )
            conn.commit()

    return RedirectResponse(url="/admin", status_code=303)

@app.post("/admin/delete_user")
async def delete_user(request: Request, user_id: int = Form(...), csrf_token: str = Form(...)):
    verify_csrf_token(request, csrf_token)

    with get_db_context() as conn:
        with conn.cursor() as cursor:
            cursor.execute("DELETE FROM users WHERE id = %s", (user_id,))
            conn.commit()

    return RedirectResponse(url="/admin", status_code=303)

@app.post("/admin/edit_user")
async def edit_user(request: Request, user_id: int = Form(...), username: str = Form(...), role: str = Form(...), csrf_token: str = Form(...)):
    verify_csrf_token(request, csrf_token)

    with get_db_context() as conn:
        with conn.cursor() as cursor:
            cursor.execute("UPDATE users SET username = %s, role = %s WHERE id = %s", (username, role, user_id))
            conn.commit()

    return RedirectResponse(url="/admin", status_code=303)

@app.post("/admin/change_password")
async def change_password(request: Request, user_id: int = Form(...), new_password: str = Form(...), csrf_token: str = Form(...)):
    verify_csrf_token(request, csrf_token)

    user = request.session.get("user", None)
    if not user or user != "admin":
        raise HTTPException(status_code=403, detail="أنت بحاجة إلى صلاحيات إدارية")

    hashed_password = hash_password(new_password)

    with get_db_context() as conn:
        with conn.cursor() as cursor:
            cursor.execute("SELECT id FROM users WHERE id = %s", (user_id,))
            if not cursor.fetchone():
                raise HTTPException(status_code=404, detail="المستخدم غير موجود")

            cursor.execute("UPDATE users SET password = %s WHERE id = %s", (hashed_password, user_id))
            conn.commit()

    return RedirectResponse(url="/admin", status_code=303)

@app.post("/admin/give_permission")
async def give_permission(request: Request, user_id: int = Form(...), permission_id: int = Form(...), csrf_token: str = Form(...)):
    verify_csrf_token(request, csrf_token)

    with get_db_context() as conn:
        with conn.cursor() as cursor:
            cursor.execute("""
                INSERT INTO user_permissions (user_id, permission_id)
                VALUES (%s, %s)
                ON CONFLICT DO NOTHING
            """, (user_id, permission_id))
            conn.commit()

    return RedirectResponse(url="/admin", status_code=303)

@app.post("/admin/remove_permission")
async def remove_permission(request: Request, user_id: int = Form(...), permission_id: int = Form(...), csrf_token: str = Form(...)):
    verify_csrf_token(request, csrf_token)

    with get_db_context() as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                "DELETE FROM user_permissions WHERE user_id = %s AND permission_id = %s",
                (user_id, permission_id)
            )
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