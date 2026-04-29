# family_service.py
import math
import os
import shutil 
import re
from typing import List, Dict, Optional, Tuple, Any
from psycopg2.extras import RealDictCursor # 💡 تم اعتماد RealDictCursor للكل
from datetime import date

from rich.pretty import traverse
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
    def search_and_fetch_names(q: str, page: int) -> Tuple[List[Dict[str, Any]], int, int, int]:
        with get_db_context() as conn:
            # 💡 توحيد الـ Cursor هنا أيضاً
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                phrase = q.strip()
                normalized_input = normalize_arabic(phrase)
                search_term_like = f"%{normalized_input}%"
                
                # منطق تحديد نوع البحث
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

                # جلب العدد الكلي
                cur.execute(f"SELECT COUNT(*) FROM family_search WHERE {sql_condition}", count_params)
                total_count = cur.fetchone()['count'] # الوصول عبر المفتاح لأننا استخدمنا RealDictCursor
                
                totals_pages = math.ceil(total_count / FamilyService.PAGE_SIZE) if total_count > 0 else 1
                current_page = max(1, min(page, totals_pages))
                offset = (current_page - 1) * FamilyService.PAGE_SIZE
                
                # جلب البيانات
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
                # 1. جلب البيانات الأساسية
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
                
                # 2. معالجة التواريخ
                for key in ["d_o_b", "d_o_d"]:
                    if isinstance(member_data.get(key), date):
                        member_data[key] = member_data[key].isoformat()

               
                # 4. جلب الأم والأبناء والاسم الكامل
                cur.execute("SELECT public.get_full_name(%s, NULL, TRUE) AS m_name", (member_data.get("m_code"),))
                m_res = cur.fetchone()
                mother_name = m_res["m_name"] if m_res else ""

                cur.execute("SELECT code, name FROM family_name WHERE f_code = %s OR m_code = %s", (code, code))
                children = cur.fetchall()

                cur.execute("SELECT public.get_full_name(%s, NULL, FALSE) AS display_name", (code,))
                display_name = cur.fetchone()["display_name"]
                
                # 3. تحديد الجنس من العلاقة إذا كان الحقل فارغاً
                gender = member_data.get("gender")
                if not gender and member_data.get("relation"):
                    rel = member_data["relation"]
                    if rel in ("ابن", "زوج", "ابن زوج", "ابن زوجة"):
                        gender = "ذكر"
                    elif rel in ("ابنة", "زوجة", "ابنة زوج", "ابنة زوجة"):
                        gender = "أنثى"
                    
                wives = []
                husbands = []
               
                # 5. منطق الزوجات (للذكر)
                if gender == "ذكر":
                    wife_ids = set()
                    if member_data.get("w_code"): wife_ids.add(member_data["w_code"])
                    
                    cur.execute("SELECT DISTINCT m_code FROM family_name WHERE f_code = %s AND m_code IS NOT NULL", (code,))
                    for r in cur.fetchall(): wife_ids.add(r["m_code"])
                    
                    cur.execute("SELECT code FROM family_name WHERE h_code = %s", (code,))
                    for r in cur.fetchall(): wife_ids.add(r["code"])
                    
                    for w_id in wife_ids:
                        cur.execute("SELECT public.get_full_name(%s, NULL, TRUE) AS wife_name", (w_id,))
                        res = cur.fetchone()
                        if res: wives.append({"code": w_id, "name": res["wife_name"]})

                # 6. منطق الأزواج (للأنثى)
                if gender == "أنثى":
                    husband_ids = set()
                    if member_data.get("h_code"): husband_ids.add(member_data["h_code"])
                    
                    cur.execute("SELECT DISTINCT f_code FROM family_name WHERE m_code = %s AND f_code IS NOT NULL", (code,))
                    for r in cur.fetchall(): husband_ids.add(r["f_code"])
                    
                    cur.execute("SELECT code FROM family_name WHERE w_code = %s", (code,))
                    for r in cur.fetchall(): husband_ids.add(r["code"])
                    
                    for h_id in husband_ids:
                        cur.execute("SELECT public.get_full_name(%s, NULL, TRUE) AS husband_name", (h_id,))
                        res = cur.fetchone()
                        if res: husbands.append({"code": h_id, "name": res["husband_name"]})

                return {
                    "member": member_data,
                    "info": member_data, # لضمان التوافق مع القالب كما طلبنا سابقاً
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

                # تنسيق التاريخ للـ HTML Input (YYYY-MM-DD)
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
                # الحذف المتسلسل (يفضل وجود CASCADE في الـ DB ولكن هذا أضمن برمجياً)
                cur.execute("DELETE FROM family_picture WHERE code_pic = %s", (code,))
            
                # الحذف من جدول family_age_search
                cur.execute("DELETE FROM family_age_search WHERE code = %s", (code,))
                
                # الحذف من جدول family_info
                cur.execute("DELETE FROM family_info WHERE code_info = %s", (code,))
                
                # الحذف من جدول family_search
                cur.execute("DELETE FROM family_search WHERE code = %s", (code,)) 
                
                # الحذف من جدول family_name (يجب أن يكون هذا آخر شيء أو يتم التعامل معه بـ CASCADE)
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
                        # r['code'] لأننا استخدمنا RealDictCursor
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
        
        with get_db_context() as conn:
            with conn.cursor() as cur:
                try:
                    cur.execute("""
                        INSERT INTO family_name (code, name, f_code, m_code, w_code, h_code, relation, level, nick_name)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """, (
                        data['code'], data['name'], data.get('f_code'), data.get('m_code'),
                        data.get('w_code'), data.get('h_code'), data.get('relation'), 
                        data.get('level'), data.get('nick_name') # 👈 أضفناه هنا
                    ))

                    # 2. إدخال في family_info (احذفه من هنا إذا لم تنفذ أمر ALTER TABLE)
                    # في الجزء الخاص بـ family_info
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
                        data['code'], data.get('gender'), data.get('email'),
                        data.get('phone'), data.get('address'), data.get('p_o_b'), data.get('status')
                    ))

                    # 3. إدخال التواريخ في family_age_search (إذا وجدت)
                    dob_val = data.get('d_o_b')
                    dod_val = data.get('d_o_d')

                    if (dob_val and dob_val.strip()) or (dod_val and dod_val.strip()):
                        cur.execute("""
                            INSERT INTO family_age_search (code, d_o_b, d_o_d)
                            VALUES (%s, %s, %s)
                        """, (
                            data['code'], 
                            dob_val if dob_val else None, 
                            dod_val if dod_val else None
                        ))
                   
                    # 4. معالجة الصورة
                    if picture_file and picture_file.filename:
                        filename = f"{data['code']}{extension}"
                        file_path = os.path.join(FamilyService.UPLOAD_DIR, filename)
                        
                        # حفظ الملف فعلياً
                        with open(file_path, "wb") as buffer:
                            shutil.copyfileobj(picture_file.file, buffer)
                        
                        # تسجيل المسار في القاعدة
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
    # 7. التعديل (Update)
    # ===============================================
    @staticmethod
    def update_member_data(code: str, data: Dict[str, Any], picture_file: Optional[Any] = None, extension: Optional[str] = None) -> bool:
        FamilyService._ensure_upload_dir()

        with get_db_context() as conn:
            with conn.cursor() as cur:
                try:
                    # 1. تحديث جدول family_name (أضفنا nick_name هنا لأنه موجود في هذا الجدول)
                    cur.execute("""
                        UPDATE family_name 
                        SET name=%s, f_code=%s, m_code=%s, w_code=%s, h_code=%s, relation=%s, level=%s, nick_name=%s
                        WHERE code=%s
                    """, (
                        data['name'], data.get('f_code'), data.get('m_code'), 
                        data.get('w_code'), data.get('h_code'), data.get('relation'), 
                        data.get('level'), data.get('nick_name'), code
                    ))

                    # 2. تحديث جدول family_info (بدون nick_name إلا إذا أضفته للقاعدة)
                    cur.execute("""
                        INSERT INTO family_info (code_info, gender, email, phone, address, p_o_b, status)
                        VALUES (%s, %s, %s, %s, %s, %s, %s)
                        ON CONFLICT (code_info) DO UPDATE SET
                            gender = EXCLUDED.gender, email = EXCLUDED.email,
                            phone = EXCLUDED.phone, address = EXCLUDED.address,
                            p_o_b = EXCLUDED.p_o_b, status = EXCLUDED.status
                    """, (code, data["gender"], data["email"], data["phone"], 
                        data["address"], data["p_o_b"], data["status"]))
                            

                    # 3. تحديث التواريخ (ON CONFLICT ضرورية هنا لأن بعض الأعضاء القدامى قد لا يملكون سجلاً في هذا الجدول)
                    cur.execute("""
                        INSERT INTO family_age_search (code, d_o_b, d_o_d)
                        VALUES (%s, %s, %s)
                        ON CONFLICT (code) DO UPDATE 
                        SET d_o_b = EXCLUDED.d_o_b, d_o_d = EXCLUDED.d_o_d
                    """, (code, data.get('d_o_b'), data.get('d_o_d')))
                  
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
        with get_db_context() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT 1 FROM family_name WHERE code = %s", (code,))
                return cur.fetchone() is not None
    
    @staticmethod       
    def get_family_table_backup_text() -> str:
        """جلب بيانات الجدول كاملة بتنسيق نصي (SQL Style)."""
        with get_db_context() as conn:
            with conn.cursor() as cur:
                # جلب الأعمدة بنفس ترتيب مثالك
                cur.execute("""
                    SELECT code, name, nick_name, f_code, m_code, relation, level, w_code, h_code 
                    FROM family_name 
                    ORDER BY code ASC
                """)
                rows = cur.fetchall()
                
                lines = []
                for row in rows:
                    # تحويل القيم لضمان التعامل مع الـ NULL والنصوص بشكل صحيح
                    formatted_values = []
                    for val in row:
                        if val is None:
                            formatted_values.append("NULL")
                        elif isinstance(val, int):
                            formatted_values.append(str(val))
                        else:
                            # وضع النصوص بين علامات تنصيص مفردة
                            formatted_values.append(f"'{val}'")
                    
                    # دمج القيم لتصبح على شكل ('val1', 'val2', ...)
                    line = "(" + ", ".join(formatted_values) + "),"
                    lines.append(line)
                
                return "\n".join(lines)               

    @staticmethod
    def get_full_family_tree_recursive(code: str) -> List[Dict[str, Any]]:
        tree_data = {}

        def traverse(c, category="الشخص الأساسي", depth=0):
            with get_db_context() as conn:
                with conn.cursor(cursor_factory=RealDictCursor) as cur:
                    # 1. جلب بيانات العضو الحالي
                    cur.execute("""
                        SELECT n.code, public.get_full_name(n.code, 4, FALSE) as full_name, 
                               n.nick_name, i.gender, n.relation 
                        FROM family_name n
                        LEFT JOIN family_info i ON n.code = i.code_info
                        WHERE n.code = %s
                    """, (c,))
                    member = cur.fetchone()
                    if not member or member['code'] in tree_data: return
                    
                    tree_data[member['code']] = {**member, "category": category}
                    
                    # 2. جلب الأزواج (تم تعديله ليجلب الاسم الرباعي)
                    cur.execute("""
                        SELECT n.code, public.get_full_name(n.code, 4, FALSE) as full_name, 
                               n.nick_name, i.gender, n.relation 
                        FROM family_name n
                        LEFT JOIN family_info i ON n.code = i.code_info
                        WHERE n.w_code = %s OR n.h_code = %s
                    """, (c, c))
                    spouses = cur.fetchall()
                    for s in spouses:
                        if s['code'] not in tree_data:
                            spouse_gender = s.get('gender', 'ذكر')
                            # تحديد المسمى
                            if depth == 0:
                                cat = "زوجة" if spouse_gender == "أنثى" else "زوج"
                            elif depth == 1:
                                parent_gender = member.get('gender')
                                base = "ابن" if parent_gender == "ذكر" else "ابنة"
                                cat = (f"زوجة {base}") if spouse_gender == "أنثى" else (f"زوج {base}")
                            else:
                                parent_gender = member.get('gender')
                                base = "حفيد" if parent_gender == "ذكر" else "حفيدة"
                                cat = (f"زوجة {base}") if spouse_gender == "أنثى" else (f"زوج {base}")
                            tree_data[s['code']] = {**s, "category": cat}
                        
                    # 3. جلب الأبناء (تم تصحيح الهيكل)
                    cur.execute("""
                        SELECT n.code, i.gender 
                        FROM family_name n
                        LEFT JOIN family_info i ON n.code = i.code_info
                        WHERE n.f_code = %s OR n.m_code = %s
                    """, (c, c))
                    children = cur.fetchall()
                    
                    for child in children:
                        gender = child['gender'] or "ذكر"
                        
                        # تحديد المسمى بدقة حسب الجيل والجنس
                        if depth == 0:
                            base = "ابن" if gender == "ذكر" else "ابنة"
                        elif depth == 1:
                            base = "حفيد" if gender == "ذكر" else "حفيدة"
                        else:
                            # التمييز بين حفيد وحفيدة
                            is_granddaughter = (member.get('gender') == "أنثى")
                            if is_granddaughter:
                                base = "ابن حفيدة" if gender == "ذكر" else "ابنة حفيدة"
                            else:
                                base = "ابن حفيد" if gender == "ذكر" else "ابنة حفيد"
                        
                        traverse(child['code'], category=base, depth=depth + 1)

        traverse(code)
        return list(tree_data.values())