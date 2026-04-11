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
    if not user:
        return False
        
    # 1. الأدمن له كامل الصلاحيات دائماً (بيانات من الجلسة)
    if user.get("role") == "admin":
        return True
    
    # 2. للمستخدم العادي: نأخذ الـ ID فقط من الجلسة 
    user_id = user.get("id")
    if not user_id:
        return False
        
    # 3. نسأل قاعدة البيانات "الآن" (Live Check)
    # هذا يضمن أنه بمجرد ضغطك على "حفظ" في لوحة التحكم، يظهر الزر عند المستخدم في الرشة القادمة
    return has_permission(user_id, perm)
