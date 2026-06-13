import math
import os
import shutil 
import re
import socket
import httplib2
import io
import logging  # 💡 تم إضافته لعمل الـ logger
from datetime import date, datetime # 💡 تم إضافة datetime هنا
from typing import List, Dict, Optional, Tuple, Any
from psycopg2.extras import RealDictCursor 
import html

from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
import google_auth_httplib2
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload

from utils.normalize import normalize_arabic
from postgresql import get_db_context

# إعداد لورجر محلي للدالة في حال لم يكن لديك لورجر عام ممرر
logger = logging.getLogger(__name__)

# إجبار النظام على استخدام IPv4 فقط لاتصالات Google API لضمان الاستقرار في Render
orig_getaddrinfo = socket.getaddrinfo
def getaddrinfo_ipv4(host, port, family=0, type=0, proto=0, flags=0):
    return orig_getaddrinfo(host, port, socket.AF_INET, type, proto, flags)
socket.getaddrinfo = getaddrinfo_ipv4

class FamilyService:
    PAGE_SIZE = 24
    MAX_TREE_DEPTH = 10  # حد أقصى لمنع الانهيار في الدوال العودية
    SCOPES = ['https://www.googleapis.com/auth/drive.file']
    TOKEN_FILE = 'token.json'
    
    # 🔒 جلب معرف مجلد صور العائلة بأمان من ملف .env
    GOOGLE_DRIVE_FOLDER_ID = os.getenv("GOOGLE_DRIVE_FAMILY_PICS_ID")

    @staticmethod
    def get_drive_service():
        """بناء خدمة الاتصال بقوقل درايف لرفع صور الأعضاء"""
        if not os.path.exists(FamilyService.TOKEN_FILE):
            raise FileNotFoundError(f"ملف الصلاحيات {FamilyService.TOKEN_FILE} غير موجود!")

        creds = Credentials.from_authorized_user_file(FamilyService.TOKEN_FILE, FamilyService.SCOPES)
        
        if creds.expired and creds.refresh_token:
            creds.refresh(Request())
            with open(FamilyService.TOKEN_FILE, 'w') as token:
                token.write(creds.to_json())
        
        http_transport = httplib2.Http(timeout=120)
        http_transport.follow_redirects = False 
        
        authorized_http = google_auth_httplib2.AuthorizedHttp(creds, http=http_transport)
        DRIVE_DISCOVERY_URL = 'https://www.googleapis.com/discovery/v1/apis/drive/v3/rest'
        
        return build(
            'drive', 
            'v3', 
            http=authorized_http, 
            discoveryServiceUrl=DRIVE_DISCOVERY_URL,
            static_discovery=False
        )

    @classmethod
    async def upload_member_picture(cls, file_data: bytes, filename: str, content_type: str) -> Optional[str]:
        """رفع الصورة مباشرة إلى مجلد family pic في قوقل درايف"""
        try:
            if not cls.GOOGLE_DRIVE_FOLDER_ID:
                print("خطأ: لم يتم ضبط متغير البيئة GOOGLE_DRIVE_FAMILY_PICS_ID")
                return None

            service = cls.get_drive_service()
            
            file_metadata = {
                'name': filename,
                'parents': [cls.GOOGLE_DRIVE_FOLDER_ID]
            }
            
            media = MediaIoBaseUpload(io.BytesIO(file_data), mimetype=content_type, resumable=True)
            
            file = service.files().create(
                body=file_metadata,
                media_body=media,
                fields='id'
            ).execute()
            
            # جعل الصورة عامة (Public) ليتم عرضها في المتصفح فوراً
            try:
                service.permissions().create(
                    fileId=file.get('id'),
                    body={'type': 'anyone', 'role': 'reader'}
                ).execute()
            except Exception as perm_err:
                print(f"تحذير أثناء جعل الصورة عامة: {perm_err}")

            return file.get('id')
            
        except Exception as e:
            print(f"خطأ أثناء رفع الصورة إلى Google Drive: {e}")
            return None

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
                
                if re.fullmatch(r"^[A-Z]\d{1,3}-\d{3}-\d{3}$", phrase.upper()):
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
    # 2. جلب التفاصيل الشاملة (تعديل جلب مسار الصورة)
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
                cur.execute(query, (code.strip().upper(),))
                row = cur.fetchone()
                if not row: return None
                
                # ✅ التعديل الصحيح والمؤمن:
                member_data = dict(row)

                # تحويل الـ Google Drive ID إلى رابط عرض مباشر متاح للمتصفح
                raw_pic_path = member_data.get("picture_url")
                google_drive_url = None

                if raw_pic_path:
                    # تنظيف المعرف من أي مسارات كاملة إن وجدت
                    drive_id = raw_pic_path.strip()
                    if "id=" in drive_id:
                        drive_id = drive_id.split("id=")[-1]
                    elif "/" in drive_id:
                        drive_id = drive_id.split("/")[-1]
                    
                    # صياغة الرابط المباشر عالي الأداء المخصص لوسم الـ img 
                    google_drive_url = f"https://drive.google.com/thumbnail?id={drive_id}&sz=w500"
                
                # تحديثها داخل البيانات الأساسية أيضاً لضمان قراءتها من أي مكان بالقالب
                member_data["picture_url"] = google_drive_url
                                
                for key in ["d_o_b", "d_o_d"]:
                    if isinstance(member_data.get(key), date):
                        member_data[key] = member_data[key].isoformat()

                cur.execute("SELECT public.get_full_name(%s, NULL, TRUE) AS m_name", (member_data.get("m_code"),))
                m_res = cur.fetchone()
                mother_name = m_res["m_name"] if m_res else ""

                # جلب اسم الأب الكامل لعرضه في لوحة العلاقات الأسرية الجديدة
                cur.execute("SELECT public.get_full_name(%s, NULL, TRUE) AS f_name", (member_data.get("f_code"),))
                f_res = cur.fetchone()
                father_name = f_res["f_name"] if f_res else ""

                cur.execute("SELECT code, name FROM family_name WHERE f_code = %s OR m_code = %s", (code, code))
                children = cur.fetchall()

                cur.execute("SELECT public.get_full_name(%s, NULL, FALSE) AS display_name", (code,))
                display_name = cur.fetchone()["display_name"]
                
                gender = member_data.get("gender")
                if not gender and member_data.get("relation"):
                    rel = member_data["relation"]
                    if rel in ("ابن", "زوج", "ابن زوج", "ابن زوجة"): gender = "ذكر"
                    elif rel in ("ابنة", "زوجة", "ابنة زوج", "ابنة زوجة"): gender = "أنثى"
                    
                wives = []
                husbands = []
               
                if gender == "ذكر":
                    wife_ids = set()
                    if member_data.get("w_code"): wife_ids.add(member_data["w_code"])
                    
                    cur.execute("SELECT DISTINCT m_code FROM family_name WHERE f_code = %s AND m_code IS NOT NULL", (code,))
                    for r in cur.fetchall(): wife_ids.add(r["m_code"])
                    
                    cur.execute("SELECT code FROM family_name WHERE h_code = %s", (code,))
                    for r in cur.fetchall(): wife_ids.add(r["code"])
                    
                    clean_wives = [w for w in wife_ids if w and w.strip()]
                    if clean_wives:
                        cur.execute("SELECT code, public.get_full_name(code, NULL, TRUE) AS wife_name FROM family_name WHERE code = ANY(%s)", (clean_wives,))
                        for r in cur.fetchall():
                            wives.append({"code": r["code"], "name": r["wife_name"]})

                if gender == "أنثى":
                    husband_ids = set()
                    if member_data.get("h_code"): husband_ids.add(member_data["h_code"])
                    
                    cur.execute("SELECT DISTINCT f_code FROM family_name WHERE m_code = %s AND f_code IS NOT NULL", (code,))
                    for r in cur.fetchall(): husband_ids.add(r["f_code"])
                    
                    cur.execute("SELECT code FROM family_name WHERE w_code = %s", (code,))
                    for r in cur.fetchall(): husband_ids.add(r["f_code"])
                    
                    clean_husbands = [h for h in husband_ids if h and h.strip()]
                    if clean_husbands:
                        cur.execute("SELECT code, public.get_full_name(code, NULL, TRUE) AS husband_name FROM family_name WHERE code = ANY(%s)", (clean_husbands,))
                        for r in cur.fetchall():
                            husbands.append({"code": r["code"], "name": r["husband_name"]})

                return {
                    "member": member_data, "info": member_data, "full_name": display_name,
                    "mother_name": mother_name, "father_full_name": father_name, "children": children, 
                    "wives": wives, "husbands": husbands, "picture_url": google_drive_url , 
                    "gender": gender, "nick_name": member_data.get("nick_name")
                }

    # ===============================================
    # 3. جلب البيانات للتعديل (تعديل صياغة مسار الصورة المباشر)
    # ===============================================
    @staticmethod
    def get_member_for_edit(code: str) -> Optional[Dict[str, Any]]:
        with get_db_context() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("SELECT * FROM family_name WHERE code = %s", (code.strip().upper(),))
                member = cur.fetchone()
                if not member: return None
                
                cur.execute("""
                    SELECT fi.*, fas.d_o_b, fas.d_o_d 
                    FROM family_info fi
                    LEFT JOIN family_age_search fas ON fi.code_info = fas.code
                    WHERE fi.code_info = %s
                """, (code.strip().upper(),))
                info = cur.fetchone() or {}

                for key in ["d_o_b", "d_o_d"]:
                    if isinstance(info.get(key), date):
                        info[key] = info[key].isoformat()

                cur.execute("SELECT pic_path FROM family_picture WHERE code_pic = %s", (code.strip().upper(),))
                pic = cur.fetchone()
                
                # ✅ صياغة الرابط المباشر للـ Drive ليعمل بالمتصفح فوراً
                google_drive_url = None
                if pic and pic.get("pic_path"):
                    raw_path = pic["pic_path"].strip()
                    if "id=" in raw_path:
                        drive_id = raw_path.split("id=")[-1]
                    elif "/" in raw_path:
                        drive_id = raw_path.split("/")[-1]
                    else:
                        drive_id = raw_path
                    google_drive_url = f"https://drive.google.com/thumbnail?id={drive_id}&sz=w500"
                
                return {
                    "member": member, "info": info, "picture_url": google_drive_url
                }
    # ===============================================
    # 4. الحذف الآمن والمسح النهائي من Google Drive
    # ===============================================
    @staticmethod
    def delete_member(code: str) -> None:
        clean_code = code.strip().upper()
        with get_db_context() as conn:
            with conn.cursor() as cur:
                # 🔒 جلب معرف ملف الصورة من درايف لحذفه سحابياً لمنع تراكم الملفات المهملة
                cur.execute("SELECT pic_path FROM family_picture WHERE code_pic = %s", (clean_code,))
                pic_row = cur.fetchone()
                if pic_row and pic_row[0]:
                    drive_file_id = pic_row[0]
                    try:
                        drive_service = FamilyService.get_drive_service()
                        drive_service.files().delete(fileId=drive_file_id).execute()
                    except Exception as e:
                        print(f"⚠️ تفادي خطأ أثناء حذف الصورة من Google Drive: {e}")

                # تصفير العلاقات لعدم كسر تكامل البيانات الـ Foreign Keys
                cur.execute("UPDATE family_name SET f_code = NULL WHERE f_code = %s", (clean_code,))
                cur.execute("UPDATE family_name SET m_code = NULL WHERE m_code = %s", (clean_code,))
                cur.execute("UPDATE family_name SET w_code = NULL WHERE w_code = %s", (clean_code,))
                cur.execute("UPDATE family_name SET h_code = NULL WHERE h_code = %s", (clean_code,))
                
                # مسح السجلات من الجداول الفرعية والأصلية
                cur.execute("DELETE FROM family_picture WHERE code_pic = %s", (clean_code,))
                cur.execute("DELETE FROM family_age_search WHERE code = %s", (clean_code,))
                cur.execute("DELETE FROM family_info WHERE code_info = %s", (clean_code,))
                cur.execute("DELETE FROM family_search WHERE code = %s", (clean_code,))
                cur.execute("DELETE FROM family_name WHERE code = %s", (clean_code,))
                
                conn.commit()

    # ===============================================
    # 5. الأدوات المساعدة وحماية الأكواد التلقائية
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
                        parts = r['code'].split('-')
                        if parts and parts[-1].isdigit():
                            nums.append(int(parts[-1]))
                    except: continue
                
                next_num = max(nums) + 1 if nums else 1
                return f"{search_prefix}{str(next_num).zfill(3)}"
            
   # ===============================================
    # 6. إضافة عضو جديد مع رفع الصورة إلى Google Drive
    # ===============================================
    @staticmethod
    def add_new_member(data: Dict[str, Any], picture_file: Optional[Any] = None, extension: Optional[str] = None) -> bool:
        def clean_db_val(val):
            if val is None: return None
            if isinstance(val, str) and val.strip() == "": return None
            return val

        clean_code = clean_db_val(data['code']).strip().upper()

        with get_db_context() as conn:
            with conn.cursor() as cur:
                try:
                    # 1. إدخال البيانات الأساسية في جدول الأسماء
                    cur.execute("""
                        INSERT INTO family_name (code, name, f_code, m_code, w_code, h_code, relation, level, nick_name)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """, (
                        clean_code, clean_db_val(data['name']), 
                        clean_db_val(data.get('f_code')), clean_db_val(data.get('m_code')),
                        clean_db_val(data.get('w_code')), clean_db_val(data.get('h_code')), 
                        clean_db_val(data.get('relation')), clean_db_val(data.get('level')), 
                        clean_db_val(data.get('nick_name'))
                    ))

                    # 2. إدخال أو تحديث البيانات الشخصية
                    cur.execute("""
                        INSERT INTO family_info (code_info, gender, email, phone, address, p_o_b, status)
                        VALUES (%s, %s, %s, %s, %s, %s, %s)
                        ON CONFLICT (code_info) DO UPDATE SET
                            gender = EXCLUDED.gender, email = EXCLUDED.email, phone = EXCLUDED.phone,
                            address = EXCLUDED.address, p_o_b = EXCLUDED.p_o_b, status = EXCLUDED.status
                    """, (
                        clean_code, clean_db_val(data.get('gender')), clean_db_val(data.get('email')),
                        clean_db_val(data.get('phone')), clean_db_val(data.get('address')), clean_db_val(data.get('p_o_b')), 
                        clean_db_val(data.get('status'))
                    ))

                    # 3. إدخال أو تحديث التواريخ
                    cur.execute("""
                        INSERT INTO family_age_search (code, d_o_b, d_o_d)
                        VALUES (%s, %s, %s)
                        ON CONFLICT (code) DO UPDATE SET d_o_b = EXCLUDED.d_o_b, d_o_d = EXCLUDED.d_o_d
                    """, (clean_code, clean_db_val(data.get('d_o_b')), clean_db_val(data.get('d_o_d'))))
                   
                    # 🚀 4. معالجة رفع الصورة إلى Google Drive 
                    # تم تدعيم الشرط بـ (strip) للتأكد من أن اسم الملف ليس فراغات مخفية
                    if picture_file and picture_file.filename and picture_file.filename.strip() != "" and extension:
                        
                        # قراءة الملف من الذاكرة مباشرة
                        file_bytes = picture_file.file.read()
                        
                        # الحماية الحديدية: التأكد من أن الملف يحتوي على بيانات فعلاً (أكبر من 0 بايت)
                        if file_bytes and len(file_bytes) > 0:
                            
                            # تصحيح تصفية الامتداد ليقبل الحروف والأرقام والنقطة فقط بشكل سليم
                            safe_ext = re.sub(r'[^a-zA-Z0-9.]', '', extension)
                            filename = f"{clean_code}{safe_ext}"
                            content_type = picture_file.content_type or "image/jpeg"
                            
                            # جلب خدمة قوقل درايف النظيفة والمباشرة
                            drive_service = FamilyService.get_drive_service() 
                            
                            # إعداد الميتا داتا وتجهيز الرفع السحابي
                            file_metadata = {
                                'name': filename, 
                                'parents': [FamilyService.GOOGLE_DRIVE_FOLDER_ID]
                            }
                            media = MediaIoBaseUpload(io.BytesIO(file_bytes), mimetype=content_type, resumable=True)
                            
                            # تنفيذ عملية الرفع الفعلي واستخراج معرف الملف الـ ID
                            drive_file = drive_service.files().create(
                                body=file_metadata, 
                                media_body=media, 
                                fields='id'
                            ).execute()
                            
                            drive_file_id = drive_file.get('id')
                            
                            # تعديل الصلاحيات لجعل الملف قابلاً للعرض العام
                            if drive_file_id:
                                try:
                                    drive_service.permissions().create(
                                        fileId=drive_file_id, 
                                        body={'type': 'anyone', 'role': 'reader'}
                                    ).execute()
                                except Exception:
                                    pass 
                            
                                # حفظ الـ Google Drive ID في جدول الصور الخاص بالقاعدة
                                cur.execute("""
                                    INSERT INTO family_picture (code_pic, pic_path)
                                    VALUES (%s, %s)
                                    ON CONFLICT (code_pic) DO UPDATE SET pic_path = EXCLUDED.pic_path
                                """, (clean_code, drive_file_id))

                    conn.commit()
                    return True
                except Exception as e:
                    conn.rollback()
                    raise e
