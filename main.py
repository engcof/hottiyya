import os
import logging
import bcrypt
import shutil
import psycopg2
import secrets
from typing import Optional
from dotenv import load_dotenv
from datetime import timedelta
from fastapi import UploadFile, File
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
DB_HOST = os.getenv("DB_HOST")
DB_NAME = os.getenv("DB_NAME")
DB_USER = os.getenv("DB_USER")
DB_PASSWORD = os.getenv("DB_PASSWORD")

if not SECRET_KEY:
    raise RuntimeError("SECRET_KEY or DB_PATH not set in .env file")

# إعداد الـ logger
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("app.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# =========================================
# إعداد FastAPI
# =========================================
app = FastAPI()
templates = Jinja2Templates(directory="templates")

app.add_middleware(
    SessionMiddleware,
    secret_key=SECRET_KEY,
    session_cookie="session",
    max_age=int(timedelta(hours=1).total_seconds())
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://render.com"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/static", StaticFiles(directory="static"), name="static")

UPLOAD_DIR = os.path.join("static", "uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)

# =========================================
# دوال مساعدة
# =========================================
@contextmanager
def get_db_context():
    conn = None
    try:
        host = os.getenv("DB_HOST")
        dbname = os.getenv("DB_NAME")
        user = os.getenv("DB_USER")
        password = os.getenv("DB_PASSWORD")
        if not all([host, dbname, user, password]):
            raise ValueError("متغيرات قاعدة البيانات مفقودة!")
        logger.info(f"الاتصال بقاعدة البيانات: {user}@{host}/{dbname}")
        conn = psycopg2.connect(
            host=host,
            dbname=dbname,
            user=user,
            password=password,
            port="5432",
            sslmode="require"
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

def get_db():
    with get_db_context() as conn:
        yield conn

def get_current_user(request: Request):
    username = request.session.get("username")
    role = request.session.get("role")
    if not username:
        raise HTTPException(status_code=401, detail="غير مسجل دخول")
    return {"username": username, "role": role}

def get_full_name(code: str) -> str:
    """إرجاع الاسم الكامل: الأب، الجد، ...، الابن"""
    with get_db_context() as conn:
        with conn.cursor() as cursor:
            cursor.execute("SELECT name, f_code FROM family_name WHERE code=%s", (code,))
            result = cursor.fetchone()
            if not result:
                return ""
            name, father_code = result
            names = [name]
            while father_code:
                cursor.execute("SELECT name, f_code FROM family_name WHERE code=%s", (father_code,))
                row = cursor.fetchone()
                if not row:
                    break
                fname, father_code = row
                names.append(fname)
            return " ".join((names))

def check_password(password, hashed):
    return bcrypt.checkpw(password.encode('utf-8'), hashed.encode('utf-8'))

def hash_password(password: str) -> str:
    hashed = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt())
    return hashed.decode('utf-8')

def get_user(condition: str, param: tuple):
    with get_db_context() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cursor:
            cursor.execute(f"SELECT * FROM users WHERE {condition}", param)
            return cursor.fetchone()

def generate_csrf_token():
    return secrets.token_urlsafe(32)

def verify_csrf_token(request: Request, csrf_token: str):
    session_token = request.session.get("csrf_token")
    if not csrf_token or csrf_token != session_token:
        raise HTTPException(status_code=403, detail="رمز CSRF غير صالح أو مفقود")

def set_cache_headers(response: HTMLResponse):
    response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, proxy-revalidate'
    response.headers['Pragma'] = 'no-cache'
    response.headers['Expires'] = '0'
    return response

# =========================================
# الصفحة الرئيسية
# =========================================
@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    user = request.session.get("user")
    response = templates.TemplateResponse("index.html", {"request": request, "user": user})
    set_cache_headers(response)
    return response

# =========================================
# تسجيل الدخول والخروج
# =========================================
@app.get("/login", response_class=HTMLResponse)
async def login(request: Request):
    csrf_token = generate_csrf_token()
    request.session["csrf_token"] = csrf_token
    response = templates.TemplateResponse("login.html", {"request": request, "csrf_token": csrf_token})
    set_cache_headers(response)
    return response

@app.post("/login")
async def login_post(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    csrf_token: str = Form(...),
    db=Depends(get_db)
):
    verify_csrf_token(request, csrf_token)
    user_data = get_user("username = %s", (username,))
    if user_data and check_password(password, user_data["password"]):
        request.session["user"] = username
        request.session["username"] = username
        request.session["role"] = user_data["role"]
        request.session["message"] = "تم تسجيل الدخول بنجاح"
        return RedirectResponse(url="/", status_code=303)
    raise HTTPException(status_code=401, detail="اسم المستخدم أو كلمة المرور غير صحيحة")

@app.get("/logout")
async def logout(request: Request):
    request.session.clear()
    response = RedirectResponse(url="/", status_code=303)
    set_cache_headers(response)
    return response

# =========================================
# إدارة المستخدمين
# =========================================
@app.get("/admin")
async def admin(request: Request, page: int = 1, user=Depends(get_current_user)):
    if user.get("role") != "admin":
        return RedirectResponse("/", status_code=303)

    csrf_token = generate_csrf_token()
    request.session["csrf_token"] = csrf_token

    with get_db_context() as conn:
        with conn.cursor() as cursor:
            users_per_page = 10
            offset = (page - 1) * users_per_page
            
            cursor.execute("SELECT id, username, role FROM users LIMIT %s OFFSET %s", (users_per_page, offset))
            users = cursor.fetchall()

            if user["username"] != "admin":
                users = [u for u in users if u[1] != "admin"]

            cursor.execute("SELECT id, name, category FROM permissions")
            permissions = cursor.fetchall()

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
            cursor.execute("INSERT INTO users (username, password, role) VALUES (%s, %s, %s)",
                           (username, hash_password(password), role))
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
    if request.session.get("user") != "admin":
        raise HTTPException(status_code=403, detail="أنت بحاجة إلى صلاحيات إدارية")
    hashed = hash_password(new_password)
    with get_db_context() as conn:
        with conn.cursor() as cursor:
            cursor.execute("SELECT id FROM users WHERE id = %s", (user_id,))
            if not cursor.fetchone():
                raise HTTPException(status_code=404, detail="المستخدم غير موجود")
            cursor.execute("UPDATE users SET password = %s WHERE id = %s", (hashed, user_id))
            conn.commit()
    return RedirectResponse(url="/admin", status_code=303)

@app.post("/admin/give_permission")
async def give_permission(request: Request, user_id: int = Form(...), permission_id: int = Form(...), csrf_token: str = Form(...)):
    verify_csrf_token(request, csrf_token)
    with get_db_context() as conn:
        with conn.cursor() as cursor:
            cursor.execute("INSERT INTO user_permissions (user_id, permission_id) VALUES (%s, %s) ON CONFLICT DO NOTHING",
                           (user_id, permission_id))
            conn.commit()
    return RedirectResponse(url="/admin", status_code=303)

@app.post("/admin/remove_permission")
async def remove_permission(request: Request, user_id: int = Form(...), permission_id: int = Form(...), csrf_token: str = Form(...)):
    verify_csrf_token(request, csrf_token)
    with get_db_context() as conn:
        with conn.cursor() as cursor:
            cursor.execute("DELETE FROM user_permissions WHERE user_id = %s AND permission_id = %s",
                           (user_id, permission_id))
            conn.commit()
    return RedirectResponse(url="/admin", status_code=303)

# =========================================
# إدارة الأسماء
# =========================================
@app.get("/names", response_class=HTMLResponse)
async def show_names(request: Request, user=Depends(get_current_user)):
    with get_db_context() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("SELECT code FROM family_name ORDER BY code")
            members = cur.fetchall()

            members_list = []
            for m in members:
                code = m["code"]
                full_name = get_full_name(code)
                members_list.append({"code": code, "full_name": full_name})

    response = templates.TemplateResponse("names.html", {
        "request": request,
        "username": user["username"],
        "role": user["role"],
        "members": members_list
    })
    set_cache_headers(response)
    return response

# إضافة عضو
@app.get("/names/add", response_class=HTMLResponse)
async def add_name_form(request: Request, user=Depends(get_current_user)):
    return templates.TemplateResponse("add_name.html", {"request": request, "username": user["username"], "error": None})

@app.post("/names/add")
async def add_name(
    request: Request,
    code: str = Form(...),
    name: str = Form(...),
    f_code: str = Form(None),
    m_code: str = Form(None),
    w_code: str = Form(None),
    h_code: str = Form(None),
    type: str = Form(None),
    level: int = Form(None),
    gender: str = Form(None),
    d_o_b: str = Form(None),
    d_o_d: str = Form(None),
    email: str = Form(None),
    phone: str = Form(None),
    address: str = Form(None),
    p_o_b: str = Form(None),
    picture: UploadFile = File(None),
    user=Depends(get_current_user)
):
    error = None
    # تنظيف البيانات
    code = code.strip()
    name = name.strip()
    
    # تحويل السلاسل الفارغة إلى None
    f_code = f_code.strip() if f_code and f_code.strip() else None
    m_code = m_code.strip() if m_code and m_code.strip() else None
    w_code = w_code.strip() if w_code and w_code.strip() else None
    h_code = h_code.strip() if h_code and h_code.strip() else None
    type = type.strip() if type and type.strip() else None
    gender = gender.strip() if gender and gender.strip() else None
    d_o_b = d_o_b.strip() if d_o_b and d_o_b.strip() else None
    d_o_d = d_o_d.strip() if d_o_d and d_o_d.strip() else None
    email = email.strip() if email and email.strip() else None
    phone = phone.strip() if phone and phone.strip() else None
    address = address.strip() if address and address.strip() else None
    p_o_b = p_o_b.strip() if p_o_b and p_o_b.strip() else None

    # التحقق من صحة البيانات الأساسية
    if not code or not name:
        error = "الكود والاسم مطلوبان!"
        return templates.TemplateResponse("add_name.html", {
            "request": request, 
            "username": user["username"]  
        })

    try:
        with get_db_context() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT code FROM family_name WHERE code = %s", (code,))
                if cur.fetchone():
                    error = "الكود مستخدم مسبقاً! اختر كوداً آخر."
                if not error:
                    cur.execute("""
                        INSERT INTO family_name (code, name, f_code, m_code, w_code, h_code, type, level)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                    """, (code, name, f_code, m_code, w_code, h_code, type, level))

                    cur.execute("""
                        INSERT INTO family_info (code_info, gender, d_o_b, d_o_d, email, phone, address, p_o_b)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                    """, (code, gender, d_o_b, d_o_d, email, phone, address, p_o_b))

                    if picture and picture.filename:
                        pic_path = os.path.join(UPLOAD_DIR, picture.filename)
                        with open(pic_path, "wb") as buffer:
                            shutil.copyfileobj(picture.file, buffer)
                        cur.execute("INSERT INTO family_picture (code_pic, pic_path) VALUES (%s, %s)", (code, pic_path))

                    conn.commit()
                    return RedirectResponse("/names", status_code=303)
    except Exception as e:
        logger.error(f"خطأ غير متوقع عند إضافة عضو: {e}")
        error = "حدث خطأ غير متوقع. حاول مرة أخرى."            
  

# تفاصيل العضو
@app.get("/names/details/{code}", response_class=HTMLResponse)
async def name_details(request: Request, code: str, user=Depends(get_current_user)):
    with get_db_context() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("SELECT * FROM family_name WHERE code = %s", (code,))
            member = cur.fetchone()
            if not member:
                raise HTTPException(status_code=404, detail="العضو غير موجود")

            cur.execute("SELECT * FROM family_info WHERE code_info = %s", (code,))
            info = cur.fetchone() or {}

            cur.execute("SELECT pic_path FROM family_picture WHERE code_pic = %s", (code,))
            pic = cur.fetchone()
            picture_url = pic["pic_path"] if pic else None

            gender = info.get("gender")
            if not gender and member.get("type"):
                t = member["type"]
                if "ابن" in t or "زوج" in t:
                    gender = "ذكر"
                elif "ابنة" in t or "زوجة" in t:
                    gender = "أنثى"

            full_name = get_full_name(code)
            mother_full_name = get_full_name(member["m_code"]) if member.get("m_code") else ""

            wives = []
            if gender == "ذكر":
                cur.execute("SELECT code FROM family_name WHERE h_code = %s", (code,))
                for w in cur.fetchall():
                    wives.append({"code": w["code"], "name": get_full_name(w["code"])})

            husbands = []
            if gender == "أنثى":
                cur.execute("SELECT code FROM family_name WHERE w_code = %s", (code,))
                for h in cur.fetchall():
                    husbands.append({"code": h["code"], "name": get_full_name(h["code"])})

            cur.execute("SELECT code FROM family_name WHERE f_code = %s OR m_code = %s", (code, code))
            children = [{"code": c["code"], "name": get_full_name(c["code"])} for c in cur.fetchall()]

    return templates.TemplateResponse("details.html", {
        "request": request,
        "username": user["username"],
        "member": member,
        "info": info,
        "picture_url": picture_url,
        "full_name": full_name,
        "mother_full_name": mother_full_name,
        "wives": wives,
        "husbands": husbands,
        "children": children,
        "gender": gender
    })

# تعديل عضو
@app.get("/names/edit/{code}", response_class=HTMLResponse)
async def edit_name_form(request: Request, code: str, user=Depends(get_current_user)):
    with get_db_context() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("SELECT * FROM family_name WHERE code=%s", (code,))
            member = cur.fetchone()
            cur.execute("SELECT * FROM family_info WHERE code_info=%s", (code,))
            info = cur.fetchone() or {}
    if not member:
        raise HTTPException(status_code=404, detail="العضو غير موجود")
    return templates.TemplateResponse("edit_name.html", {
        "request": request,
        "member": member,
        "info": info,
        "username": user["username"]
    })

@app.post("/names/edit/{code}")
async def edit_name(
    request: Request,
    code: str,
    name: str = Form(...),
    f_code: str = Form(None),
    m_code: str = Form(None),
    w_code: str = Form(None),
    h_code: str = Form(None),
    type: str = Form(None),
    level: int = Form(None),
    gender: str = Form(None),
    d_o_b: str = Form(None),
    d_o_d: str = Form(None),
    email: str = Form(None),
    phone: str = Form(None),
    address: str = Form(None),
    p_o_b: str = Form(None),
    picture: UploadFile = File(None)
):
    
    
    with get_db_context() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                UPDATE family_name SET name=%s, f_code=%s, m_code=%s, w_code=%s, h_code=%s, type=%s, level=%s
                WHERE code=%s
            """, (name, f_code, m_code, w_code, h_code, type, level, code))

            cur.execute("""
                UPDATE family_info SET gender=%s, d_o_b=%s, d_o_d=%s, email=%s, phone=%s, address=%s, p_o_b=%s
                WHERE code_info=%s
            """, (gender, d_o_b, d_o_d, email, phone, address, p_o_b, code))

            if picture and picture.filename:
                # حذف الصورة القديمة
                cur.execute("SELECT pic_path FROM family_picture WHERE code_pic=%s", (code,))
                old = cur.fetchone()
                if old and old["pic_path"] and os.path.exists(old["pic_path"]):
                    os.remove(old["pic_path"])

                pic_path = os.path.join(UPLOAD_DIR, picture.filename)
                with open(pic_path, "wb") as buffer:
                    shutil.copyfileobj(picture.file, buffer)
                cur.execute("""
                    INSERT INTO family_picture (code_pic, pic_path) VALUES (%s, %s)
                    ON CONFLICT (code_pic) DO UPDATE SET pic_path=%s
                """, (code, pic_path, pic_path))

            conn.commit()
    return RedirectResponse(f"/names/details/{code}", status_code=303)

# حذف عضو
@app.post("/names/delete")
async def delete_name(code: str = Form(...), user=Depends(get_current_user)):
    with get_db_context() as conn:
        with conn.cursor() as cur:
            # حذف الصورة من القرص
            cur.execute("SELECT pic_path FROM family_picture WHERE code_pic = %s", (code,))
            pic = cur.fetchone()
            if pic and pic["pic_path"] and os.path.exists(pic["pic_path"]):
                os.remove(pic["pic_path"])

            cur.execute("DELETE FROM family_picture WHERE code_pic = %s", (code,))
            cur.execute("DELETE FROM family_info WHERE code_info = %s", (code,))
            cur.execute("DELETE FROM family_name WHERE code = %s", (code,))
            conn.commit()
    return RedirectResponse("/names", status_code=303)

# =========================================
# صفحات إضافية
# =========================================
@app.get("/404")
async def not_found(request: Request):
    return {"message": "الصفحة غير موجودة"}

@app.get("/session_test")
async def session_test(request: Request):
    user = request.session.get("user")
    print("Session user:", user)
    return {"session_user": user}


#uvicorn main:app --reload