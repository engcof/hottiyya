#security/session.py
import secrets
import re
from typing import Optional, Tuple, Dict, Any, List
from fastapi import Request, HTTPException, status
from fastapi.responses import HTMLResponse
from postgresql import get_db_context
from services.notification import get_unread_notification_count

class SessionService:

    # =======================================================
    # 1. نظام التحقق الحي من الصلاحيات (RBAC & Live Check)
    # =======================================================

    @staticmethod
    def has_permission(user_id: int, permission_name: str) -> bool:
        """الاستعلام المباشر والحي من قاعدة البيانات للتأكد من امتلاك المستخدم للصلاحية."""
        try:
            with get_db_context() as conn:
                with conn.cursor() as cur:
                    cur.execute("""
                        SELECT 1 FROM user_permissions up
                        JOIN permissions p ON up.permission_id = p.id
                        WHERE up.user_id = %s AND p.name = %s
                    """, (user_id, permission_name))
                    return cur.fetchone() is not None
        except Exception as e:
            print(f"❌ Error in SessionService.has_permission: {e}")
            return False

    @classmethod
    def can(cls, user: Optional[Dict[str, Any]], perm: str) -> bool:
        """
        البوابة الذكية لفحص الصلاحيات:
        - تعطي صلاحية مطلقة للأدمن تلقائياً.
        - تفحص صلاحيات المستخدم العادي حياً من قاعدة البيانات (Live Check).
        """
        if not user:
            return False
            
        if user.get("role") == "admin":
            return True
        
        user_id = user.get("id")
        if not user_id:
            return False
            
        return cls.has_permission(user_id, perm)

    # =======================================================
    # 🔒 بوابات الحماية الفولاذية المتقدمة ضد تلاعب المشرفين
    # =======================================================
    
    @staticmethod
    def verify_manager_is_not_touching_admin(current_user: Optional[Dict[str, Any]], target_user: Optional[Dict[str, Any]], action_context: str) -> None:
        """
        دالة حماية سيادية: تمنع تلاعب المشرفين بحسابات الأدمنية (الرئيسي والتنفيذي) في الخلفية.
        تلقي استثناء (HTTPException) مباشرة لقطع العملية في حال وجود اختراق أو تلاعب.
        """
        if not current_user or not target_user:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN, 
                detail="خطأ أمني: المستخدم الحالي أو المستهدف غير معروف."
            )
            
        # 1. حماية مطلقة لحساب admin الرئيسي ضد أي عملية تعديل أو حذف من أي شخص كان
        if target_user.get("username") == "admin":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="إجراء محظور: لا يمكن تعديل أو حذف البيانات الأساسية للحساب الرئيسي للنظام نهائياً!"
            )
            
        # 2. حماية الأدمن التنفيذي (مثل engcof): إذا كان المستخدم الحالي ليس الأدمن المطلق، ويحاول التلاعب بحساب دوره admin
        if current_user.get("username") != "admin" and target_user.get("role") == "admin":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"خطأ أمني حرج: غير مصرح للمشرفين بإجراء ({action_context}) على حسابات المسؤولين التنفيذيين!"
            )

    # =======================================================
    # 2. إدارة رموز الحماية ضد هجمات CSRF
    # =======================================================

    @staticmethod
    def generate_csrf_token() -> str:
        return secrets.token_urlsafe(32)

    @classmethod
    def verify_csrf_token(cls, request: Request, form_csrf_token: Optional[str]) -> None:
        session_token = request.session.get("csrf_token")
        if not form_csrf_token or form_csrf_token != session_token:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN, 
                detail="رمز حماية الجلسة (CSRF) غير صالح أو مفقود."
            )

    # =======================================================
    # 3. إدارة جلسات المستخدمين والتحقق الحقيقي
    # =======================================================

    @staticmethod
    def get_current_user(request: Request) -> Dict[str, Any]:
        user = request.session.get("user")
        if not user:
            raise HTTPException(
                status_code=status.HTTP_303_SEE_OTHER,
                headers={"Location": "/auth/login"}
            )

        try:
            with get_db_context() as conn:
                with conn.cursor() as cur:
                    cur.execute("SELECT id, username, role FROM users WHERE id = %s", (user['id'],))
                    actual_db_user = cur.fetchone()
                    
                    if not actual_db_user:
                        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="المستخدم غير موجود بالنظام.")

                    updated_user = {
                        "id": actual_db_user[0],
                        "username": actual_db_user[1],
                        "role": actual_db_user[2]
                    }
                    request.session["user"] = updated_user
                    return updated_user
        except Exception:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="فشل التحقق من الجلسة الحالية.")

    @classmethod
    def get_admin_context(cls, request: Request) -> Tuple[Optional[Dict], Optional[str]]:
        try:
            user = cls.get_current_user(request)
            if not user or user.get("role") != "admin":
                return None, None
            
            csrf_token = cls.generate_csrf_token()
            request.session["csrf_token"] = csrf_token
            return user, csrf_token
        except HTTPException:
            return None, None

    # =======================================================
    # 4. بناء سياق البيانات للقوالب (Template Context)
    # =======================================================

    @classmethod
    def get_page_context(
        cls, 
        request: Request, 
        required_perm: Optional[str] = None, 
        additional_perms: Optional[List[str]] = None
    ) -> Optional[Dict[str, Any]]:
        user = request.session.get("user")
        
        if required_perm and not cls.can(user, required_perm):
            return None

        csrf_token = request.session.get("csrf_token")
        if not csrf_token:
            csrf_token = cls.generate_csrf_token()
            request.session["csrf_token"] = csrf_token

        perms_results = {}
        if additional_perms and user:
            for p in additional_perms:
                perms_results[p] = cls.can(user, p)
                
        unread_count = 0
        if user:
            unread_count = get_unread_notification_count(user["id"])

        return {
            "request": request,
            "user": user,
            "csrf_token": csrf_token,
            "perms": perms_results,
            "unread_count": unread_count,
            "can_view": perms_results.get("view_tree", cls.can(user, "view_tree")) if user else False,
            "is_admin": user.get("role") == "admin" if user else False
        }

    @classmethod
    def get_global_context(cls, request: Request) -> Dict[str, Any]:
        user = request.session.get("user")
        return {
            "request": request,
            "user": user,
            "can_view": cls.can(user, "view_tree") if user else False,
            "unread_count": get_unread_notification_count(user["id"]) if user else 0
        }

    @staticmethod
    def set_cache_headers(response: HTMLResponse) -> HTMLResponse:
        response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, proxy-revalidate'
        response.headers['Pragma'] = 'no-cache'
        response.headers['Expires'] = '0'
        return response