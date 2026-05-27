# family_service.py
import math
import os
import shutil 
import re
from typing import List, Dict, Optional, Tuple, Any
from psycopg2.extras import RealDictCursor 
from datetime import date
import html

from utils.normalize import normalize_arabic
from postgresql import get_db_context

class FamilyService:
    PAGE_SIZE = 24
    UPLOAD_DIR = "static/uploads"

    @staticmethod
    def _ensure_upload_dir():
        """التأكد من وجود مجلد الرفع."""
        if not os.path.exists(FamilyService.UPLOAD_DIR):
            os.makedirs(FamilyService.UPLOAD_DIR, exist_ok=True)

    # ===============================================
    # 1. البحث وجلب القوائم
    # ===============================================
    @staticmethod
    def search_and_fetch_family(q: str, page: int) -> Tuple[List[Dict[str, Any]], int, int, int]:
        with get_db_context() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                phrase = q.strip()
                normalized_input = normalize_arabic(phrase)
                search_term_like = f"%{normalized_input}%"
                
                if re.fullmatch(r"[A-Z]\d{0,3}-\d{3}-\d{3}", phrase.upper()):
                    sql_condition = "code = %s"
                    count_params = (phrase.upper(),)
                elif "-" in phrase and len(phrase.split()) == 1:
                    sql_condition = "code ILIKE %s"
                    count_params = (f"%{phrase}%",)
                else:
                    sql_condition = "(public.normalize_arabic(full_name) ILIKE %s OR public.normalize_arabic(nick_name) ILIKE %s)"
                    count_params = (search_term_like, search_term_like)

                sql_condition += " AND level >= 0"

                cur.execute(f"SELECT COUNT(*) FROM family_search WHERE {sql_condition}", count_params)
                total_count = cur.fetchone()['count']
                
                totals_pages = math.ceil(total_count / FamilyService.PAGE_SIZE) if total_count > 0 else 1
                current_page = max(1, min(page, totals_pages))
                offset = (current_page - 1) * FamilyService.PAGE_SIZE
                
                cur.execute(f"""
                    SELECT code, public.get_full_name(code, 5, FALSE) AS full_name, nick_name
                    FROM family_search
                    WHERE {sql_condition}
                    ORDER BY public.normalize_arabic(full_name) ASC
                    LIMIT %s OFFSET %s
                """, count_params + (FamilyService.PAGE_SIZE, offset))
                
                members = cur.fetchall()
                return members, current_page, totals_pages, total_count

    # ===============================================
    # 2. جلب التفاصيل الشاملة (Details)
    # ===============================================
    @staticmethod
    def get_member_details(code: str) -> Optional[Dict[str, Any]]:
        with get_db_context() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                query = """
                SELECT n.*, i.*, a.d_o_b, a.d_o_d, a.age_at_death, p.pic_path AS picture_url
                FROM family_name n
                LEFT JOIN family_info i ON n.code = i.code_info
                LEFT JOIN family_age_search a ON n.code = a.code
                LEFT JOIN family_picture p ON n.code = p.code_pic
                WHERE n.code = %s;
                """
                cur.execute(query, (code,))
                row = cur.fetchone()
                if not row: return None
                
                member_data = dict(row)
                
                for key in ["d_o_b", "d_o_d"]:
                    if isinstance(member_data.get(key), date):
                        member_data[key] = member_data[key].isoformat()

                cur.execute("SELECT public.get_full_name(%s, NULL, TRUE) AS m_name", (member_data.get("m_code"),))
                m_res = cur.fetchone()
                mother_name = m_res["m_name"] if m_res else ""

                cur.execute("SELECT code, name FROM family_name WHERE f_code = %s OR m_code = %s", (code, code))
                children = cur.fetchall()

                cur.execute("SELECT public.get_full_name(%s, NULL, FALSE) AS display_name", (code,))
                display_name = cur.fetchone()["display_name"]
                
                gender = member_data.get("gender")
                if not gender and member_data.get("relation"):
                    rel = member_data["relation"]
                    if rel in ("ابن", "زوج", "ابن زوج", "ابن زوجة"):
                        gender = "ذكر"
                    elif rel in ("ابنة", "زوجة", "ابنة زوج", "ابنة زوجة"):
                        gender = "أنثى"
                    
                wives = []
                husbands = []
               
                if gender == "ذكر":
                    wife_ids = set()
                    if member_data.get("w_code"): wife_ids.add(member_data["w_code"])
                    
                    cur.execute("SELECT DISTINCT m_code FROM family_name WHERE f_code = %s AND m_code IS NOT NULL", (code,))
                    for r in cur.fetchall(): wife_ids.add(r["m_code"])
                    
                    cur.execute("SELECT code FROM family_name WHERE h_code = %s", (code,))
                    for r in cur.fetchall(): wife_ids.add(r["code"])
                    
                    for w_id in wife_ids:
                        if w_id and w_id.strip():
                            cur.execute("SELECT public.get_full_name(%s, NULL, TRUE) AS wife_name", (w_id,))
                            res = cur.fetchone()
                            if res: wives.append({"code": w_id, "name": res["wife_name"]})

                if gender == "أنثى":
                    husband_ids = set()
                    if member_data.get("h_code"): husband_ids.add(member_data["h_code"])
                    
                    cur.execute("SELECT DISTINCT f_code FROM family_name WHERE m_code = %s AND f_code IS NOT NULL", (code,))
                    for r in cur.fetchall(): husband_ids.add(r["f_code"])
                    
                    cur.execute("SELECT code FROM family_name WHERE w_code = %s", (code,))
                    for r in cur.fetchall(): husband_ids.add(r["code"])
                    
                    for h_id in husband_ids:
                        if h_id and h_id.strip():
                            cur.execute("SELECT public.get_full_name(%s, NULL, TRUE) AS husband_name", (h_id,))
                            res = cur.fetchone()
                            if res: husbands.append({"code": h_id, "name": res["husband_name"]})

                return {
                    "member": member_data,
                    "info": member_data,
                    "full_name": display_name,
                    "mother_name": mother_name,
                    "children": children,
                    "wives": wives,
                    "husbands": husbands,
                    "picture_url": member_data.get("picture_url"),
                    "gender": gender,
                    "nick_name": member_data.get("nick_name")
                }

    # ===============================================
    # 3. جلب البيانات للتعديل (Edit)
    # ===============================================
    @staticmethod
    def get_member_for_edit(code: str) -> Optional[Dict[str, Any]]:
        with get_db_context() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("SELECT * FROM family_name WHERE code = %s", (code,))
                member = cur.fetchone()
                if not member: return None
                
                cur.execute("""
                    SELECT fi.*, fas.d_o_b, fas.d_o_d 
                    FROM family_info fi
                    LEFT JOIN family_age_search fas ON fi.code_info = fas.code
                    WHERE fi.code_info = %s
                """, (code,))
                info = cur.fetchone() or {}

                for key in ["d_o_b", "d_o_d"]:
                    if isinstance(info.get(key), date):
                        info[key] = info[key].isoformat()

                cur.execute("SELECT pic_path FROM family_picture WHERE code_pic = %s", (code,))
                pic = cur.fetchone()
                
                return {
                    "member": member, 
                    "info": info, 
                    "picture_url": pic["pic_path"] if pic else None
                }

    # ===============================================
    # 4. الحذف
    # ===============================================
    @staticmethod
    def delete_member(code: str) -> None:
        with get_db_context() as conn:
            with conn.cursor() as cur:
                cur.execute("UPDATE family_name SET f_code = NULL WHERE f_code = %s", (code,))
                cur.execute("UPDATE family_name SET m_code = NULL WHERE m_code = %s", (code,))
                cur.execute("UPDATE family_name SET w_code = NULL WHERE w_code = %s", (code,))
                cur.execute("UPDATE family_name SET h_code = NULL WHERE h_code = %s", (code,))
                
                cur.execute("DELETE FROM family_picture WHERE code_pic = %s", (code,))
                cur.execute("DELETE FROM family_age_search WHERE code = %s", (code,))
                cur.execute("DELETE FROM family_info WHERE code_info = %s", (code,))
                cur.execute("DELETE FROM family_search WHERE code = %s", (code,))
                cur.execute("DELETE FROM family_name WHERE code = %s", (code,))
                
                conn.commit()

    # ===============================================
    # 5. الأدوات المساعدة (Utility)
    # ===============================================
    @staticmethod
    def get_next_code(prefix: str) -> str:
        prefix = prefix.upper().strip()
        search_prefix = prefix if prefix.endswith('-') else f"{prefix}-"
        with get_db_context() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("SELECT code FROM family_search WHERE code LIKE %s", (f"{search_prefix}%",))
                rows = cur.fetchall()
                if not rows: return f"{search_prefix}001"
                
                nums = []
                for r in rows:
                    try:
                        nums.append(int(r['code'].split('-')[-1]))
                    except: continue
                
                next_num = max(nums) + 1 if nums else 1
                return f"{search_prefix}{str(next_num).zfill(3)}"
            
    # ===============================================
    # 6. الإضافة (Create)
    # ===============================================
    @staticmethod
    def add_new_member(data: Dict[str, Any], picture_file: Optional[Any] = None, extension: Optional[str] = None) -> bool:
        FamilyService._ensure_upload_dir()
        
        # حماية إضافية على مستوى السيرفر لضمان تحويل الفراغات النصية إلى NULL حقيقي
        def clean_db_val(val):
            if val is None: return None
            if isinstance(val, str) and val.strip() == "": return None
            return val

        with get_db_context() as conn:
            with conn.cursor() as cur:
                try:
                    # 1. إدخال جدول الأسماء الأساسي
                    cur.execute("""
                        INSERT INTO family_name (code, name, f_code, m_code, w_code, h_code, relation, level, nick_name)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """, (
                        clean_db_val(data['code']), clean_db_val(data['name']), 
                        clean_db_val(data.get('f_code')), clean_db_val(data.get('m_code')),
                        clean_db_val(data.get('w_code')), clean_db_val(data.get('h_code')), 
                        clean_db_val(data.get('relation')), clean_db_val(data.get('level')), 
                        clean_db_val(data.get('nick_name'))
                    ))

                    # 2. إدخال جدول المعلومات الإضافية
                    cur.execute("""
                        INSERT INTO family_info (code_info, gender, email, phone, address, p_o_b, status)
                        VALUES (%s, %s, %s, %s, %s, %s, %s)
                        ON CONFLICT (code_info) DO UPDATE SET
                            gender = EXCLUDED.gender,
                            email = EXCLUDED.email,
                            phone = EXCLUDED.phone,
                            address = EXCLUDED.address,
                            p_o_b = EXCLUDED.p_o_b,
                            status = EXCLUDED.status
                    """, (
                        clean_db_val(data['code']), clean_db_val(data.get('gender')), clean_db_val(data.get('email')),
                        clean_db_val(data.get('phone')), clean_db_val(data.get('address')), clean_db_val(data.get('p_o_b')), 
                        clean_db_val(data.get('status'))
                    ))

                    # 3. 💡 [تصحيح حاسم] إدخال التواريخ بشكل دائم لمنع مشاكل الـ JOIN لاحقاً
                    dob_val = clean_db_val(data.get('d_o_b'))
                    dod_val = clean_db_val(data.get('d_o_d'))
                    
                    cur.execute("""
                        INSERT INTO family_age_search (code, d_o_b, d_o_d)
                        VALUES (%s, %s, %s)
                        ON CONFLICT (code) DO UPDATE SET
                            d_o_b = EXCLUDED.d_o_b,
                            d_o_d = EXCLUDED.d_o_d
                    """, (clean_db_val(data['code']), dob_val, dod_val))
                   
                    # 4. معالجة وحفظ الصورة الشخصية
                    if picture_file and picture_file.filename:
                        filename = f"{data['code']}{extension}"
                        file_path = os.path.join(FamilyService.UPLOAD_DIR, filename)
                        
                        with open(file_path, "wb") as buffer:
                            shutil.copyfileobj(picture_file.file, buffer)
                        
                        cur.execute("""
                            INSERT INTO family_picture (code_pic, pic_path)
                            VALUES (%s, %s)
                            ON CONFLICT (code_pic) DO UPDATE SET pic_path = EXCLUDED.pic_path
                        """, (data['code'], file_path))

                    conn.commit()
                    return True
                except Exception as e:
                    conn.rollback()
                    raise e

    # ===============================================
    # 7. Tالتعديل (Update)
    # ===============================================
    @staticmethod
    def update_member_data(code: str, data: Dict[str, Any], picture_file: Optional[Any] = None, extension: Optional[str] = None) -> bool:
        FamilyService._ensure_upload_dir()

        def clean_db_val(val):
            if val is None: return None
            if isinstance(val, str) and val.strip() == "": return None
            return val

        with get_db_context() as conn:
            with conn.cursor() as cur:
                try:
                    # 1. تحديث جدول family_name
                    cur.execute("""
                        UPDATE family_name 
                        SET name=%s, f_code=%s, m_code=%s, w_code=%s, h_code=%s, relation=%s, level=%s, nick_name=%s
                        WHERE code=%s
                    """, (
                        clean_db_val(data['name']), clean_db_val(data.get('f_code')), clean_db_val(data.get('m_code')), 
                        clean_db_val(data.get('w_code')), clean_db_val(data.get('h_code')), clean_db_val(data.get('relation')), 
                        clean_db_val(data.get('level')), clean_db_val(data.get('nick_name')), code
                    ))

                    # 2. تحديث جدول family_info
                    cur.execute("""
                        INSERT INTO family_info (code_info, gender, email, phone, address, p_o_b, status)
                        VALUES (%s, %s, %s, %s, %s, %s, %s)
                        ON CONFLICT (code_info) DO UPDATE SET
                            gender = EXCLUDED.gender, email = EXCLUDED.email,
                            phone = EXCLUDED.phone, address = EXCLUDED.address,
                            p_o_b = EXCLUDED.p_o_b, status = EXCLUDED.status
                    """, (code, clean_db_val(data["gender"]), clean_db_val(data["email"]), clean_db_val(data["phone"]), 
                        clean_db_val(data["address"]), clean_db_val(data["p_o_b"]), clean_db_val(data["status"])))
                            
                    # 3. تحديث التواريخ بأمان
                    cur.execute("""
                        INSERT INTO family_age_search (code, d_o_b, d_o_d)
                        VALUES (%s, %s, %s)
                        ON CONFLICT (code) DO UPDATE 
                        SET d_o_b = EXCLUDED.d_o_b, d_o_d = EXCLUDED.d_o_d
                    """, (code, clean_db_val(data.get('d_o_b')), clean_db_val(data.get('d_o_d'))))
                  
                    # 4. الصورة
                    if picture_file and picture_file.filename:
                        filename = f"{code}{extension}"
                        file_path = os.path.join(FamilyService.UPLOAD_DIR, filename)
                        with open(file_path, "wb") as buffer:
                            shutil.copyfileobj(picture_file.file, buffer)
                        
                        cur.execute("""
                            INSERT INTO family_picture (code_pic, pic_path)
                            VALUES (%s, %s)
                            ON CONFLICT (code_pic) DO UPDATE SET pic_path = EXCLUDED.pic_path
                        """, (code, file_path))

                    conn.commit()
                    return True
                except Exception as e:
                    conn.rollback()
                    raise e
    
    @staticmethod
    def is_code_exists(code: str) -> bool:
        """التحقق مما إذا كان الكود موجوداً بالفعل في قاعدة البيانات."""
        if not code or code.strip() == "": return False
        with get_db_context() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT 1 FROM family_name WHERE code = %s", (code.strip().upper(),))
                return cur.fetchone() is not None
    
    @staticmethod       
    def get_family_table_backup_text() -> str:
        """جلب بيانات الجدول كاملة بتنسيق نصي (SQL Style)."""
        with get_db_context() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT code, name, nick_name, f_code, m_code, relation, level, w_code, h_code 
                    FROM family_name 
                    ORDER BY code ASC
                """)
                rows = cur.fetchall()
                
                lines = []
                for row in rows:
                    formatted_values = []
                    for val in row:
                        if val is None:
                            formatted_values.append("NULL")
                        elif isinstance(val, int):
                            formatted_values.append(str(val))
                        else:
                            formatted_values.append(f"'{val}'")
                    
                    line = "(" + ", ".join(formatted_values) + "),"
                    lines.append(line)
                
                return "\n".join(lines)               

    @staticmethod
    def get_full_family_tree_recursive(code: str) -> List[Dict[str, Any]]:
        tree_data = {}

        def traverse(c, category="الشخص", depth=0):
            if not c: return
            with get_db_context() as conn:
                with conn.cursor(cursor_factory=RealDictCursor) as cur:
                    cur.execute("""
                        SELECT n.code, public.get_full_name(n.code, 4, FALSE) as full_name, 
                               n.nick_name, i.gender, n.relation, i.status,
                               n.f_code, n.m_code, n.w_code, n.h_code
                        FROM family_name n
                        LEFT JOIN family_info i ON n.code = i.code_info
                        WHERE n.code = %s
                    """, (c,))
                    member = cur.fetchone()
                    if not member or member['code'] in tree_data: return
                    
                    current_gender = member['gender']
                    if not current_gender and member['relation']:
                        rel = member['relation']
                        if rel in ("ابن", "زوج", "ابن زوج", "ابن زوجة"):
                            current_gender = "ذكر"
                        elif rel in ("ابنة", "زوجة", "ابنة زوج", "ابنة زوجة"):
                            current_gender = "أنثى"
                    
                    member['gender'] = current_gender
                    tree_data[member['code']] = {**member, "category": category}
                    
                    spouse_ids = set()
                    
                    if member.get("w_code"): spouse_ids.add(member["w_code"])
                    if member.get("h_code"): spouse_ids.add(member["h_code"])
                    
                    if current_gender == "ذكر":
                        cur.execute("SELECT DISTINCT m_code FROM family_name WHERE f_code = %s AND m_code IS NOT NULL", (c,))
                    else:
                        cur.execute("SELECT DISTINCT f_code FROM family_name WHERE m_code = %s AND f_code IS NOT NULL", (c,))
                    
                    for r in cur.fetchall():
                        val = r['m_code'] if current_gender == "ذكر" else r['f_code']
                        if val: spouse_ids.add(val)
                    
                    cur.execute("SELECT code FROM family_name WHERE w_code = %s OR h_code = %s", (c, c))
                    for r in cur.fetchall():
                        if r.get("code"): spouse_ids.add(r["code"])

                    for s_id in spouse_ids:
                        if s_id and s_id not in tree_data:
                            cur.execute("""
                                SELECT n.code, public.get_full_name(n.code, 4, FALSE) as full_name, 
                                       n.nick_name, i.gender, n.relation 
                                FROM family_name n
                                LEFT JOIN family_info i ON n.code = i.code_info
                                WHERE n.code = %s
                            """, (s_id,))
                            s_data = cur.fetchone()
                            
                            if s_data:
                                s_gender = s_data.get('gender') or ("أنثى" if current_gender == "ذكر" else "ذكر")
                                
                                if depth == 0:
                                    cat = "زوجة" if s_gender == "أنثى" else "زوج"
                                elif depth == 1:
                                    base = "ابن" if current_gender == "ذكر" else "ابنة"
                                    cat = (f"زوجة {base}") if s_gender == "أنثى" else (f"زوج {base}")
                                else:
                                    base = "حفيد" if current_gender == "ذكر" else "حفيدة"
                                    cat = (f"زوجة {base}") if s_gender == "أنثى" else (f"زوج {base}")
                                
                                tree_data[s_id] = {**s_data, "category": cat, "gender": s_gender}
                        
                    cur.execute("""
                        SELECT n.code, i.gender, n.relation
                        FROM family_name n
                        LEFT JOIN family_info i ON n.code = i.code_info
                        WHERE n.f_code = %s OR n.m_code = %s
                    """, (c, c))
                    children = cur.fetchall()
                    
                    for child in children:
                        ch_gender = child['gender']
                        if not ch_gender and child['relation']:
                            ch_gender = "ذكر" if child['relation'] == "ابن" else "أنثى"
                        ch_gender = ch_gender or "ذكر"
                        
                        if depth == 0:
                            base = "ابن" if ch_gender == "ذكر" else "ابنة"
                        elif depth == 1:
                            base = "حفيد" if ch_gender == "ذكر" else "حفيدة"
                        else:
                            is_from_female = (current_gender == "أنثى")
                            base = (f"ابن {'حفيدة' if is_from_female else 'حفيد'}") if ch_gender == "ذكر" else (f"ابنة {'حفيدة' if is_from_female else 'حفيد'}")
                        
                        traverse(child['code'], category=base, depth=depth + 1)

        traverse(code)
        return list(tree_data.values())