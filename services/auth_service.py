# services/auth_service.py
from typing import Optional
from fastapi import Request
from postgresql import get_db_context
from psycopg2.extras import RealDictCursor

def get_user(condition: str, param: tuple):
    with get_db_context() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cursor:
            cursor.execute(f"SELECT * FROM users WHERE {condition}", param)
            return cursor.fetchone()





def get_current_user(request: Request) -> Optional[dict]:
    """إرجاع المستخدم المسجل كـ dict أو None"""
    return request.session.get("user")  # يحتوي: username - role

