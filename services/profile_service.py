# profile_service.py
from typing import List, Dict
from postgresql import get_db_context
from psycopg2.extras import RealDictCursor

class ProfileService:
    @staticmethod
    def get_inbox_data(user_id: int, limit: int, offset: int) -> Dict:
        try:
            with get_db_context() as conn:
                with conn.cursor(cursor_factory=RealDictCursor) as cur:
                    cur.execute("""
                        SELECT n.id, n.message, n.created_at, n.is_read, n.sender_id,
                               COALESCE(u.username, 'النظام') as sender_username 
                        FROM notifications n
                        LEFT JOIN users u ON n.sender_id = u.id
                        WHERE n.recipient_id = %s
                        ORDER BY n.created_at DESC LIMIT %s OFFSET %s
                    """, (user_id, limit, offset))
                    messages = cur.fetchall()

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
                    # 💡 التحقق من وجود المستلم الفعلي في قاعدة البيانات لمنع أخطاء الحشو العشوائي الكاذبة
                    cur.execute("SELECT id FROM users WHERE id = %s", (recipient_id,))
                    if not cur.fetchone():
                        return False

                    cur.execute("INSERT INTO notifications (sender_id, recipient_id, message) VALUES (%s, %s, %s)", 
                                (sender_id, recipient_id, message))
                    conn.commit()
            return True
        except Exception as e:
            print(f"❌ Error sending message: {e}")
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
        except Exception: 
            pass

    @staticmethod
    def get_all_users_for_admin() -> List[Dict]:
        try:
            with get_db_context() as conn:
                with conn.cursor(cursor_factory=RealDictCursor) as cur:
                    cur.execute("SELECT id, username FROM users WHERE role != 'admin' ORDER BY username")
                    return cur.fetchall()
        except Exception:
            return []