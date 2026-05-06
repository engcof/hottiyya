#security/session.py
from fastapi import Request, HTTPException, status
from typing import Optional
from fastapi.responses import HTMLResponse
from postgresql import get_db_context
from security.csrf import generate_csrf_token, verify_csrf_token
from utils.has_permissions import can
from services.notification import get_unread_notification_count


def get_current_user(request: Request) -> dict:
    user= request.session.get("user")
    if not user:
        raise HTTPException(
            status_code=status.HTTP_303_SEE_OTHER,
            headers={"Location": "/auth/login"}
        )

    # 🟢 التحقق من الهوية الحقيقية من قاعدة البيانات الموحدة
    with get_db_context() as conn:
        with conn.cursor() as cur:
            # نبحث بالـ ID لضمان الحصول على engcof حتى لو تغيرت الجلسة
            cur.execute("SELECT id, username, role FROM users WHERE id = %s", (user['id'],))
            actual_db_user = cur.fetchone()
            
            if not actual_db_user:
                 raise HTTPException(status_code=401, detail="المستخدم غير موجود")

            # تحديث بيانات الجلسة بالبيانات الحقيقية من DB
            return {
                "id": actual_db_user[0],
                "username": actual_db_user[1],
                "role": actual_db_user[2]
            }

# --- Helper Function لمنع التكرار في التحقق وجلب التوكن ---
def get_admin_context(request: Request):
    user = get_current_user(request)
    if not user or user.get("role") != "admin":
        return None, None
    csrf_token = generate_csrf_token()
    request.session["csrf_token"] = csrf_token
    return user, csrf_token



def get_page_context(request: Request, required_perm: str = None, additional_perms: list = None):
    user = request.session.get("user")
    
    if required_perm and not can(user, required_perm):
        return None

    # 3. التحقق من وجود التوكن أو توليده (تعديل لضمان الثبات)
    csrf_token = request.session.get("csrf_token")
    if not csrf_token:
        csrf_token = generate_csrf_token()
        request.session["csrf_token"] = csrf_token

    perms_results = {}
    if additional_perms:
        for p in additional_perms:
            perms_results[p] = can(user, p)
            
    unread_count = 0
    if user:
        unread_count = get_unread_notification_count(user["id"])

    return {
        "request": request,
        "user": user,
        "csrf_token": csrf_token, # سيتم تمريره للقالب الآن
        "perms": perms_results,
        "unread_count": unread_count,
        "can_view": perms_results.get("view_tree", can(user, "view_tree")) if user else False,
        "is_admin": user.get("role") == "admin" if user else False
    }

# دالة مساعدة لتجهيز سياق البيانات (Context)
def get_global_context(request):
    user = request.session.get("user")
    return {
        "request": request,
        "user": user,
        "can_view": can(user, "view_tree") if user else False,
        "unread_count": get_unread_notification_count(user["id"]) if user else 0
    }
def set_cache_headers(response: HTMLResponse):
    response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, proxy-revalidate'
    response.headers['Pragma'] = 'no-cache'
    response.headers['Expires'] = '0'
    return response