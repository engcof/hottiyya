# services/analytics.py
import uuid
from datetime import datetime, timedelta
from fastapi import Request
from postgresql import get_db_context


def log_visit(request: Request, user: dict | None = None):
    """تسجيل الزيارة بطريقة آمنة وسريعة مع ON CONFLICT"""
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
                """, (session_id, user_id, username, ip, user_agent, path))
            conn.commit()
    except Exception as e:
        # فقط في أول تشغيل أو لو الـ index لسه ما اتعملش
        if "uniq_session_id" in str(e) or "ON CONFLICT" in str(e):
            print(f"تحذير مؤقت (أول مرة فقط): {e}")
        else:
            print(f"خطأ غير متوقع في log_visit: {e}")


def get_total_visitors() -> int:
    with get_db_context() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(DISTINCT session_id) FROM visits")
            return cur.fetchone()[0] or 0


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