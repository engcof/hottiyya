from fastapi import FastAPI, Request, Form, Depends, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware
import sqlite3, bcrypt

# --------------------------
# إعداد FastAPI
# --------------------------
app = FastAPI()
templates = Jinja2Templates(directory="templates")
app.mount("/static", StaticFiles(directory="static"), name="static")
app.add_middleware(SessionMiddleware, secret_key="SUPER_SECRET_KEY_1234567890")

DB_PATH = "database/family_tree.db"

# --------------------------
# دوال مساعدة
# --------------------------
def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def hash_password(password):
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")

def check_password(password, hashed):
    return bcrypt.checkpw(password.encode("utf-8"), hashed.encode("utf-8"))

# --------------------------
# جلسة المستخدم
# --------------------------
def get_current_user(request: Request):
    username = request.session.get("username")
    role = request.session.get("role")
    if not username:
        raise HTTPException(status_code=401, detail="غير مسجل دخول")
    return {"username": username, "role": role}

def require_permission(permission_name: str):
    def dependency(request: Request, user=Depends(get_current_user)):
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT 1
            FROM users u
            JOIN user_permissions up ON u.id = up.user_id
            JOIN permissions p ON p.id = up.permission_id
            WHERE u.username = ? AND p.name = ?
        """, (user["username"], permission_name))
        if not cursor.fetchone():
            raise HTTPException(status_code=403, detail="لا تملك الصلاحية المطلوبة")
        return True
    return dependency

def no_cache(response):
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    return response

# --------------------------
# الصفحات العامة
# --------------------------
@app.get("/", response_class=HTMLResponse)
def home(request: Request):
    username = request.session.get("username")
    role = request.session.get("role")
    response = templates.TemplateResponse("home.html", {"request": request, "username": username, "role": role})
    return no_cache(response)

@app.get("/login", response_class=HTMLResponse)
def login_form(request: Request):
    message = request.session.pop("message", "")
    response = templates.TemplateResponse("login.html", {"request": request, "message": message})
    return no_cache(response)

@app.post("/login")
def login_post(request: Request, username: str = Form(...), password: str = Form(...)):
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT * FROM users WHERE username = ?", (username,))
    user = cur.fetchone()
    conn.close()

    if not user:
        request.session["message"] = "اسم المستخدم غير صحيح ❌"
        return RedirectResponse("/login", status_code=303)

    if not check_password(password, user["password"]):
        request.session["message"] = "كلمة المرور غير صحيحة ❌"
        return RedirectResponse("/login", status_code=303)

    request.session["username"] = username
    request.session["role"] = user["role"]
    request.session["message"] = "تم تسجيل الدخول بنجاح ✅"
    return RedirectResponse("/", status_code=303)

@app.get("/logout")
def logout(request: Request):
    request.session.clear()
    return RedirectResponse("/login", status_code=303)

# --------------------------
# إدارة المستخدمين (الأدمن فقط)
# --------------------------
@app.get("/admin/", response_class=HTMLResponse)
def admin_users(request: Request, user=Depends(get_current_user)):
    if user["role"] != "admin":
        return RedirectResponse("/", status_code=303)
    
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT * FROM users")
    users = cur.fetchall()

    cur.execute("SELECT * FROM permissions")
    permissions = cur.fetchall()
    conn.close()

    response = templates.TemplateResponse("admin.html", {
        "request": request,
        "username": user["username"],
        "users": users,
        "permissions": permissions
    })
    return no_cache(response)

@app.post("/admin/users/add")
def add_user(request: Request, username: str = Form(...), password: str = Form(...)):
    conn = get_db()
    cur = conn.cursor()
    try:
        hashed_pw = hash_password(password)
        cur.execute("INSERT INTO users (username, password, role) VALUES (?, ?, ?)", (username, hashed_pw, "user"))
        conn.commit()
    except Exception as e:
        conn.close()
        raise HTTPException(status_code=400, detail=f"حدث خطأ: {e}")
    conn.close()
    return RedirectResponse("/admin/users", status_code=303)

@app.post("/admin/users/delete")
def delete_user(user_id: int = Form(...)):
    conn = get_db()
    cur = conn.cursor()
    cur.execute("DELETE FROM users WHERE id = ?", (user_id,))
    conn.commit()
    conn.close()
    return RedirectResponse("/admin/users", status_code=303)






#uvicorn main:app --reload