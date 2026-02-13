# utils/permissions.py
from postgresql import get_db_context

def has_permission(user_id: int, permission: str) -> bool:
    try:
        with get_db_context() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT 1 FROM user_permissions up
                    JOIN permissions p ON up.permission_id = p.id
                    WHERE up.user_id = %s AND p.name = %s
                """, (user_id, permission))
                return cur.fetchone() is not None
    except Exception as e:
        print(f"❌ Error in has_permission: {e}")
        return False

def can(user: dict, perm: str) -> bool:
    """المساعد الشامل الذي تستخدمه في القوالب والراوترات"""
    if not user:
        return False
    # الأدمن يمر دائماً
    if user.get("role") == "admin":
        return True
    # التحقق للمستخدمين العاديين من قاعدة البيانات
    return bool(user.get("id") and has_permission(user.get("id"), perm))       
