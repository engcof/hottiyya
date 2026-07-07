# services/notification_service.py
from typing import List, Dict, Optional
from postgresql import get_db_context
from psycopg2.extras import RealDictCursor

class NotificationService:

    @staticmethod
    def get_inbox_data(user_id: int, limit: int, offset: int) -> Dict:
        """
        جلب رسائل صندوق الوارد للمستخدم مع اسم المرسل، ودعم الترقيم (Pagination)،
        بالإضافة إلى حساب العدد الإجمالي والرسائل غير المقروءة في استعلام واحد.
        """
        try:
            with get_db_context() as conn:
                with conn.cursor(cursor_factory=RealDictCursor) as cur:
                    # 1. جلب الرسائل للصفحة الحالية
                    cur.execute("""
                        SELECT n.id, n.message, n.created_at, n.is_read, n.sender_id,
                               COALESCE(u.username, 'الإدارة/النظام') as sender_username 
                        FROM notifications n
                        LEFT JOIN users u ON n.sender_id = u.id
                        WHERE n.recipient_id = %s
                        ORDER BY n.created_at DESC 
                        LIMIT %s OFFSET %s
                    """, (user_id, limit, offset))
                    messages = cur.fetchall()

                    # 2. حساب الإجمالي وغير المقروء دفعة واحدة لتحسين الأداء
                    cur.execute("""
                        SELECT 
                            COUNT(id) as total,
                            COUNT(id) FILTER (WHERE is_read = FALSE) as unread
                        FROM notifications 
                        WHERE recipient_id = %s
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
    def get_unread_count(user_id: int) -> int:
        """
        حساب العدد الإجمالي للرسائل غير المقروءة فقط (مفيدة للاستخدام في القوالب والمين لعلامة التنبيه).
        """
        try:
            with get_db_context() as conn:
                with conn.cursor() as cur:
                    cur.execute("""
                        SELECT COUNT(id) 
                        FROM notifications 
                        WHERE recipient_id = %s AND is_read = FALSE
                    """, (user_id,))
                    result = cur.fetchone()
                    return result[0] if result else 0
        except Exception as e:
            print(f"❌ Error getting unread count: {e}")
            return 0

    @staticmethod
    def send_notification(sender_id: int, recipient_id: int, message: str) -> bool:
        """
        إرسال رسالة أو إشعار جديد إلى مستخدم معين بعد التحقق من وجوده.
        """
        try:
            with get_db_context() as conn:
                with conn.cursor() as cur:
                    # التحقق من وجود المستلم الفعلي في قاعدة البيانات لمنع الهجمات أو الأخطاء العشوائية
                    cur.execute("SELECT id FROM users WHERE id = %s", (recipient_id,))
                    if not cur.fetchone():
                        return False

                    cur.execute("""
                        INSERT INTO notifications (sender_id, recipient_id, message) 
                        VALUES (%s, %s, %s)
                    """, (sender_id, recipient_id, message))
                    conn.commit()
            return True
        except Exception as e:
            print(f"❌ Error sending notification: {e}")
            return False

    @staticmethod
    def mark_as_read(notification_id: int, user_id: int) -> bool:
        """
        وضع علامة 'مقروءة' على إشعار معين يخص المستخدم لحمايته من هجمات الـ IDOR.
        """
        try:
            with get_db_context() as conn:
                with conn.cursor() as cur:
                    cur.execute("""
                        UPDATE notifications 
                        SET is_read = TRUE 
                        WHERE id = %s AND recipient_id = %s
                    """, (notification_id, user_id))
                    conn.commit()
            return True
        except Exception as e:
            print(f"❌ Error marking notification as read: {e}")
            return False

    @staticmethod
    def delete_notification(notification_id: int, user_id: int) -> bool:
        """
        حذف إشعار معين يخص المستخدم لضمان الأمان.
        """
        try:
            with get_db_context() as conn:
                with conn.cursor() as cur:
                    cur.execute("""
                        DELETE FROM notifications 
                        WHERE id = %s AND recipient_id = %s
                    """, (notification_id, user_id))
                    conn.commit()
            return True
        except Exception as e:
            print(f"❌ Error deleting notification: {e}")
            return False

    @staticmethod
    def get_all_users_for_admin() -> List[Dict]:
        """
        جلب قائمة المستخدمين لصفحة إرسال الرسائل الخاصة بالمدير (باستثناء المدراء الآخرين).
        """
        try:
            with get_db_context() as conn:
                with conn.cursor(cursor_factory=RealDictCursor) as cur:
                    cur.execute("SELECT id, username FROM users WHERE role != 'admin' ORDER BY username")
                    return cur.fetchall()
        except Exception as e:
            print(f"❌ Error fetching users for admin: {e}")
            return []

    @staticmethod
    def get_admin_user_id() -> Optional[int]:
        """
        جلب معرّف (ID) لأول مستخدم يمتلك دور الـ 'admin'.
        """
        try:
            with get_db_context() as conn:
                with conn.cursor() as cur:
                    cur.execute("SELECT id FROM users WHERE role = 'admin' LIMIT 1")
                    result = cur.fetchone()
                    return result[0] if result else None
        except Exception as e:
            print(f"❌ Error getting admin ID: {e}")
            return None