# ===============================================
    # 7. تعديل وتحديث البيانات على السحابة ديركت
    # ===============================================
    @staticmethod
    def update_member_data(code: str, data: Dict[str, Any], picture_file: Optional[Any] = None, extension: Optional[str] = None) -> bool:
        def clean_db_val(val):
            if val is None: return None
            if isinstance(val, str) and val.strip() == "": return None
            return val

        clean_code = code.strip().upper()

        with get_db_context() as conn:
            with conn.cursor() as cur:
                try:
                    cur.execute("""
                        UPDATE family_name 
                        SET name=%s, f_code=%s, m_code=%s, w_code=%s, h_code=%s, relation=%s, level=%s, nick_name=%s
                        WHERE code=%s
                    """, (
                        clean_db_val(data['name']), clean_db_val(data.get('f_code')), clean_db_val(data.get('m_code')), 
                        clean_db_val(data.get('w_code')), clean_db_val(data.get('h_code')), clean_db_val(data.get('relation')), 
                        clean_db_val(data.get('level')), clean_db_val(data.get('nick_name')), clean_code
                    ))

                    cur.execute("""
                        INSERT INTO family_info (code_info, gender, email, phone, address, p_o_b, status)
                        VALUES (%s, %s, %s, %s, %s, %s, %s)
                        ON CONFLICT (code_info) DO UPDATE SET
                            gender = EXCLUDED.gender, email = EXCLUDED.email, phone = EXCLUDED.phone,
                            address = EXCLUDED.address, p_o_b = EXCLUDED.p_o_b, status = EXCLUDED.status
                    """, (clean_code, clean_db_val(data["gender"]), clean_db_val(data["email"]), clean_db_val(data["phone"]), 
                        clean_db_val(data["address"]), clean_db_val(data["p_o_b"]), clean_db_val(data["status"])))
                            
                    cur.execute("""
                        INSERT INTO family_age_search (code, d_o_b, d_o_d)
                        VALUES (%s, %s, %s)
                        ON CONFLICT (code) DO UPDATE SET d_o_b = EXCLUDED.d_o_b, d_o_d = EXCLUDED.d_o_d
                    """, (clean_code, clean_db_val(data.get('d_o_b')), clean_db_val(data.get('d_o_d'))))
                  
                    # تحديث الصورة في درايف عند رفع صورة جديدة فعلية وغير فارغة
                    if picture_file and picture_file.filename and picture_file.filename.strip() != "" and extension:
                        
                        file_bytes = picture_file.file.read()
                        
                        # 🔒 حماية المساحة: لا تنفذ التعديل السحابي إلا لو كان الملف يحتوي على بيانات
                        if file_bytes and len(file_bytes) > 0:
                            
                            # حذف الصورة القديمة من درايف إن وجدت لتوفير المساحة أولاً بأول
                            cur.execute("SELECT pic_path FROM family_picture WHERE code_pic = %s", (clean_code,))
                            old_pic = cur.fetchone()
                            if old_pic and old_pic[0]:
                                try:
                                    drive_service = FamilyService.get_drive_service()
                                    drive_service.files().delete(fileId=old_pic[0]).execute()
                                except: pass

                            safe_ext = re.sub(r'[^a-zA-Z0-9.]', '', extension)
                            filename = f"{clean_code}{safe_ext}"
                            content_type = picture_file.content_type or "image/jpeg"
                            
                            drive_service = FamilyService.get_drive_service()
                            file_metadata = {'name': filename, 'parents': [FamilyService.GOOGLE_DRIVE_FOLDER_ID]}
                            media = MediaIoBaseUpload(io.BytesIO(file_bytes), mimetype=content_type, resumable=True)
                            drive_file = drive_service.files().create(body=file_metadata, media_body=media, fields='id').execute()
                            
                            try:
                                drive_service.permissions().create(fileId=drive_file.get('id'), body={'type': 'anyone', 'role': 'reader'}).execute()
                            except: pass
                            
                            if drive_file.get('id'):
                                cur.execute("""
                                    INSERT INTO family_picture (code_pic, pic_path)
                                    VALUES (%s, %s)
                                    ON CONFLICT (code_pic) DO UPDATE SET pic_path = EXCLUDED.pic_path
                                """, (clean_code, drive_file.get('id')))

                    conn.commit()
                    return True
                except Exception as e:
                    conn.rollback()
                    raise e
                
    @staticmethod
    def is_code_exists(code: str) -> bool:
        if not code or code.strip() == "": return False
        with get_db_context() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT 1 FROM family_name WHERE code = %s", (code.strip().upper(),))
                return cur.fetchone() is not None
    
    @staticmethod       
    def get_family_table_backup_text() -> str:
        with get_db_context() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT code, name, nick_name, f_code, m_code, relation, level, w_code, h_code 
                    FROM family_name ORDER BY code ASC
                """)
                rows = cur.fetchall()
                lines = []
                for row in rows:
                    formatted_values = []
                    for val in row:
                        if val is None: formatted_values.append("NULL")
                        elif isinstance(val, int): formatted_values.append(str(val))
                        else: formatted_values.append(f"'{val}'")
                    lines.append("(" + ", ".join(formatted_values) + "),")
                return "\n".join(lines)               

    # ===============================================
    # 8. شجرة العائلة العودية المؤمنة من الحلقات الدائرية (DoS Protected)
    # ===============================================
    @staticmethod
    def get_full_family_tree_recursive(code: str) -> List[Dict[str, Any]]:
        tree_data = {}
        global_visited = set()

        def traverse(c, category="الشخص", depth=0):
            if not c or depth > FamilyService.MAX_TREE_DEPTH: return
            if c in global_visited: return
            global_visited.add(c)
            
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
                        if rel in ("ابن", "زوج", "ابن زوج", "ابن زوجة"): current_gender = "ذكر"
                        elif rel in ("ابنة", "زوجة", "ابنة زوج", "ابنة زوجة"): current_gender = "أنثى"
                    
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
                        if s_id and s_id not in tree_data and s_id not in global_visited:
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
                                if depth == 0: cat = "زوجة" if s_gender == "أنثى" else "زوج"
                                elif depth == 1:
                                    base = "ابن" if current_gender == "ذكر" else "ابنة"
                                    cat = f"زوجة {base}" if s_gender == "أنثى" else f"زوج {base}"
                                else:
                                    base = "حفيد" if current_gender == "ذكر" else "حفيدة"
                                    cat = f"زوجة {base}" if s_gender == "أنثى" else f"زوج {base}"
                                
                                tree_data[s_id] = {**s_data, "category": cat, "gender": s_gender}
                        
                    cur.execute("""
                        SELECT n.code, i.gender, n.relation
                        FROM family_name n
                        LEFT JOIN family_info i ON n.code = i.code_info
                        WHERE n.f_code = %s OR n.m_code = %s
                    """, (c, c))
                    children = cur.fetchall()
                    
                    for child in children:
                        ch_code = child['code']
                        if ch_code in global_visited: continue
                        ch_gender = child['gender'] or ("ذكر" if child['relation'] == "ابن" else "أنثى")
                        
                        if depth == 0: base = "ابن" if ch_gender == "ذكر" else "ابنة"
                        elif depth == 1: base = "حفيد" if ch_gender == "ذكر" else "حفيدة"
                        else:
                            is_from_female = (current_gender == "أنثى")
                            base = (f"ابن {'حفيدة' if is_from_female else 'حفيد'}") if ch_gender == "ذكر" else (f"ابنة {'حفيدة' if is_from_female else 'حفيد'}")
                        
                        traverse(ch_code, category=base, depth=depth + 1)

        traverse(code)
        return list(tree_data.values())


    # ===============================================
    # 9. مسار التشخيص الموحد وحالة قاعدة البيانات
    # ===============================================
    @staticmethod
    def get_db_status_diagnostics() -> Dict[str, Any]:
        """فحص حالة الاتصال بقاعدة البيانات وجلب إحصائيات سريعة للأسماء المضافة"""
        try:
            with get_db_context() as conn:
                with conn.cursor(cursor_factory=RealDictCursor) as cur:
                    cur.execute("SELECT COUNT(*) AS total FROM family_name")
                    total = cur.fetchone()["total"]

                    cur.execute("SELECT code, name FROM family_name ORDER BY name DESC LIMIT 15")
                    latest = cur.fetchall()

            return {
                "status": "success",
                "total_names_in_database": total,
                "latest_15_names": latest,
                "checked_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            }
        except Exception as e:
            logger.error(f"🔴 خطأ في قاعدة البيانات بمسار التشخيص الموحد: {e}")
            return {"status": "error", "message": "حدث خطأ داخلي أثناء معالجة البيانات."}    