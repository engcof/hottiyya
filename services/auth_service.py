import re
import html
from typing import Optional, Tuple
from postgresql import get_db_context
from psycopg2.extras import RealDictCursor
from security.hash import hash_password, check_password

class AuthService:
    # المتغيرات الثابتة داخل الكلاس
    VALID_USERNAME_REGEX = r'^[\w-]{2,30}$'
    PASSWORD_MIN_LENGTH = 6

    @staticmethod
    def get_user(condition: str, param: tuple):
        with get_db_context() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cursor:
                cursor.execute(f"SELECT * FROM users WHERE {condition}", param)
                return cursor.fetchone()

    @classmethod
    def get_user_by_username(cls, username: str):
        return cls.get_user("username = %s", (username,))

    @classmethod
    def add_new_user(cls, username: str, password: str, role: str) -> Tuple[bool, str]:
        username_stripped = username.strip()
        
        # استخدام cls. للوصول للمتغيرات الثابتة
        if not re.fullmatch(cls.VALID_USERNAME_REGEX, username_stripped):
            return False, "اسم المستخدم غير صالح."

        if len(password) < cls.PASSWORD_MIN_LENGTH:
            return False, f"كلمة المرور يجب ألا تقل عن {cls.PASSWORD_MIN_LENGTH} أحرف."

        username_safe = html.escape(username_stripped)
        
        if cls.get_user_by_username(username_safe):
            return False, "المستخدم موجود بالفعل."

        try:
            hashed_pwd = hash_password(password)
            with get_db_context() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        "INSERT INTO users (username, password, role) VALUES (%s, %s, %s)",
                        (username_safe, hashed_pwd, html.escape(role))
                    )
                    conn.commit()
            return True, f"تم إضافة المستخدم {username_safe} بنجاح."
        except Exception as e:
            return False, f"خطأ في قاعدة البيانات: {str(e)}"

    @classmethod
    def update_user(cls, user_id: int, username: str, role: str) -> Tuple[bool, str]:
        username_stripped = username.strip()
        # تصحيح: استخدام cls. لضمان الوصول للمتغير
        if not re.fullmatch(cls.VALID_USERNAME_REGEX, username_stripped):
            return False, "اسم المستخدم غير صالح."
        
        if role == "admin":
            return False, "غير مسموح بتعيين دور إدمن عبر هذه الواجهة."

        username_safe = html.escape(username_stripped)
        role_safe = html.escape(role)

        try:
            with get_db_context() as conn:
                with conn.cursor() as cur:
                    cur.execute("SELECT username FROM users WHERE id = %s", (user_id,))
                    user_record = cur.fetchone()
                    if not user_record:
                        return False, "المستخدم غير موجود."
                    
                    old_username = user_record[0]
                    cur.execute("UPDATE users SET username = %s, role = %s WHERE id = %s", 
                                (username_safe, role_safe, user_id))
                    conn.commit()
                    return True, f"تم تعديل المستخدم ({old_username}) بنجاح."
        except Exception as e:
            return False, f"فشل في التعديل: {str(e)}"

    @classmethod
    def delete_user(cls, user_id: int) -> Tuple[bool, str]:
        try:
            with get_db_context() as conn:
                with conn.cursor() as cur:
                    cur.execute("SELECT username FROM users WHERE id = %s", (user_id,))
                    user_record = cur.fetchone()
                    if not user_record:
                        return False, "المستخدم غير موجود بالفعل."

                    username_to_delete = user_record[0]
                    cur.execute("DELETE FROM users WHERE id = %s", (user_id,))
                    conn.commit()
                    return True, f"تم حذف المستخدم ({username_to_delete}) بنجاح."
        except Exception as e:
            return False, f"فشل في الحذف: {str(e)}"

    @classmethod
    def change_password(cls, user_id: int, new_password: str) -> Tuple[bool, str]:
        """تم نقلها داخل الكلاس وتحويلها لـ classmethod"""
        if len(new_password) < cls.PASSWORD_MIN_LENGTH:
            return False, f"كلمة المرور يجب ألا تقل عن {cls.PASSWORD_MIN_LENGTH} أحرف."
            
        try:
            hashed_password = hash_password(new_password)
            with get_db_context() as conn:
                with conn.cursor() as cur:
                    cur.execute("SELECT username FROM users WHERE id = %s", (user_id,))
                    user_record = cur.fetchone()
                    if not user_record:
                        return False, "المستخدم غير موجود."

                    username_to_update = user_record[0]
                    cur.execute("UPDATE users SET password = %s WHERE id = %s", (hashed_password, user_id))
                    conn.commit()
                    return True, f"تم تغيير كلمة مرور ({username_to_update}) بنجاح."
        except Exception as e:
            return False, f"فشل في تغيير كلمة المرور: {str(e)}"
        
    @classmethod
    def give_permission(cls, user_id: int, permission_id: int) -> Tuple[bool, str]:
        """منح صلاحية لمستخدم معين مع معالجة التكرار"""
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
    def get_admin_dashboard_data(cls, page: int, users_per_page: int = 10):
        """جلب بيانات الجدول الرئيسي في صفحة الإدارة"""
        offset = (page - 1) * users_per_page
        with get_db_context() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cursor:
                # جلب المستخدمين
                cursor.execute("SELECT id, username, role FROM users ORDER BY id DESC LIMIT %s OFFSET %s", (users_per_page, offset))
                users = cursor.fetchall()
                
                # جلب الصلاحيات المتاحة
                cursor.execute("SELECT id, name, category FROM permissions")
                all_permissions = cursor.fetchall()
                
                # جلب صلاحيات كل مستخدم
                user_permissions_map = {}
                for u in users:
                    cursor.execute("""
                        SELECT p.name FROM permissions p
                        JOIN user_permissions up ON p.id = up.permission_id
                        WHERE up.user_id = %s
                    """, (u['id'],))
                    user_permissions_map[u['id']] = [p['name'] for p in cursor.fetchall()]
                
                # حساب الإجمالي للترقيم
                cursor.execute("SELECT COUNT(*) as total FROM users")
                total_count = cursor.fetchone()['total']
                total_pages = (total_count + users_per_page - 1) // users_per_page
                
                return {
                    "users": users,
                    "permissions": all_permissions,
                    "user_permissions": user_permissions_map,
                    "total_pages": total_pages
                }

    @classmethod
    def get_permissions_page_data(cls):
        """جلب بيانات صفحة الصلاحيات المنفصلة"""
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

    