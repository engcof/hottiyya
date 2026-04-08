# profile_service.py
import re
import math
from typing import List, Dict, Optional, Tuple
from postgresql import get_db_context
from psycopg2.extras import RealDictCursor
from security.hash import hash_password, check_password

class ProfileService:
    # --- إعدادات الأمان ---
    SYMBOL_START_PATTERN = r"^[-\s_\.\@\#\!\$\%\^\&\*\(\)\{\}\[\]\<\>]"

    # ---------------------------------------------------------
    # 1. إدارة الحساب والأمان
    # ---------------------------------------------------------
    @staticmethod
    def change_user_password(user_id: int, current_password: str, new_password: str) -> Tuple[bool, str]:
        if not new_password or len(new_password) < 6:
            return False, "كلمة السر الجديدة يجب أن تكون 6 أحرف على الأقل."

        if re.match(ProfileService.SYMBOL_START_PATTERN, new_password):
            return False, "كلمة السر الجديدة لا يجب أن تبدأ برمز أو مسافة."

        try:
            with get_db_context() as conn:
                with conn.cursor() as cur:
                    cur.execute("SELECT password FROM users WHERE id = %s", (user_id,))
                    db_row = cur.fetchone()
                    
                    if not db_row or not check_password(current_password, db_row[0]):
                        return False, "كلمة السر الحالية غير صحيحة."

                    cur.execute("UPDATE users SET password = %s WHERE id = %s", (hash_password(new_password), user_id))
                    conn.commit()
                    return True, "تم تحديث كلمة المرور بنجاح!"
        except Exception as e:
            print(f"❌ Error changing password: {e}")
            return False, "حدث خطأ في النظام أثناء تحديث كلمة المرور."

    # ---------------------------------------------------------
    # 2. إدارة الإشعارات والرسائل
    # ---------------------------------------------------------
    @staticmethod
    def get_inbox_data(user_id: int, limit: int, offset: int) -> Dict:
        """جلب الرسائل والإحصائيات في دالة واحدة لتقليل استعلامات قاعدة البيانات."""
        try:
            with get_db_context() as conn:
                with conn.cursor(cursor_factory=RealDictCursor) as cur:
                    # جلب الرسائل
                    cur.execute("""
                        SELECT n.id, n.message, n.created_at, n.is_read, n.sender_id,
                               COALESCE(u.username, 'النظام') as sender_username 
                        FROM notifications n
                        LEFT JOIN users u ON n.sender_id = u.id
                        WHERE n.recipient_id = %s
                        ORDER BY n.created_at DESC LIMIT %s OFFSET %s
                    """, (user_id, limit, offset))
                    messages = cur.fetchall()

                    # جلب الأعداد (الإجمالي وغير المقروء)
                    cur.execute("""
                        SELECT 
                            COUNT(id) as total,
                            COUNT(id) FILTER (WHERE is_read = FALSE) as unread
                        FROM notifications WHERE recipient_id = %s
                    """, (user_id,))
                    counts = cur.fetchone()

                    return {
                        "messages": messages,
                        "total_count": counts['total'] or 0,
                        "unread_count": counts['unread'] or 0
                    }
        except Exception as e:
            print(f"❌ Error fetching inbox data: {e}")
            return {"messages": [], "total_count": 0, "unread_count": 0}

    @staticmethod
    def send_message(sender_id: int, recipient_id: int, message: str) -> bool:
        try:
            with get_db_context() as conn:
                with conn.cursor() as cur:
                    cur.execute("INSERT INTO notifications (sender_id, recipient_id, message) VALUES (%s, %s, %s)", 
                                (sender_id, recipient_id, message))
                    conn.commit()
            return True
        except Exception:
            return False

    @staticmethod
    def delete_message(notification_id: int, user_id: int) -> bool:
        try:
            with get_db_context() as conn:
                with conn.cursor() as cur:
                    cur.execute("DELETE FROM notifications WHERE id = %s AND recipient_id = %s", (notification_id, user_id))
                    conn.commit()
            return True
        except Exception:
            return False

    @staticmethod
    def mark_as_read(notification_id: int, user_id: int):
        try:
            with get_db_context() as conn:
                with conn.cursor() as cur:
                    cur.execute("UPDATE notifications SET is_read = TRUE WHERE id = %s AND recipient_id = %s", (notification_id, user_id))
                    conn.commit()
        except Exception: pass

    # ---------------------------------------------------------
    # 3. وظائف الإدارة (Admin Tasks)
    # ---------------------------------------------------------
    @staticmethod
    def get_all_users_for_admin() -> List[Dict]:
        try:
            with get_db_context() as conn:
                with conn.cursor(cursor_factory=RealDictCursor) as cur:
                    cur.execute("SELECT id, username FROM users WHERE role != 'admin' ORDER BY username")
                    return cur.fetchall()
        except Exception:
            return []

