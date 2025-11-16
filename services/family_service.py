from postgresql import get_db_context
from typing import List, Dict

def get_full_name(code: str) -> str:
    with get_db_context() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT name, f_code FROM family_name WHERE code=%s", (code,))
            result = cur.fetchone()
            if not result:
                return ""
            name, f_code = result
            names = [name]
            while f_code:
                cur.execute("SELECT name, f_code FROM family_name WHERE code=%s", (f_code,))
                row = cur.fetchone()
                if not row:
                    break
                name, f_code = row
                names.append(name)
            return " ".join((names))  # من الأقدم إلى الأحدث
    return ""

def get_member_with_details(code: str) -> Dict:
    with get_db_context() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM family_name WHERE code = %s", (code,))
            member = cur.fetchone()
            if not member:
                return None
            # ... باقي التفاصيل (مثل الصورة، الأبناء، إلخ)
    return member