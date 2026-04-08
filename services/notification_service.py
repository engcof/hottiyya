from typing import List, Dict, Optional
from postgresql import get_db_context
from psycopg2.extras import RealDictCursor

class NotificationService:
    @staticmethod
    def get_inbox_messages(user_id: int, limit: int, offset: int) -> List[Dict]:
        """جلب رسائل صندوق الوارد مع اسم المرسل ودعم الترقيم."""
        try:
            with get_db_context() as conn:
                with conn.cursor(cursor_factory=RealDictCursor) as cur:
                    cur.execute("""
                        SELECT 
                            n.id, n.message, n.created_at, n.is_read, n.sender_id,
                            COALESCE(u.username, 'النظام') as sender_username 
                        FROM notifications n
                        LEFT JOIN users u ON n.sender_id = u.id
                        WHERE n.recipient_id = %s
                        ORDER BY n.created_at DESC
                        LIMIT %s OFFSET %s
                    """, (user_id, limit, offset))
                    return cur.fetchall()
        except Exception as e:
            print(f"❌ Error in get_inbox_messages: {e}")
            return []

    @staticmethod
    def get_counts(user_id: int) -> Dict[str, int]:
        """جلب إجمالي الرسائل وغير المقروء منها في استدعاء واحد (لتحسين الأداء)."""
        try:
            with get_db_context() as conn:
                with conn.cursor() as cur:
                    cur.execute("""
                        SELECT 
                            COUNT(id) as total,
                            COUNT(id) FILTER (WHERE is_read = FALSE) as unread
                        FROM notifications 
                        WHERE recipient_id = %s
                    """, (user_id,))
                    res = cur.fetchone()
                    return {"total": res[0], "unread": res[1]}
        except Exception:
            return {"total": 0, "unread": 0}

    @staticmethod
    def send_notification(recipient_id: int, message: str, sender_id: int) -> bool:
        """إضافة إشعار جديد."""
        try:
            with get_db_context() as conn:
                with conn.cursor() as cur:
                    cur.execute("""
                        INSERT INTO notifications (sender_id, recipient_id, message)
                        VALUES (%s, %s, %s)
                    """, (sender_id, recipient_id, message))
                    conn.commit()
            return True
        except Exception:
            return False

    @staticmethod
    def delete_notification(notification_id: int, user_id: int) -> bool:
        """حذف إشعار مع التحقق من ملكية المستخدم."""
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
        """تحديث حالة الرسالة إلى مقروءة."""
        with get_db_context() as conn:
            with conn.cursor() as cur:
                cur.execute("UPDATE notifications SET is_read = TRUE WHERE id = %s AND recipient_id = %s", (notification_id, user_id))
                conn.commit()