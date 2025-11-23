from postgresql import get_db_context
from typing import List, Dict

def get_full_name(code: str, max_length: int = None, include_nick: bool = True) -> str:
    if not code:
        return ""

    names = []
    current_code = code

    with get_db_context() as conn:
        with conn.cursor() as cur:
            while current_code and (max_length is None or len(names) < max_length):
                cur.execute("SELECT name, f_code FROM family_name WHERE code = %s", (current_code,))
                row = cur.fetchone()
                if not row or not row[0]:
                    break
                names.append(row[0].strip())
                if not row[1]:
                    break
                current_code = row[1]

    full_name = " ".join(names)

    # نضيف اللقب فقط إذا طُلب (في التفاصيل نعم، في القائمة لا)
    if include_nick:
        try:
            with get_db_context() as conn:
                with conn.cursor() as cur:
                    cur.execute("SELECT nick_name FROM family_name WHERE code = %s", (code,))
                    nick_row = cur.fetchone()
                    if nick_row and nick_row[0]:
                        nick = nick_row[0].strip()
                        if nick:
                            full_name += f" ({nick})"
        except:
            pass

    return full_name

def get_member_with_details(code: str) -> Dict:
    with get_db_context() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM family_name WHERE code = %s", (code,))
            member = cur.fetchone()
            if not member:
                return None
            # ... باقي التفاصيل (مثل الصورة، الأبناء، إلخ)
    return member