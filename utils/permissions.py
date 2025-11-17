# utils/permissions.py
from postgresql import get_db_context

def has_permission(user_id: int, permission: str) -> bool:
    with get_db_context() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT 1 FROM user_permissions 
                WHERE user_id = %s AND permission = %s
            """, (user_id, permission))
            return cur.fetchone() is not None