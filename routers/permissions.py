from fastapi import APIRouter, Request, Depends, HTTPException, Form
from postgresql import get_db_context
from services.auth_service import get_current_user
from security.csrf import generate_csrf_token, verify_csrf_token
from fastapi.responses import HTMLResponse, RedirectResponse
from security.session import set_cache_headers
from psycopg2.extras import RealDictCursor
from core.templates import templates
import html # تم إضافة هذه المكتبة لتنقية المدخلات (Sanitization)

router = APIRouter(prefix="/permissions", tags=["permissions"])

@router.get("/", response_class=HTMLResponse)
async def permissions_page(request: Request, page: int = 1):
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
            # جلب الصلاحيات مع الترقيم
            perms_per_page = 10
            offset = (page - 1) * perms_per_page
            cursor.execute("""
                SELECT id, name, category 
                FROM permissions 
                ORDER BY name 
                LIMIT %s OFFSET %s
            """, (perms_per_page, offset))
            perms = cursor.fetchall()

            # جلب المستخدمين وتعيينات الصلاحيات
            cursor.execute("SELECT id, username, role FROM users")
            users = cursor.fetchall()
            cursor.execute("""
                    SELECT up.*, u.username, p.name 
                    FROM user_permissions up
                    JOIN users u ON up.user_id = u.id
                    JOIN permissions p ON up.permission_id = p.id
                """)
            assignments = cursor.fetchall()    
            
            # حساب الصفحات
            cursor.execute("SELECT COUNT(*) FROM permissions")
            total_perms = cursor.fetchone()[0]
            total_pages = (total_perms + perms_per_page - 1) // perms_per_page

    with get_db_context() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cursor:   
            # جلب كل الصلاحيات (للقائمة المنسدلة في التعديل)
            cursor.execute("SELECT id, name, category FROM permissions ORDER BY name")
            all_permissions = cursor.fetchall()

    response = templates.TemplateResponse("/permissions/permissions.html", {
        "request": request,
        "csrf_token": csrf_token,
        "users": users,
        "user": usr,
        "perms": perms,
        "all_permissions": all_permissions,
        "assignments": assignments,
        "current_page": page,
        "total_pages": total_pages,
        "error_message": error_message,     # تم تمرير رسالة الخطأ
        "success_message": success_message   # تم تمرير رسالة النجاح
    })
    set_cache_headers(response)
    return response

@router.post("/add_permission")
async def add_permission(
    request: Request,
    name: str = Form(...),
    category: str = Form(...),
    current_page: int = Form(1),
    csrf_token: str = Form(...)
):
    verify_csrf_token(request, csrf_token)
    
    name_safe = html.escape(name.strip())
    category_safe = html.escape(category.strip())
    
    if not name_safe or not category_safe:
        request.session["error_message"] = "يجب إدخال اسم وفئة الصلاحية."
        return RedirectResponse(f"/permissions?page={current_page}", status_code=303)

    try:
        with get_db_context() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT id FROM permissions WHERE name = %s", (name_safe,))
                if cur.fetchone():
                    request.session["error_message"] = f"الصلاحية **{name_safe}** موجودة بالفعل."
                    return RedirectResponse(f"/permissions?page={current_page}", status_code=303)
                    
                cur.execute(
                    "INSERT INTO permissions (name, category) VALUES (%s, %s)",
                    (name_safe, category_safe)
                )
                conn.commit()
                
        request.session["success_message"] = f"تم إضافة الصلاحية **{name_safe}** بنجاح."
        return RedirectResponse(f"/permissions?page={current_page}", status_code=303)
        
    except Exception as e:
        request.session["error_message"] = f"حدث خطأ في قاعدة البيانات أثناء إضافة الصلاحية: {str(e)}"
        return RedirectResponse(f"/permissions?page={current_page}", status_code=303)
    

@router.post("/edit_permission")
async def edit_permission(
    request: Request, 
    perm_id: int = Form(...), 
    name: str = Form(...), 
    category: str = Form(...), 
    current_page: int = Form(1),
    csrf_token: str = Form(...)
):
    verify_csrf_token(request, csrf_token)
    
    name_safe = html.escape(name.strip())
    category_safe = html.escape(category.strip())
    
    if not name_safe or not category_safe:
        request.session["error_message"] = "يجب إدخال اسم وفئة الصلاحية."
        return RedirectResponse(f"/permissions?page={current_page}", status_code=303)

    try:
        with get_db_context() as conn:
            with conn.cursor() as cur:
                # التحقق من وجود الصلاحية وجلب اسمها القديم
                cur.execute("SELECT name FROM permissions WHERE id = %s", (perm_id,))
                perm_record = cur.fetchone()
                if not perm_record:
                    request.session["error_message"] = "الصلاحية المراد تعديلها غير موجودة."
                    return RedirectResponse(f"/permissions?page={current_page}", status_code=303)
                
                old_name = perm_record[0]

                # التحقق من تكرار اسم الصلاحية الجديد
                if old_name != name_safe:
                    cur.execute("SELECT id FROM permissions WHERE name = %s", (name_safe,))
                    if cur.fetchone():
                        request.session["error_message"] = f"الصلاحية بالاسم **{name_safe}** موجودة بالفعل. اختر اسماً آخر."
                        return RedirectResponse(f"/permissions?page={current_page}", status_code=303)

                cur.execute("UPDATE permissions SET name = %s, category = %s WHERE id = %s", 
                            (name_safe, category_safe, perm_id))
                conn.commit()

                request.session["success_message"] = f"تم تعديل الصلاحية **{old_name}** إلى **{name_safe}** بنجاح."
                # إعادة توجيه إلى صفحة الإدارة بعد التحديث
                return RedirectResponse(url=f"/permissions?page={current_page}", status_code=303)  
    except Exception as e:
        request.session["error_message"] = f"فشل في تعديل الصلاحية: {str(e)}"
        return RedirectResponse(url=f"/permissions?page={current_page}", status_code=303)
    

@router.post("/delete_permission")
async def delete_permission(
    request: Request, 
    perm_id: int = Form(...), 
    current_page: int = Form(1),
    csrf_token: str = Form(...)
):
    verify_csrf_token(request, csrf_token)

    try:
        with get_db_context() as conn:
            with conn.cursor() as cur:
                # محاولة جلب اسم الصلاحية قبل الحذف لرسالة النجاح
                cur.execute("SELECT name FROM permissions WHERE id = %s", (perm_id,))
                perm_record = cur.fetchone()
                
                if not perm_record:
                    request.session["error_message"] = "الصلاحية المراد حذفها غير موجودة."
                    return RedirectResponse(url=f"/permissions?page={current_page}", status_code=303)

                permission_name_to_delete = perm_record[0]

                cur.execute("DELETE FROM permissions WHERE id = %s", (perm_id,))
                conn.commit()
                
                request.session["success_message"] = f"تم حذف الصلاحية **{permission_name_to_delete}** بنجاح."

                # إعادة توجيه إلى نفس الصفحة بعد التحديث
                return RedirectResponse(url=f"/permissions?page={current_page}", status_code=303)  
    except Exception as e:
        request.session["error_message"] = f"فشل في حذف الصلاحية: {str(e)}"
        return RedirectResponse(url=f"/permissions?page={current_page}", status_code=303)