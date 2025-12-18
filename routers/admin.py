from fastapi import APIRouter, Request, Depends, HTTPException, Form
from postgresql import get_db_context
from security.csrf import generate_csrf_token, verify_csrf_token
from fastapi.responses import HTMLResponse, RedirectResponse
from security.session import set_cache_headers,get_current_user
from psycopg2.extras import RealDictCursor
from security.hash import hash_password
# استيراد الخدمات والراوترات
from core.templates import templates
from services.analytics import get_logged_in_users_history ,get_activity_logs_paginated
from services.notification import send_notification
import html
import re

# === ثوابت التحقق ===
VALID_USERNAME_REGEX = r"^[a-zA-Z0-9_\-\u0600-\u06FF]{2,30}$" 
PASSWORD_MIN_LENGTH = 4

router = APIRouter(prefix="/admin", tags=["admin"])

@router.get("/", response_class=HTMLResponse)
async def admin_page(request: Request, page: int = 1):
    login_history = get_logged_in_users_history(limit=50)
    usr = request.session.get("user")
    user = get_current_user(request)
    if not user or user.get("role") != "admin":
        return RedirectResponse("/auth/login", status_code=303)
    
    csrf_token = generate_csrf_token()
    request.session["csrf_token"] = csrf_token
     
    # === استخراج رسائل Flash Messages من الجلسة ===
    error_message = request.session.pop("error_message", None)
    success_message = request.session.pop("success_message", None)
    
    with get_db_context() as conn:
        with conn.cursor() as cursor:
            users_per_page = 10
            offset = (page - 1) * users_per_page
            # جلب المستخدمين
            cursor.execute("SELECT id, username, role FROM users LIMIT %s OFFSET %s", (users_per_page, offset))
            users = cursor.fetchall()
            
            # إخفاء حساب "admin" إذا لم يكن المستخدم الحالي هو "admin"
            if user["username"] != "admin":
                users = [u for u in users if u[1] != "admin"]
            
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
            
            # حساب الصفحات
            cursor.execute("SELECT COUNT(*) FROM users")
            total_users = cursor.fetchone()[0]
            total_pages = (total_users + users_per_page - 1) // users_per_page

    response = templates.TemplateResponse("/admin/admin.html", {
        "request": request,
        "csrf_token": csrf_token,
        "users": users,
        "user": usr,
        "permissions": permissions,
        "user_permissions": user_permissions,
        "current_page": page,
        "total_pages": total_pages,
        "login_history": login_history,
        "error_message": error_message,     # تم تمرير رسالة الخطأ
        "success_message": success_message   # تم تمرير رسالة النجاح
    })
    set_cache_headers(response)
    return response

@router.get("/permissions")
async def permissions_page(request: Request):
    user = get_current_user(request)
    if not user or user.get("role") != "admin":
        return RedirectResponse("/auth/login")

    with get_db_context() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("SELECT * FROM permissions")
            perms = cur.fetchall()
            cur.execute("""
                SELECT up.*, u.username, p.name 
                FROM user_permissions up
                JOIN users u ON up.user_id = u.id
                JOIN permissions p ON up.permission_id = p.id
            """)
            assignments = cur.fetchall()

    return templates.TemplateResponse("admin/permissions.html", {
        "request": request, 
        "user": user, 
        "perms": perms, 
        "assignments": assignments
    })

# تم حذف دالة GET /admin/add_user لأن النموذج موجود ضمن admin.html

@router.post("/add_user")
async def add_user(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    role: str = Form(...),
    current_page: int = Form(1), # رقم الصفحة للعودة إليها
    csrf_token: str = Form(...)
):
    verify_csrf_token(request, csrf_token)
    
    username_stripped = username.strip()
    error = None

    # التحقق من المدخلات
    if not re.fullmatch(VALID_USERNAME_REGEX, username_stripped):
        error = "اسم المستخدم غير صالح. يجب أن يحتوي على 2-30 حرفاً أو رقماً أو (_) أو (-)."
    elif len(password) < PASSWORD_MIN_LENGTH:
        error = f"كلمة المرور يجب ألا تقل عن {PASSWORD_MIN_LENGTH} أحرف."
    elif role == "admin":
         error = "غير مسموح بإضافة مستخدم بدور إدمن. هذا الدور محجوز للإدارة العليا فقط."

    if error:
        # في حال وجود خطأ، نخزنه ونعيد التوجيه
        request.session["error_message"] = error
        return RedirectResponse(f"/admin?page={current_page}", status_code=303)
        
    username_safe = html.escape(username_stripped)
    role_safe = html.escape(role)
    
    try:
        with get_db_context() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT id FROM users WHERE username = %s", (username_safe,))
                if cur.fetchone():
                    request.session["error_message"] = "المستخدم موجود بالفعل"
                    return RedirectResponse(f"/admin?page={current_page}", status_code=303) 
                
                cur.execute(
                    "INSERT INTO users (username, password, role) VALUES (%s, %s, %s)",
                    (username_safe, hash_password(password), role_safe)
                )
                conn.commit()
        
        request.session["success_message"] = f"تم إضافة المستخدم {username_safe} بنجاح."
        # إعادة التوجيه إلى نفس الصفحة بعد الإضافة
        return RedirectResponse(f"/admin?page={current_page}", status_code=303)
    except Exception as e:
        # في حال وجود خطأ في قاعدة البيانات، نخزنه ونعيد التوجيه
        request.session["error_message"] = f"حدث خطأ في قاعدة البيانات أثناء الإضافة: {str(e)}"
        return RedirectResponse(f"/admin?page={current_page}", status_code=303)
    

  # دالة لتغيير كلمة مرور مستخدم

