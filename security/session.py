from fastapi import Request, HTTPException, status
from typing import Optional
from fastapi.responses import HTMLResponse
from postgresql import get_db_context



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

def set_cache_headers(response: HTMLResponse):
    response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, proxy-revalidate'
    response.headers['Pragma'] = 'no-cache'
    response.headers['Expires'] = '0'
    return response