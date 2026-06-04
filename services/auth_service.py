import re
from typing import Optional, Tuple
from fastapi import Request
from postgresql import get_db_context
from psycopg2.extras import RealDictCursor
from security.hash import hash_password, check_password

class AuthService:
    VALID_USERNAME_REGEX = r"^[a-zA-Z0-9][a-zA-Z0-9_-]{2,29}$"
    PASSWORD_MIN_LENGTH = 6
    FORBIDDEN_NAMES = ["admin", "root", "support", "system", "mod", "editor", "engcof"]

    @staticmethod
    def get_user(condition: str, param: tuple):
        with get_db_context() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cursor:
                cursor.execute(f"SELECT id, username, password, role FROM users WHERE {condition}", param)
                return cursor.fetchone()

    @classmethod
    def get_user_by_username(cls, username: str):
        return cls.get_user("LOWER(username) = %s", (username.strip().lower(),))
    
    @classmethod
    def get_user_by_id(cls, user_id: int):
        return cls.get_user("id = %s", (user_id,))

    @classmethod
    def add_new_user(cls, username: str, password: str, role: str) -> Tuple[bool, str]:
        username_clean = username.strip()
        username_lower = username_clean.lower()
        
        # 1. التحقق من الأسماء المحظورة والسيادية للنظام
        if username_lower in cls.FORBIDDEN_NAMES:
            return False, "اسم المستخدم هذا محجوز لجهة إدارية وغير متاح للتسجيل."
        
        # 2. التحقق من النمط القياسي
        if not re.fullmatch(cls.VALID_USERNAME_REGEX, username_clean):
            return False, "اسم المستخدم غير صالح برمجياً."

        if len(password) < cls.PASSWORD_MIN_LENGTH:
            return False, f"كلمة المرور يجب ألا تقل عن {cls.PASSWORD_MIN_LENGTH} أحرف."

        # 3. منع تكرار الحسابات (فحص حاسم بالحروف الصغيرة)
        if cls.get_user_by_username(username_lower):
            return False, "اسم المستخدم مسجل بالفعل في النظام، يرجى اختيار اسم آخر."

        try:
            hashed_pwd = hash_password(password)
            with get_db_context() as conn:
                with conn.cursor() as cur:
                    # نلزم النظام بحقن دور 'user' الافتراضي للحسابات العامة لحمايتها
                    cur.execute(
                        "INSERT INTO users (username, password, role) VALUES (%s, %s, %s)",
                        (username_clean, hashed_pwd, "user" if role != "admin" else "user")
                    )
                    conn.commit()
            return True, "تم إضافة المستخدم بنجاح."
        except Exception as e:
            print(f"❌ Database Error in add_new_user: {e}")
            return False, "حدث خطأ غير متوقع أثناء إنتاج الحساب في قاعدة البيانات."

    @classmethod
    def update_user(cls, user_id: int, username: str, role: str) -> Tuple[bool, str]:
        username_clean = username.strip()
        
        if not re.fullmatch(cls.VALID_USERNAME_REGEX, username_clean):
            return False, "اسم المستخدم المحول غير صالح."
        
        # حظر صارم ومطلق لمنع حقن رتبة الـ admin عبر هذه الدالة العامة
        if role == "admin":
            return False, "إجراء محظور سيادياً: لا يمكن رفع الرتبة إلى مسؤول عبر هذه البوابة."

        try:
            with get_db_context() as conn:
                with conn.cursor() as cur:
                    cur.execute("SELECT username, role FROM users WHERE id = %s", (user_id,))
                    user_record = cur.fetchone()
                    if not user_record:
                        return False, "الحساب المستهدف غير موجود."
                    
                    old_username = user_record[0]
                    
                    # حماية إضافية ضد الـ Mass Assignment: التحقق من الأدوار المصرح بها فقط للتعيين
                    allowed_roles = ["user", "manager"]
                    target_role = role if role in allowed_roles else user_record[1]

                    cur.execute("UPDATE users SET username = %s, role = %s WHERE id = %s", 
                                (username_clean, target_role, user_id))
                    conn.commit()
                    return True, f"تم تعديل المستخدم ({old_username}) بنجاح."
        except Exception as e:
            print(f"❌ Database Error in update_user: {e}")
            return False, "فشلت عملية تحديث البيانات في قاعدة البيانات."

    @classmethod
    def delete_user(cls, user_id: int) -> Tuple[bool, str]:
        try:
            with get_db_context() as conn:
                with conn.cursor() as cur:
                    cur.execute("SELECT username, role FROM users WHERE id = %s", (user_id,))
                    user_record = cur.fetchone()
                    if not user_record:
                        return False, "المستخدم غير موجود بالفعل."

                    # قفل أمان: منع حذف الحسابات الإدارية السيادية عبر دوال الحذف العادية
                    if user_record[1] == "admin" or user_record[0] == "admin":
                        return False, "خطأ أمني: لا يمكن حذف الحساب السيادي الرئيسي للنظام."

                    username_to_delete = user_record[0]
                    cur.execute("DELETE FROM users WHERE id = %s", (user_id,))
                    conn.commit()
                    return True, f"تم حذف المستخدم ({username_to_delete}) بنجاح."
        except Exception as e:
            print(f"❌ Database Error in delete_user: {e}")
            return False, "تعذر معالجة طلب الحذف في قاعدة البيانات."

    @classmethod
    def change_password(
        cls, 
        user_id: int, 
        new_password: str, 
        current_password: Optional[str] = None, 
        request: Optional[Request] = None
    ) -> Tuple[bool, str]:
        if not new_password or len(new_password) < cls.PASSWORD_MIN_LENGTH:
            return False, f"كلمة المرور الجديدة يجب ألا تقل عن {cls.PASSWORD_MIN_LENGTH} أحرف."

        symbol_start_pattern = r"^[-\s_\.\@\#\!\$\%\^\&\*\(\)\{\}\[\]\<\>]"
        if re.match(symbol_start_pattern, new_password):
            return False, "كلمة المرور الجديدة لا يجب أن تبدأ برمز أو مسافة."
            
        try:
            with get_db_context() as conn:
                with conn.cursor() as cur:
                    cur.execute("SELECT password, role, username FROM users WHERE id = %s", (user_id,))
                    user_record = cur.fetchone()
                    if not user_record:
                        return False, "المستخدم غير موجود بالنظام."

                    db_password, db_role, username_to_update = user_record[0], user_record[1], user_record[2]

                    if current_password is not None:
                        if db_role == 'admin':
                            return False, "إجراء محظور: لا يمكن للمسؤول تغيير كلمة مروره من هذه الواجهة."
                        if not check_password(current_password, db_password):
                            return False, "كلمة السر الحالية غير صحيحة."

                    hashed_password = hash_password(new_password)
                    cur.execute("UPDATE users SET password = %s WHERE id = %s", (hashed_password, user_id))
                    
                    ip = "0.0.0.0 (الإدارة)"
                    user_agent = "System Admin Tool"
                    path = "/admin-changed-your-password"

                    if request:
                        current_logged_user = request.session.get("user", {})
                        current_logged_id = current_logged_user.get("id")

                        if current_logged_id == user_id:
                            ip = request.client.host
                            user_agent = request.headers.get("user-agent", "unknown")
                            path = "/profile/change-password"
                        else:
                            ip = f"{request.client.host} (الأدمن)"
                            user_agent = request.headers.get("user-agent", "unknown")
                            path = "/admin-changed-your-password"

                    import uuid
                    security_session = f"sec-mod-{uuid.uuid4()}"
                    
                    cur.execute("""
                        INSERT INTO visits (session_id, user_id, username, ip, user_agent, path)
                        VALUES (%s, %s, %s, %s, %s, %s)
                    """, (security_session, user_id, username_to_update, ip, user_agent, path))
                    
                    conn.commit()
                    return True, "تم تحديث كلمة المرور بنجاح وقيدها في السجل الأمني."
        except Exception as e:
            print(f"❌ Error in AuthService.change_password: {e}")
            return False, "حدث خطأ في النظام أثناء تحديث كلمة المرور."

    @classmethod
    def give_permission(cls, user_id: int, permission_id: int) -> Tuple[bool, str]:
        try:
            with get_db_context() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        "INSERT INTO user_permissions (user_id, permission_id) VALUES (%s, %s)", 
                        (user_id, permission_id)
                    )
                    conn.commit()
            return True, "تم منح الصلاحية بنجاح."
        except Exception as e:
            if "duplicate key value violates unique constraint" in str(e):
                return False, "الصلاحية ممنوحة لهذا المستخدم بالفعل."
            return False, f"فشل في منح الصلاحية: {str(e)}"

    @classmethod
    def remove_permission(cls, user_id: int, permission_id: int) -> Tuple[bool, str]:
        try:
            with get_db_context() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        "DELETE FROM user_permissions WHERE user_id = %s AND permission_id = %s", 
                        (user_id, permission_id)
                    )
                    if cur.rowcount == 0:
                        return False, "هذه الصلاحية ليست لدى المستخدم أصلاً."
                    conn.commit()
            return True, "تم إزالة الصلاحية بنجاح."
        except Exception as e:
            return False, f"فشل في إزالة الصلاحية: {str(e)}"
        
    @classmethod
    def get_admin_dashboard_data(cls, page: int, users_per_page: int = 10, search_query: str = ""):
        offset = (page - 1) * users_per_page
        search_query_clean = f"%{search_query.strip()}%" if search_query else None
        
        with get_db_context() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cursor:
                if search_query_clean:
                    cursor.execute("""
                        SELECT id, username, role FROM users 
                        WHERE username ILIKE %s 
                        ORDER BY id DESC LIMIT %s OFFSET %s
                    """, (search_query_clean, users_per_page, offset))
                else:
                    cursor.execute("SELECT id, username, role FROM users ORDER BY id DESC LIMIT %s OFFSET %s", (users_per_page, offset))
                users = cursor.fetchall()
                
                cursor.execute("SELECT id, name, category FROM permissions")
                all_permissions = cursor.fetchall()
                
                for perm in all_permissions:
                    if not perm.get('category'):
                        perm['category'] = "عام"
                
                user_permissions_map = {}
                for u in users:
                    cursor.execute("""
                        SELECT p.name FROM permissions p
                        JOIN user_permissions up ON p.id = up.permission_id
                        WHERE up.user_id = %s
                    """, (u['id'],))
                    user_permissions_map[u['id']] = [p['name'] for p in cursor.fetchall()]
                
                if search_query_clean:
                    cursor.execute("SELECT COUNT(*) as total FROM users WHERE username ILIKE %s", (search_query_clean,))
                else:
                    cursor.execute("SELECT COUNT(*) as total FROM users")
                    
                total_count = cursor.fetchone()['total']
                total_pages = (total_count + users_per_page - 1) // users_per_page
                total_pages = max(1, total_pages)
                
                return {
                    "users": users,
                    "permissions": all_permissions,
                    "user_permissions": user_permissions_map,
                    "total_pages": total_pages
                }
            
    @classmethod
    def get_permissions_page_data(cls):
        with get_db_context() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("SELECT * FROM permissions ORDER BY category")
                perms = cur.fetchall()
                cur.execute("""
                    SELECT up.*, u.username, p.name 
                    FROM user_permissions up
                    JOIN users u ON up.user_id = u.id
                    JOIN permissions p ON up.permission_id = p.id
                """)
                assignments = cur.fetchall()
                return perms, assignments

    @classmethod
    def get_user_permissions_list(cls, user_id: int) -> list:
        try:
            with get_db_context() as conn:
                with conn.cursor() as cursor:
                    cursor.execute("""
                        SELECT p.name FROM permissions p
                        JOIN user_permissions up ON p.id = up.permission_id
                        WHERE up.user_id = %s
                    """, (user_id,))
                    return [row[0] for row in cursor.fetchall()]
        except Exception as e:
            print(f"❌ Error in AuthService.get_user_permissions_list: {e}")
            return []