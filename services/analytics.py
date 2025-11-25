# services/analytics.py
import uuid
from datetime import datetime, timedelta
from fastapi import Request
from postgresql import get_db_context

def log_visit(request: Request, user: dict | None = None):
    session_id = request.session.get("session_id")
    if not session_id:
        session_id = str(uuid.uuid4())
        request.session["session_id"] = session_id

    path = request.url.path
    ip = request.client.host
    ua = request.headers.get("user-agent", "unknown")

    with get_db_context() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO visits (session_id, user_id, username, ip, user_agent, path)
                VALUES (%s, %s, %s, %s, %s, %s)
            """, (
                session_id,
                user.get("id") if user else None,
                user.get("username") if user else None,
                ip,
                ua,
                path
            ))
            conn.commit()

def get_total_visitors() -> int:
    with get_db_context() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(DISTINCT session_id) FROM visits")
            result = cur.fetchone()[0]
            return result or 0

def get_today_visitors() -> int:
    today = datetime.now().date()
    with get_db_context() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT COUNT(DISTINCT session_id) FROM visits
                WHERE DATE(timestamp) = %s
            """, (today,))
            result = cur.fetchone()[0]
            return result or 0

def get_online_users() -> list[dict]:
    """اللي دخلوا في آخر 10 دقايق"""
    threshold = datetime.now() - timedelta(minutes=10)
    with get_db_context() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT DISTINCT ON (session_id) 
                       session_id, username, timestamp
                FROM visits 
                WHERE timestamp > %s
                ORDER BY session_id, timestamp DESC
            """, (threshold,))
            rows = cur.fetchall()

    return [
        {
            "username": row[1] or "زائر مجهول",
            "last_seen": row[2].strftime("%H:%M:%S")
        }
        for row in rows
    ]

def get_online_count() -> int:
    return len(get_online_users())