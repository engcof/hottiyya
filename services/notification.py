# services/notification.py
from typing import Optional, List, Dict
from postgresql import get_db_context
from psycopg2.extras import RealDictCursor
import math

# ----------------------------------------------------
# # 1. دوال جلب الإشعارات (المعدلة لدعم الترقيم)
# ----------------------------------------------------
def get_inbox_messages(user_id: int, limit: int, offset: int) -> List[Dict]:
    """
    جلب رسائل صندوق الوارد للمستخدم مع اسم المرسل، مع دعم الترقيم.
    """
    with get_db_context() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("""
                SELECT 
                    n.id, n.message, n.created_at, n.is_read, n.sender_id,
                    -- 💡 تم تعديل هنا من n.message_text إلى n.message
                    COALESCE(u.username, 'الإدارة/النظام') as sender_username 
                FROM notifications n
                LEFT JOIN users u ON n.sender_id = u.id
                WHERE n.recipient_id = %s
                ORDER BY n.created_at DESC
                LIMIT %s OFFSET %s
            """, (user_id, limit, offset))
            return cur.fetchall()

# ----------------------------------------------------
# # 2. دوال العد والحساب (الأسماء المحسّنة)
# # ----------------------------------------------------
def get_total_inbox_messages_count(user_id: int) -> int:
    """
    حساب العدد الإجمالي لرسائل صندوق الوارد للمستخدم.
    (تحل محل count_user_messages)
    """
    with get_db_context() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(id) FROM notifications WHERE recipient_id = %s", (user_id,))
            return cur.fetchone()[0]

def get_unread_notification_count(user_id: int) -> int:
    """
    حساب العدد الإجمالي للرسائل غير المقروءة.
    (تحل محل count_unread_messages و get_unread_notifications)
    """
    with get_db_context() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(id) FROM notifications WHERE recipient_id = %s AND is_read = FALSE", (user_id,))
            return cur.fetchone()[0]

# ----------------------------------------------------
# 3. دوال العمليات (الإبقاء عليها)
# ----------------------------------------------------
def mark_notification_as_read(notification_id: int, user_id: int):
    """وضع علامة "مقروءة" على إشعار معين يخص المستخدم."""
    with get_db_context() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                UPDATE notifications
                SET is_read = TRUE
                WHERE id = %s AND recipient_id = %s
            """, (notification_id, user_id))
            conn.commit()

def delete_notification(notification_id: int, user_id: int):
    """حذف إشعار معين يخص المستخدم لضمان الأمان."""
    with get_db_context() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                DELETE FROM notifications
                WHERE id = %s AND recipient_id = %s
            """, (notification_id, user_id))
            conn.commit()

def send_notification(recipient_id: int, message: str, sender_id: int):
    """إضافة إشعار جديد إلى قاعدة البيانات."""
    with get_db_context() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO notifications (sender_id, recipient_id, message)
                VALUES (%s, %s, %s)
            """, (sender_id, recipient_id, message))
            conn.commit()
            
# ----------------------------------------------------
# 4. دوال الإدارة (الإبقاء عليها)
# ----------------------------------------------------
def get_all_users_for_admin() -> list[dict]:
    """جلب قائمة المستخدمين (لصفحة الإرسال للمدير)."""
    with get_db_context() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("SELECT id, username FROM users WHERE role != 'admin' ORDER BY username")
            return cur.fetchall()

def get_admin_user_id() -> int | None:
    """جلب معرّف (ID) لأي مستخدم لديه دور 'admin'."""
    with get_db_context() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT id FROM users WHERE role = 'admin' LIMIT 1")
            result = cur.fetchone()
            return result[0] if result else None