# تعديل مستخدم
@router.post("/edit_user")
async def edit_user(
    request: Request, 
    user_id: int = Form(...), 
    username: str = Form(...), 
    role: str = Form(...), 
    current_page: int = Form(1), # تم الإضافة
    csrf_token: str = Form(...)
):
    verify_csrf_token(request, csrf_token)
    
    username_stripped = username.strip()
    error = None

    # التحقق من المدخلات
    if not re.fullmatch(VALID_USERNAME_REGEX, username_stripped):
        error = "اسم المستخدم غير صالح. يجب أن يحتوي على 3-30 حرفاً  أو رقماً أو (_) أو (-)."
    elif role == "admin":
        error = "غير مسموح بتعيين دور إدمن عبر هذه الواجهة."

    if error:
        request.session["error_message"] = error
        return RedirectResponse(f"/admin?page={current_page}", status_code=303)

    username_safe = html.escape(username_stripped)
    role_safe = html.escape(role)

    try:
        with get_db_context() as conn:
            with conn.cursor() as cur:
                # التحقق من وجود المستخدم وجلب اسمه القديم
                cur.execute("SELECT id, username FROM users WHERE id = %s", (user_id,))
                user_record = cur.fetchone()
                if not user_record:
                    request.session["error_message"] = "المستخدم غير موجود"
                    return RedirectResponse(f"/admin?page={current_page}", status_code=303)
                
                old_username = user_record[1]


                cur.execute("UPDATE users SET username = %s, role = %s WHERE id = %s", 
                            (username_safe, role_safe, user_id))
                conn.commit()

                request.session["success_message"] = f"تم تعديل المستخدم ({old_username}) بنجاح."
                # إعادة توجيه إلى نفس الصفحة بعد التحديث
                return RedirectResponse(url=f"/admin?page={current_page}", status_code=303)  
    except Exception as e:
        request.session["error_message"] = f"فشل في تعديل المستخدم: {str(e)}"
        return RedirectResponse(url=f"/admin?page={current_page}", status_code=303)

# حذف مستخدم
@router.post("/delete_user")
async def delete_user(
    request: Request, 
    user_id: int = Form(...), 
    current_page: int = Form(1), # تم الإضافة
    csrf_token: str = Form(...)
):
    verify_csrf_token(request, csrf_token)

    try:
        with get_db_context() as conn:
            with conn.cursor() as cur:
                # محاولة جلب اسم المستخدم قبل الحذف لرسالة النجاح
                cur.execute("SELECT username FROM users WHERE id = %s", (user_id,))
                user_record = cur.fetchone()

                cur.execute("DELETE FROM users WHERE id = %s", (user_id,))
                conn.commit()
                
                username_to_delete = user_record[0] if user_record else "مستخدم مجهول"
                request.session["success_message"] = f"تم حذف المستخدم ({username_to_delete}) بنجاح."

                # إعادة توجيه إلى نفس الصفحة بعد التحديث
                return RedirectResponse(url=f"/admin?page={current_page}", status_code=303)  
    except Exception as e:
        request.session["error_message"] = f"فشل في حذف المستخدم: {str(e)}"
        return RedirectResponse(url=f"/admin?page={current_page}", status_code=303)

