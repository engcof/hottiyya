# services/analytics.py
import uuid
from datetime import datetime, timedelta
from fastapi import Request
from postgresql import get_db_context

def log_visit(request: Request, user: dict | None = None):
    """تسجيل الزيارة بطريقة آمنة وسريعة مع ON CONFLICT وتحديث الإجمالي."""
    session_id = request.session.get("session_id")
    if not session_id:
        session_id = str(uuid.uuid4())
        request.session["session_id"] = session_id


    user_id = user.get("id") if user and user.get("id") else None
    username = user.get("username") if user and user.get("username") else None

    ip = request.client.host
    path = request.url.path
    user_agent = request.headers.get("user-agent", "unknown")

    try:
        with get_db_context() as conn:
            with conn.cursor() as cur:
                # 1. محاولة إدراج/تحديث الجلسة
                cur.execute("""
                    INSERT INTO visits (
                        session_id, user_id, username, ip, user_agent, path
                    ) VALUES (%s, %s, %s, %s, %s, %s)
                    ON CONFLICT (session_id) DO UPDATE SET
                        timestamp = NOW(),
                        user_id = EXCLUDED.user_id,
                        username = EXCLUDED.username,
                        ip = EXCLUDED.ip,
                        path = EXCLUDED.path
                    RETURNING xmax = 0;
                """, (session_id, user_id, username, ip, user_agent, path))
                
                # RETURNING xmax = 0: يُرجع True إذا كان الصف جديدًا (INSERT)، و False إذا تم تحديثه (UPDATE)
                is_new_session = cur.fetchone()[0]

                # 2. تحديث العداد الإجمالي إذا كانت الجلسة جديدة
                if is_new_session:
                    cur.execute("""
                        UPDATE stats_summary
                        SET value = value + 1
                        WHERE key = 'total_visitors_count';
                    """)

            conn.commit()
    except Exception as e:
        # فقط في أول تشغيل أو لو الـ index لسه ما اتعملش
        if "uniq_session_id" in str(e) or "ON CONFLICT" in str(e):
            print(f"تحذير مؤقت (أول مرة فقط): {e}")
        else:
            print(f"خطأ غير متوقع في log_visit: {e}")


def get_total_visitors() -> int:
    """جلب العدد الإجمالي الحقيقي من جدول stats_summary."""
    with get_db_context() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT value FROM stats_summary WHERE key = 'total_visitors_count'")
            result = cur.fetchone()
            return result[0] if result else 0


def get_today_visitors() -> int:
    today = datetime.now().date()
    with get_db_context() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(DISTINCT session_id) FROM visits WHERE DATE(timestamp) = %s", (today,))
            return cur.fetchone()[0] or 0


def get_online_users() -> list[dict]:
    threshold = datetime.now() - timedelta(minutes=10)
    with get_db_context() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT DISTINCT ON (session_id) username, timestamp
                FROM visits
                WHERE timestamp > %s
                ORDER BY session_id, timestamp DESC
            """, (threshold,))
            rows = cur.fetchall()
            return [
                {
                    "username": row[0] or "زائر مجهول",
                    "last_seen": row[1].strftime("%H:%M")
                }
                for row in rows
            ]


def get_online_count() -> int:
    return len(get_online_users())


# =======================================================
# دوال خاصة بصفحة الإدارة لمراقبة الدخول
# =======================================================

def get_logged_in_users_history(limit: int = 50) -> list[dict]:
    """
    جلب سجلات الدخول (حيث يكون user_id موجودًا) مع تاريخ ووقت آخر رؤية.
    نستخدم DISTINCT ON (user_id) لضمان ظهور آخر سجل لكل مستخدم.
    """
    with get_db_context() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT DISTINCT ON (user_id) 
                       username, timestamp, user_id
                FROM visits
                WHERE user_id IS NOT NULL AND user_id > 0
                ORDER BY user_id, timestamp DESC
                LIMIT %s
            """, (limit,))
            rows = cur.fetchall()
            
            # تحويل النتائج إلى قائمة قواميس مع تنسيق التاريخ
            return [
                {
                    "username": row[0],
                    "timestamp": row[1], # سنقوم بتنسيقها في قالب HTML
                    "user_id": row[2]
                }
                for row in rows
            ]


def clean_visits_history(days: int = 7):
    """حذف سجلات الزيارات والدخول التي مر عليها أكثر من (days) يوم."""
    threshold_date = datetime.now() - timedelta(days=days)
    try:
        with get_db_context() as conn:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM visits WHERE timestamp < %s", (threshold_date,))
            conn.commit()
            print(f"تم حذف سجلات الزيارات التي مر عليها أكثر من {days} أيام.")
    except Exception as e:
        print(f"خطأ أثناء حذف السجلات القديمة: {e}")

def log_action(user_id: int, action: str, details: str):
    """تسجيل العملية مع التأكد من هوية المستخدم من قاعدة البيانات."""
    try:
        with get_db_context() as conn:
            with conn.cursor() as cur:
                # نتحقق أولاً من اسم المستخدم المرتبط بهذا الـ ID لضمان الدقة
                cur.execute("SELECT username FROM users WHERE id = %s", (user_id,))
                user_res = cur.fetchone()
                actual_username = user_res[0] if user_res else "Unknown"

                cur.execute("""
                    INSERT INTO activity_logs (user_id, action, details)
                    VALUES (%s, %s, %s)
                """, (user_id, action, details))
            conn.commit()
    except Exception as e:
        print(f"Error in log_action: {e}")


def get_all_activity_logs(limit: int = 100):
    """جلب سجل النشاطات مع اسم المستخدم القائم بالعملية."""
    with get_db_context() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT al.id, u.username, al.action, al.details, al.timestamp
                FROM activity_logs al
                LEFT JOIN users u ON al.user_id = u.id
                ORDER BY al.timestamp DESC
                LIMIT %s
            """, (limit,))
            return cur.fetchall()       

def get_activity_logs_paginated(page: int = 1, per_page: int = 30):
    """جلب السجلات مع الترقيم (30 نشاط لكل صفحة)."""
    offset = (page - 1) * per_page
    
    with get_db_context() as conn:
        with conn.cursor() as cur:
            # 1. جلب العدد الإجمالي للصفحات
            cur.execute("SELECT COUNT(*) FROM activity_logs")
            total_logs = cur.fetchone()[0]
            total_pages = (total_logs + per_page - 1) // per_page

            # 2. جلب البيانات مع ربطها باسم المستخدم
            cur.execute("""
                SELECT al.id, u.username, al.action, al.details, al.timestamp
                FROM activity_logs al
                LEFT JOIN users u ON al.user_id = u.id
                ORDER BY al.timestamp DESC
                LIMIT %s OFFSET %s
            """, (per_page, offset))
            
            logs = [
                {
                    "id": row[0],
                    "username": row[1] or "نظام/محذوف",
                    "action": row[2],
                    "details": row[3],
                    "timestamp": row[4]
                } for row in cur.fetchall()
            ]
            
            return logs, total_pages        
