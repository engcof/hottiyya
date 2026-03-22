# family_service.py
import math
import os
import shutil 
import re # 💡 تمت إضافته للتعامل مع regexp إن لزم الأمر مستقبلاً
from typing import List, Dict, Optional, Tuple, Any
from psycopg2.extras import RealDictCursor
from psycopg2.extras import DictCursor
from datetime import date
# نفترض استيراد الدوال المساعدة والـ DB Context من ملفات أخرى
from utils.normalize import normalize_arabic
from postgresql import get_db_context

PAGE_SIZE = 24
UPLOAD_DIR = "static/uploads"
os.makedirs(UPLOAD_DIR, exist_ok=True)

# ===============================================
# 1. دوال جلب الأسماء والبحث (Show Names Logic)
# ===============================================

def get_total_name_count() -> int:
    """جلب العدد الكلي للأعضاء الذين لديهم مستوى >= 2 بدون بحث."""
    with get_db_context() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM family_search WHERE level >= 2")
            return cur.fetchone()[0]

def search_and_fetch_names(q: str, page: int) -> Tuple[List[Dict[str, Any]], int, int, int]:
    with get_db_context() as conn:
        with conn.cursor() as cur:
            phrase = q.strip()
            # توحيد النص للبحث
            normalized_input = normalize_arabic(phrase)
            search_term_like = f"%{normalized_input}%"
            
            # تحديد الشرط
            if re.fullmatch(r"[A-Z]\d{0,3}-\d{3}-\d{3}", phrase.upper()):
                sql_condition = "code = %s"
                count_params = (phrase.upper(),)
            elif "-" in phrase and len(phrase.split()) == 1:
                sql_condition = "code ILIKE %s"
                count_params = (f"%{phrase}%",)
            else:
                # تحسين: البحث في الاسم الموحد واللقب الموحد
                sql_condition = "(public.normalize_arabic(full_name) ILIKE %s OR public.normalize_arabic(nick_name) ILIKE %s)"
                count_params = (search_term_like, search_term_like)

            # إضافة شرط المستوى دائماً
            sql_condition += " AND level >= 0"

            # 1. جلب العدد الكلي
            cur.execute(f"SELECT COUNT(*) FROM family_search WHERE {sql_condition}", count_params)
            total_count = cur.fetchone()[0]
            
            # حسابات الترقيم (Pagination)
            totals_pages = math.ceil(total_count / PAGE_SIZE) if total_count > 0 else 1
            current_page = max(1, min(page, totals_pages))
            offset = (current_page - 1) * PAGE_SIZE
            
            # 2. جلب البيانات مع الفرز داخل SQL لضمان صحة الترقيم
            # لاحظ استخدام public.normalize_arabic في الـ ORDER BY
            cur.execute(f"""
                SELECT code, public.get_full_name(code, 7, FALSE) AS display_name, nick_name
                FROM family_search
                WHERE {sql_condition}
                ORDER BY public.normalize_arabic(full_name) ASC
                LIMIT %s OFFSET %s
            """, count_params + (PAGE_SIZE, offset))
            
            rows = cur.fetchall()

    # معالجة النتائج (بدون الحاجة لعمل sort في بايثون)
    members = [{
        "code": r[0],
        "full_name": r[1],
        "nick_name": r[2].strip() if r[2] else None
    } for r in rows]
    
    return members, current_page, totals_pages, total_count