@router.post("/change_password")
async def change_password(
    request: Request, 
    user_id: int = Form(...), 
    new_password: str = Form(...), 
    current_page: int = Form(1), # تم الإضافة
    csrf_token: str = Form(...)
):
    # التحقق من رمز CSRF
    verify_csrf_token(request, csrf_token)
    
    # التحقق من صلاحيات المستخدم (الحفاظ على الكود الأصلي)
    user = get_current_user(request)
    if not user or user.get("role") != "admin": # تم تعديل التحقق ليكون صحيحًا
        request.session["error_message"] = "أنت بحاجة إلى صلاحيات إدارية للوصول إلى هذه الصفحة"
        return RedirectResponse(url=f"/admin?page={current_page}", status_code=303)
    
    # التحقق من طول كلمة المرور
    if len(new_password) < PASSWORD_MIN_LENGTH:
        request.session["error_message"] = f"كلمة المرور يجب ألا تقل عن {PASSWORD_MIN_LENGTH} أحرف."
        return RedirectResponse(url=f"/admin?page={current_page}", status_code=303)
        
    # تشفير كلمة المرور الجديدة
    hashed_password = hash_password(new_password)

    # تحديث كلمة المرور في قاعدة البيانات
    try:
        with get_db_context() as conn:
            with conn.cursor() as cur:
                # التحقق من وجود المستخدم وجلب اسمه
                cur.execute("SELECT username FROM users WHERE id = %s", (user_id,))
                user_record = cur.fetchone()
                if not user_record:
                    request.session["error_message"] = "المستخدم غير موجود"
                    return RedirectResponse(url=f"/admin?page={current_page}", status_code=303)

                username_to_update = user_record[0]

                # تحديث كلمة المرور
                cur.execute("UPDATE users SET password = %s WHERE id = %s", (hashed_password, user_id))
                conn.commit()

                request.session["success_message"] = f"تم تغيير كلمة مرور المستخدم ({username_to_update}) بنجاح."
                # إعادة توجيه إلى نفس الصفحة بعد التحديث
                return RedirectResponse(url=f"/admin?page={current_page}", status_code=303)  
    except Exception as e:
        request.session["error_message"] = f"فشل في تغيير كلمة المرور: {str(e)}"
        return RedirectResponse(url=f"/admin?page={current_page}", status_code=303)

# منح صلاحية لمستخدم
@router.post("/give_permission")
async def give_permission(
    request: Request, 
    user_id: int = Form(...), 
    permission_id: int = Form(...), 
    current_page: int = Form(1), # تم الإضافة
    csrf_token: str = Form(...)
):
    verify_csrf_token(request, csrf_token)

    try:
        with get_db_context() as conn:
            with conn.cursor() as cur:
                cur.execute("INSERT INTO user_permissions (user_id, permission_id) VALUES (%s, %s)", 
                            (user_id, permission_id))
                conn.commit()
                
                request.session["success_message"] = "تم منح الصلاحية بنجاح."

                # إعادة توجيه إلى نفس الصفحة بعد التحديث
                return RedirectResponse(url=f"/admin?page={current_page}", status_code=303)  
    except Exception as e:
        # منع خطأ تكرار المفتاح الأساسي (عادة ما يكون خطأ 23505 في PostgreSQL)
        error_detail = f"فشل في منح الصلاحية: {str(e)}"
        if "duplicate key value violates unique constraint" in str(e):
             error_detail = "الصلاحية ممنوحة لهذا المستخدم بالفعل."
             
        request.session["error_message"] = error_detail
        return RedirectResponse(url=f"/admin?page={current_page}", status_code=303)
    
# إزالة صلاحية من مستخدم
@router.post("/remove_permission")
async def remove_permission(
    request: Request, 
    user_id: int = Form(...), 
    permission_id: int = Form(...), 
    current_page: int = Form(1), # تم الإضافة
    csrf_token: str = Form(...)
):
    verify_csrf_token(request, csrf_token)

    try:
        with get_db_context() as conn:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM user_permissions WHERE user_id = %s AND permission_id = %s", 
                            (user_id, permission_id))
                conn.commit()
                
                request.session["success_message"] = "تم إزالة الصلاحية بنجاح."

                # إعادة توجيه إلى نفس الصفحة بعد التحديث
                return RedirectResponse(url=f"/admin?page={current_page}", status_code=303)  
    except Exception as e:
        request.session["error_message"] = f"فشل في إزالة الصلاحية: {str(e)}"
        return RedirectResponse(url=f"/admin?page={current_page}", status_code=303)
    

@router.get("/logs")
async def view_all_activity_logs(request: Request, page: int = 1):
    user = request.session.get("user")
    # التأكد من رتبة الإدمن (كما في الصورة)
    if not user or user.get("role") != "admin":
         return RedirectResponse(url="/403", status_code=303)
    
   
    logs, total_pages = get_activity_logs_paginated(page=page, per_page=30)
    
    response = templates.TemplateResponse("admin/logs.html", {
        "request": request,
        "logs": logs,
        "current_page": page,
        "total_pages": total_pages,
        "user": user
    })
    set_cache_headers(response)
    return response