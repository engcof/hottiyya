from postgresql import get_db_context
from psycopg2.extras import RealDictCursor
from typing import Tuple, List, Dict

class PermissionService:
    @staticmethod
    def get_permissions_data(page: int, per_page: int = 10) -> Dict:
        offset = (page - 1) * per_page
        with get_db_context() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cursor:
                # جلب الصلاحيات
                cursor.execute("""
                    SELECT id, name, category FROM permissions 
                    ORDER BY name LIMIT %s OFFSET %s
                """, (per_page, offset))
                perms = cursor.fetchall()

                # حساب إجمالي الصفحات
                cursor.execute("SELECT COUNT(*) FROM permissions")
                count_res = cursor.fetchone()
                # التعامل مع اختلاف مخرجات الـ cursor (Dict vs Tuple)
                total_perms = count_res['count'] if isinstance(count_res, dict) else count_res[0]
                total_pages = (total_perms + per_page - 1) // per_page

                # جلب بقية البيانات
                cursor.execute("SELECT id, username, role FROM users ORDER BY username")
                users = cursor.fetchall()
                
                cursor.execute("""
                    SELECT up.*, u.username, p.name as permission_name 
                    FROM user_permissions up
                    JOIN users u ON up.user_id = u.id
                    JOIN permissions p ON up.permission_id = p.id
                """)
                assignments = cursor.fetchall()

                cursor.execute("SELECT id, name, category FROM permissions ORDER BY name")
                all_permissions = cursor.fetchall()

                return {
                    "perms": perms,
                    "users": users,
                    "assignments": assignments,
                    "all_permissions": all_permissions,
                    "total_pages": total_pages,
                    "current_page": page,
                    "has_prev": page > 1,
                    "has_next": page < total_pages
                }
    
    @staticmethod
    def add_permission(name: str, category: str) -> Tuple[bool, str]:
        with get_db_context() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT id FROM permissions WHERE name = %s", (name,))
                if cur.fetchone():
                    return False, f"الصلاحية **{name}** موجودة بالفعل."
                
                cur.execute(
                    "INSERT INTO permissions (name, category) VALUES (%s, %s)",
                    (name, category)
                )
                conn.commit()
                return True, f"تم إضافة الصلاحية **{name}** بنجاح."

    @staticmethod
    def update_permission(perm_id: int, name: str, category: str) -> Tuple[bool, str]:
        with get_db_context() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT name FROM permissions WHERE id = %s", (perm_id,))
                record = cur.fetchone()
                if not record:
                    return False, "الصلاحية غير موجودة."
                
                old_name = record[0]
                if old_name != name:
                    cur.execute("SELECT id FROM permissions WHERE name = %s", (name,))
                    if cur.fetchone():
                        return False, f"الاسم **{name}** مستخدم لصلاحية أخرى."

                cur.execute("UPDATE permissions SET name = %s, category = %s WHERE id = %s", 
                            (name, category, perm_id))
                conn.commit()
                return True, f"تم تعديل **{old_name}** إلى **{name}** بنجاح."

    @staticmethod
    def delete_permission(perm_id: int) -> Tuple[bool, str]:
        with get_db_context() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT name FROM permissions WHERE id = %s", (perm_id,))
                record = cur.fetchone()
                if not record:
                    return False, "الصلاحية غير موجودة."
                
                name = record[0]
                cur.execute("DELETE FROM permissions WHERE id = %s", (perm_id,))
                conn.commit()
                return True, f"تم حذف الصلاحية **{name}** بنجاح."