def fetch_names_no_search(page: int) -> Tuple[List[Dict[str, Any]], int, int, int]:
    """جلب الأسماء بدون بحث مع الترقيم."""
    total_count = get_total_name_count()
    totals_pages = math.ceil(total_count / PAGE_SIZE) if total_count > 0 else 1
    current_page = min(page, totals_pages)
    if current_page < 1: current_page = 1
    offset = (current_page - 1) * PAGE_SIZE
    
    with get_db_context() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT code, public.get_full_name(code, 7, FALSE) AS full_name_display, nick_name, level
                FROM family_search 
                WHERE level >= 0
                ORDER BY full_name 
                LIMIT %s OFFSET %s
            """, (PAGE_SIZE, offset))
            rows = cur.fetchall()

    members = []
    for row in rows:
        code, display_name, nick_name, level = row
        clean_display_name = normalize_arabic(display_name)
        clean_nick_name = normalize_arabic(nick_name.strip()) if nick_name else None
        members.append({
            "code": code,
            "full_name": clean_display_name,
            "nick_name": clean_nick_name
        })
    members.sort(key=lambda x: x["full_name"])
    
    return members, current_page, totals_pages, total_count


# ===============================================
# 2. دالة جلب التفاصيل (Details Logic)
# ===============================================
def get_member_details(code: str) -> Optional[Dict[str, Any]]:
    with get_db_context() as conn:
        # استخدام DictCursor لجلب البيانات كقاموس
        with conn.cursor(cursor_factory=DictCursor) as cur:
            # 1. الاستعلام الشامل لجلب كل شيء (family_name, info, age, picture)
            query = """
            SELECT 
                n.*, i.*, a.d_o_b, a.d_o_d, a.age_at_death, p.pic_path AS picture_url
            FROM family_name n
            LEFT JOIN family_info i ON n.code = i.code_info
            LEFT JOIN family_age_search a ON n.code = a.code
            LEFT JOIN family_picture p ON n.code = p.code_pic
            WHERE n.code = %s;
            """
            cur.execute(query, (code,))
            row = cur.fetchone()

            if not row:
                return None
            
            info_data = dict(row)
            
            # -------------------------------------------------------------------
            # 2. معالجة التواريخ: تحويل كائن التاريخ إلى سلسلة نصية (str) بصيغة ISO
            # -------------------------------------------------------------------
            d_o_b_from_db = info_data.get("d_o_b")
            d_o_d_from_db = info_data.get("d_o_d")

            d_o_b_str = d_o_b_from_db.isoformat() if isinstance(d_o_b_from_db, date) else None
            d_o_d_str = d_o_d_from_db.isoformat() if isinstance(d_o_d_from_db, date) else None
            
            # -------------------------------------------------------------------
            # 3. جلب البيانات المشتقة والعلاقات
            # -------------------------------------------------------------------
            
            # الاسم الكامل (سلسلة الأجداد) بدون اللقب
            cur.execute("SELECT public.get_full_name(%s, NULL, FALSE) AS full_name", (code,))
            full_name_no_nick = cur.fetchone()["full_name"]
            
            # اللقب
            nick_value = info_data.get("nick_name")
            display_nick_name = (nick_value if nick_value is not None else "").strip()
            
            # الأم
            mother_full_name = ""
            if info_data.get("m_code"):
                 cur.execute("SELECT public.get_full_name(%s, NULL, TRUE) AS mother_name", (info_data["m_code"],))
                 mother_full_name = cur.fetchone()["mother_name"]

            # الجنس (الحساب التخميني إذا لم يكن مسجلاً)
            gender = info_data.get("gender")
            if not gender and info_data.get("relation"):
                rel = info_data["relation"]
                if rel in ("ابن", "زوج", "ابن زوج", "ابن زوجة"):
                    gender = "ذكر"
                elif rel in ("ابنة", "زوجة", "ابنة زوج", "ابنة زوجة"):
                    gender = "أنثى"
            
            # الأزواج/الزوجات
            wives = []
            husbands = []

            # جلب الزوجات إذا كان العضو ذكر
            if gender == "ذكر":
                wife_ids = set()
                
                # 1. الزوجة الحالية المسجلة مباشرة في بياناته (إذا كان لجدولك حقل w_code)
                current_w = info_data.get("w_code")
                if current_w:
                    wife_ids.add(current_w)
                
                # 2. الزوجات اللاتي أنجب منهن (عن طريق البحث عن أكواد الأمهات للأبناء المرتبطين به)
                cur.execute("SELECT DISTINCT m_code FROM family_name WHERE f_code = %s AND m_code IS NOT NULL", (code,))
                for r in cur.fetchall():
                    wife_ids.add(r["m_code"])

                # 3. البحث العكسي: أي أنثى مسجل في خانة زوجها (h_code) كود هذا الذكر
                cur.execute("SELECT code FROM family_name WHERE h_code = %s", (code,))
                for r in cur.fetchall():
                    wife_ids.add(r["code"])
                
                # جلب الأسماء النهائية للزوجات
                for w_id in wife_ids:
                    cur.execute("SELECT public.get_full_name(%s, NULL, TRUE) AS wife_name", (w_id,))
                    res = cur.fetchone()
                    if res:
                        wives.append({"code": w_id, "name": res["wife_name"]})
            
           # جلب الزوج/الأزواج إذا كان العضو أنثى 
            if gender == "أنثى":
                husband_ids = set()
                
                # 1. الزوج الحالي المسجل مباشرة في بياناتها
                current_h = info_data.get("h_code")
                if current_h:
                    husband_ids.add(current_h)
                
                # 2. الأزواج الذين أنجبت منهم (عن طريق الأبناء)
                cur.execute("SELECT DISTINCT f_code FROM family_name WHERE m_code = %s AND f_code IS NOT NULL", (code,))
                for r in cur.fetchall():
                    husband_ids.add(r["f_code"])

                # 3. الإضافة الهامة: البحث عن أي ذكر مسجل في النظام أن هذه الأنثى هي زوجته (حتى لو لم ينجبوا)
                # في بعض الأنظمة يكون الزوج مسجل في خانة h_code لدى الزوجة، وفي أنظمة أخرى العكس
                cur.execute("SELECT code FROM family_name WHERE code = (SELECT h_code FROM family_name WHERE code = %s)", (code,))
                # وأيضاً نبحث عن أي ذكر كود زوجته (w_code) هو كود هذه الأنثى
                cur.execute("SELECT code FROM family_name WHERE w_code = %s", (code,))
                for r in cur.fetchall():
                    husband_ids.add(r["code"])
                
                # جلب الأسماء النهائية
                for h_id in husband_ids:
                    cur.execute("SELECT public.get_full_name(%s, NULL, TRUE) AS husband_name", (h_id,))
                    res = cur.fetchone()
                    if res:
                        husbands.append({"code": h_id, "name": res["husband_name"]})
                
            # الأبناء
            cur.execute("SELECT code, name FROM family_name WHERE f_code = %s OR m_code = %s", (code, code))
            children = [{"code": r["code"], "name": r["name"]} for r in cur.fetchall()]

            # ----------------------------------------------------
            # 4. بناء قاموس الإرجاع النهائي
            # ----------------------------------------------------
            
            details = {
                "member": {
                    "code": code, "name": info_data.get("name"), 
                    "f_code": info_data.get("f_code"), "m_code": info_data.get("m_code"),
                    "w_code": info_data.get("w_code"), "h_code": info_data.get("h_code"), 
                    "relation": info_data.get("relation"), "level": info_data.get("level"), 
                    "nick_name": info_data.get("nick_name")
                },
                "info": {
                    "d_o_b": d_o_b_str,               # القيمة المحولة
                    "d_o_d": d_o_d_str,               # القيمة المحولة
                    "age_at_death": info_data.get("age_at_death"),
                    "email": info_data.get("email"),
                    "phone": info_data.get("phone"),
                    "address": info_data.get("address"),
                    "p_o_b": info_data.get("p_o_b"),
                    "status": info_data.get("status"),
                    "gender": info_data.get("gender")
                },
                "picture_url": info_data.get("picture_url"),
                "full_name": full_name_no_nick,
                "nick_name": display_nick_name,
                "mother_full_name": mother_full_name,
                "wives": wives,
                "husbands": husbands,
                "children": children,
                "gender": gender
            }
            
            return details

# ===============================================
# 3. دالة التحقق من الكود (Add/Edit Helper)
# ===============================================

def is_code_exists(code: str) -> bool:
    """التحقق مما إذا كان الكود موجوداً بالفعل في قاعدة البيانات."""
    with get_db_context() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT 1 FROM family_name WHERE code = %s", (code,))
            return cur.fetchone() is not None

# ===============================================
# 4. دالة الإضافة (Add Logic)
# ===============================================

def add_new_member(data: Dict[str, Any], picture: Optional[Any], ext: Optional[str]) -> None:
    """تنفيذ عملية إضافة عضو جديد."""
    
    code = data["code"]
    dob = data.get("d_o_b")
    dod = data.get("d_o_d")
    
    with get_db_context() as conn:
        with conn.cursor() as cur:
            # 1. إدخال family_name 
            cur.execute("""
                INSERT INTO family_name 
                (code, name, f_code, m_code, w_code, h_code, relation, level, nick_name)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            """, (data["code"], data["name"], data["f_code"], data["m_code"], data["w_code"], 
                  data["h_code"], data["relation"], data["level"], data["nick_name"]))

            # 2. إدخال family_info
            cur.execute("""
                INSERT INTO family_info 
                (code_info, gender, email, phone, address, p_o_b, status)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (code_info) DO NOTHING
            """, (code, data["gender"], data["email"], data["phone"], 
                  data["address"], data["p_o_b"], data["status"]))

            # 3. إدخال family_age_search (باستخدام ON CONFLICT)
            if dob or dod:
                cur.execute("""
                    INSERT INTO family_age_search 
                    (code, d_o_b, d_o_d)
                    VALUES (%s, %s, %s)
                    ON CONFLICT (code) DO UPDATE SET
                        d_o_b = EXCLUDED.d_o_b,
                        d_o_d = EXCLUDED.d_o_d,
                        updated_at = NOW()
                """, (code, dob, dod))
                
            # 4. حفظ الصورة
            if picture and picture.filename and ext:
                safe_filename = f"{code}{ext}"
                pic_path = os.path.join(UPLOAD_DIR, safe_filename)
                with open(pic_path, "wb") as f:
                    shutil.copyfileobj(picture.file, f)
                cur.execute("""
                    INSERT INTO family_picture (code_pic, pic_path) VALUES (%s, %s)
                    ON CONFLICT (code_pic) DO UPDATE SET pic_path = EXCLUDED.pic_path
                """, (code, pic_path))

            conn.commit()

# ===============================================
# 5. دالة التعديل (Edit Logic)
# ===============================================

def update_member_data(code: str, data: Dict[str, Any], picture: Optional[Any], ext: Optional[str]) -> None:
    """تنفيذ عملية تحديث بيانات عضو موجود."""
    
    dob = data.get("d_o_b")
    dod = data.get("d_o_d")
    
    with get_db_context() as conn:
        with conn.cursor() as cur:
            # 1. تحديث family_name
            cur.execute("""
                UPDATE family_name SET
                name=%s, f_code=%s, m_code=%s, w_code=%s, h_code=%s,
                relation=%s, level=%s, nick_name=%s
                WHERE code=%s
            """, (data["name"], data["f_code"], data["m_code"], data["w_code"], data["h_code"], 
                  data["relation"], data["level_int"], data["nick_name"], code)) # 💡 استخدام level_int

            # 2. تحديث family_info (باستخدام INSERT OR UPDATE لضمان وجود الصف)
            cur.execute("""
                INSERT INTO family_info (code_info, gender, email, phone, address, p_o_b, status)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (code_info) DO UPDATE SET
                    gender = EXCLUDED.gender, email = EXCLUDED.email,
                    phone = EXCLUDED.phone, address = EXCLUDED.address,
                    p_o_b = EXCLUDED.p_o_b, status = EXCLUDED.status
            """, (code, data["gender"], data["email"], data["phone"], 
                  data["address"], data["p_o_b"], data["status"]))
                      
            # 3. تحديث family_age_search (باستخدام ON CONFLICT)
            cur.execute("""
                INSERT INTO family_age_search (code, d_o_b, d_o_d)
                VALUES (%s, %s, %s)
                ON CONFLICT (code) DO UPDATE SET
                    d_o_b = EXCLUDED.d_o_b,
                    d_o_d = EXCLUDED.d_o_d,
                    updated_at = NOW()
            """, (code, dob, dod))
            # 4. تحديث الصورة 
            if picture and picture.filename and ext:
                safe_filename = f"{code}{ext}"
                pic_path = os.path.join(UPLOAD_DIR, safe_filename)
                with open(pic_path, "wb") as f:
                    shutil.copyfileobj(picture.file, f)
                cur.execute("""
                    INSERT INTO family_picture (code_pic, pic_path) VALUES (%s, %s)
                    ON CONFLICT (code_pic) DO UPDATE SET pic_path = EXCLUDED.pic_path
                """, (code, pic_path))

            conn.commit()

def get_member_for_edit(code: str) -> Optional[Dict[str, Any]]:
    """جلب بيانات العضو ومعلوماته وصورته للاستخدام في نموذج التعديل."""
    with get_db_context() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("SELECT * FROM family_name WHERE code = %s", (code,))
            member = cur.fetchone()

            if not member:
                return None
            
            # جلب family_info والتواريخ من family_age_search
            cur.execute("""
                SELECT 
                    fi.*, 
                    fas.d_o_b, 
                    fas.d_o_d 
                FROM family_info fi
                LEFT JOIN family_age_search fas ON fi.code_info = fas.code
                WHERE fi.code_info = %s
            """, (code,))
            info = cur.fetchone() or {}
            
            # 💡 معالجة التواريخ للتأكد من أنها سلاسل نصية (ISO format) إذا كانت موجودة
            if info.get("d_o_b") and isinstance(info["d_o_b"], date):
                info["d_o_b"] = info["d_o_b"].isoformat()
            if info.get("d_o_d") and isinstance(info["d_o_d"], date):
                info["d_o_d"] = info["d_o_d"].isoformat()

            cur.execute("SELECT pic_path FROM family_picture WHERE code_pic = %s", (code,))
            pic = cur.fetchone()
            picture_url = pic["pic_path"] if pic else None
            
    return {"member": member, "info": info, "picture_url": picture_url}
# ===============================================
# 6. دالة الحذف (Delete Logic)
# ===============================================

def delete_member(code: str) -> None:
    """حذف عضو من جميع الجداول ذات الصلة."""
    with get_db_context() as conn:
        with conn.cursor() as cur:
            # الحذف من جدول الصورة
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

def get_next_available_code(prefix_input: str) -> str:
    """جلب الكود التالي بناءً على البادئة (مثلاً A0-005)."""
    # تنظيف وتنسيق البادئة
    prefix = prefix_input.upper().strip()
    # نضمن أن البادئة تنتهي بشرطة للبحث الدقيق
    search_prefix = prefix if prefix.endswith('-') else f"{prefix}-"

    with get_db_context() as conn:
        with conn.cursor() as cur:
            # جلب كل الأكواد التي تبدأ بهذه البادئة لفرزها عددياً
            cur.execute("SELECT code FROM family_search WHERE code LIKE %s", (f"{search_prefix}%",))
            rows = cur.fetchall()

            if not rows:
                return f"{search_prefix}001"

            # استخراج الأرقام الأخيرة وتحويلها لـ int لضمان الترتيب الصحيح
            existing_numbers = []
            for row in rows:
                parts = row[0].split('-')
                if parts:
                    try:
                        existing_numbers.append(int(parts[-1]))
                    except (ValueError, IndexError): continue

            next_num = max(existing_numbers) + 1 if existing_numbers else 1
            return f"{search_prefix}{str(next_num).zfill(3)}"


def get_single_member_full_details(code: str) -> Optional[Dict[str, Any]]:
    """جلب تفاصيل شاملة لفرد واحد لغرض الطباعة الفردية."""
    # يمكننا إعادة استخدام دالة get_member_details الموجودة لديك أصلاً 
    # لأنها تعيد بالفعل كل ما نحتاجه (الأبناء، الأزواج، المعلومات الشخصية)
    return get_member_details(code)    

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
