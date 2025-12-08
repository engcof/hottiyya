from datetime import datetime
from fastapi import APIRouter, Request, Form, UploadFile, File, HTTPException, Depends
from fastapi.responses import HTMLResponse, RedirectResponse
from security.csrf import generate_csrf_token, verify_csrf_token
from postgresql import get_db_context
from psycopg2.extras import RealDictCursor
from utils.permissions import has_permission
from utils.normalize import normalize_arabic
from security.session import set_cache_headers
from typing import Optional
import subprocess
from fastapi.responses import FileResponse
import shutil
import signal
import os
import re
from dotenv import load_dotenv
from core.templates import templates
import html # تم إضافة استيراد html في البداية

load_dotenv()
IMPORT_PASSWORD = os.getenv("IMPORT_PASSWORD", "change_me_in_production")

router = APIRouter(prefix="/names", tags=["family"])

UPLOAD_DIR = "static/uploads"
os.makedirs(UPLOAD_DIR, exist_ok=True)

# ====================== مساعد الصلاحيات (الأقوى) ======================
def can(user: dict, perm: str) -> bool:
    if not user:
        return False
    if user.get("role") == "admin":
        return True
    return bool(user.get("id") and has_permission(user.get("id"), perm))

def to_tsquery_safe(phrase: str):
    words = [w for w in phrase.split() if w.strip()]
    return " & ".join([f"{w}:*" for w in words])

# ====================== قائمة الأعضاء ======================
@router.get("/", response_class=HTMLResponse)
async def show_names(request: Request, page: int = 1, q: str = None):
    user = request.session.get("user")
    if not user:
        return RedirectResponse("/auth/login")

    can_add    = can(user, "add_member")
    can_edit   = can(user, "edit_member")
    can_delete = can(user, "delete_member")

    ITEMS_PER_PAGE = 24
    offset = (page - 1) * ITEMS_PER_PAGE

    rows = []
    total = 0
    search_term = None # تحديد search_term خارج الكتل

    with get_db_context() as conn:
        with conn.cursor() as cur:
            if q and q.strip():
                phrase = q.strip()
                
                # توحيد المدخلات مرة واحدة
                clean_phrase = " ".join(phrase.split())
                normalized_input = normalize_arabic(clean_phrase)
                search_term = f"%{normalized_input}%" # 💡 هذا هو المعامل الذي سنستخدمه

                # -----------------------
                # 1) البحث بالكود (الأولوية القصوى)
                # ----------------------
                if "-" in phrase and len(phrase.split()) == 1:
                    cur.execute("""
                        SELECT code, public.get_full_name(code, 7, FALSE) AS full_name_display, nick_name, level
                        FROM family_search
                        WHERE code ILIKE %s AND level >= 2
                        ORDER BY code
                        LIMIT %s OFFSET %s
                    """, (f"%{phrase}%", ITEMS_PER_PAGE, offset))
                    rows = cur.fetchall()
                    
                    cur.execute("""
                        SELECT COUNT(*)
                        FROM family_search
                        WHERE code ILIKE %s AND level >= 2
                    """, (f"%{phrase}%",))
                    total = cur.fetchone()[0]

                # -----------------------
                # 2) البحث باللقب (إذا كانت كلمة واحدة وليست كود)
                # -----------------------
                elif len(phrase.split()) == 1:
                    cur.execute("""
                        SELECT code, public.get_full_name(code, 7, FALSE) AS full_name_display, nick_name, level
                        FROM family_search
                        WHERE nick_name ILIKE %s AND level >= 2
                        ORDER BY full_name
                        LIMIT %s OFFSET %s
                    """, (f"%{phrase}%", ITEMS_PER_PAGE, offset))
                    rows = cur.fetchall()
                    
                    cur.execute("""
                        SELECT COUNT(*)
                        FROM family_search
                        WHERE nick_name ILIKE %s AND level >= 2
                    """, (f"%{phrase}%",))
                    total = cur.fetchone()[0]

                # -----------------------
                # 3) البحث بجملة كاملة (Full Text Search) - يستخدم التوحيد
                # -----------------------
                else:
                    # 💡 نستخدم الاستعلام الموحد والمرن (الذي ثبت أنه يحل المشاكل)
                    cur.execute("""
                        SELECT code, public.get_full_name(code, 7, FALSE) AS full_name_display, nick_name, level
                        FROM family_search
                        WHERE public.normalize_arabic_db(TRIM(full_name)) ILIKE %s AND level >= 2
                        ORDER BY full_name
                        LIMIT %s OFFSET %s
                    """, (search_term, ITEMS_PER_PAGE, offset))
                    rows = cur.fetchall()
                    
                    cur.execute("""
                        SELECT COUNT(*)
                        FROM family_search
                        WHERE public.normalize_arabic_db(TRIM(full_name)) ILIKE %s AND level >= 2
                    """, (search_term,))
                    total = cur.fetchone()[0]
                 

            else:
                # 💡 بدون بحث - جلب الاسم المقطوع مباشرة لضمان الأداء
                cur.execute("""
                    SELECT code, public.get_full_name(code, 7, FALSE) AS full_name_display, nick_name, level
                    FROM family_search 
                    WHERE level >= 2
                    ORDER BY full_name 
                    LIMIT %s OFFSET %s
                """, (ITEMS_PER_PAGE, offset))
                rows = cur.fetchall()
    
                cur.execute("SELECT COUNT(*) FROM family_search WHERE level >= 2")
                total = cur.fetchone()[0]
            
            members = []
            
            # 💡 يتم الآن معالجة الصفوف بسرعة دون استدعاءات داخلية لـ DB
            for row in rows:
                # يجب التأكد من الترتيب: code, full_name_display, nick_name, level
                code, display_name, nick_name, level = row
                
                clean_display_name = normalize_arabic(display_name)
                clean_nick_name = normalize_arabic(nick_name.strip()) if nick_name else None

                members.append({
                    "code": code,
                    "full_name": clean_display_name,
                    "nick_name": clean_nick_name
                })

            members.sort(key=lambda x: x["full_name"])
    total_pages = (total + ITEMS_PER_PAGE - 1) // ITEMS_PER_PAGE

    response = templates.TemplateResponse("family/names.html", {
        "request": request,
        "user": user,
        "members": members,
        "page": page,
        "total_pages": total_pages,
        "has_prev": page > 1,
        "has_next": page < total_pages,
        "q": q,
        "can_add": can_add,
        "can_edit": can_edit,
        "can_delete": can_delete
    })
    set_cache_headers(response)
    return response

# ====================== تفاصيل العضو ======================
@router.get("/details/{code}", response_class=HTMLResponse)
async def name_details(request: Request, code: str):
    user = request.session.get("user")
    if not user:
        return RedirectResponse("/auth/login")

    with get_db_context() as conn:
        # استخدام RealDictCursor لسهولة الوصول للبيانات بالاسم
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            
            # 1. جلب العضو من family_name
            cur.execute("SELECT * FROM family_name WHERE code = %s", (code,))
            member = cur.fetchone()
            if not member:
                raise HTTPException(status_code=404, detail="العضو غير موجود")

            
            # 2. جلب الاسم الكامل (سلسلة الأجداد) بدون اللقب
            cur.execute("SELECT public.get_full_name(%s, NULL, FALSE) AS full_name", (code,))
            result = cur.fetchone()
            full_name_no_nick = result["full_name"] if result else member.get("name", "اسم غير معروف")
            
            # 3. جلب اللقب منفصلاً
            display_nick_name = member.get("nick_name")
            if display_nick_name:
                 display_nick_name = display_nick_name.strip()
            
            # 4. جلب اسم الأم
            mother_full_name = ""
            if member.get("m_code"):
                 cur.execute("SELECT public.get_full_name(%s, NULL, TRUE) AS mother_name", (member["m_code"],))
                 result = cur.fetchone()
                 mother_full_name = result["mother_name"] if result else "الأم غير موجودة"

            # ----------------------------------------------------
            # 5. بقية الاستعلامات
            # ----------------------------------------------------
            cur.execute("SELECT * FROM family_info WHERE code_info = %s", (code,))
            info = cur.fetchone() or {}
            
            cur.execute("SELECT pic_path FROM family_picture WHERE code_pic = %s", (code,))
            pic = cur.fetchone()
            picture_url = pic["pic_path"] if pic else None

            gender = info.get("gender")
            if not gender and member.get("relation"):
                rel = member["relation"]
                if rel in ("ابن", "زوج", "ابن زوج", "ابن زوجة"):
                    gender = "ذكر"
                elif rel in ("ابنة", "زوجة", "ابنة زوج", "ابنة زوجة"):
                    gender = "أنثى"
            
            # 6. جلب أسماء الأزواج/الزوجات
            wives = []
            if gender == "ذكر":
                cur.execute("SELECT code FROM family_name WHERE h_code = %s", (code,))
                wives_codes = cur.fetchall()
                for r in wives_codes:
                    cur.execute("SELECT public.get_full_name(%s, NULL, TRUE) AS wife_name", (r["code"],))
                    result = cur.fetchone()
                    wife_name = result["wife_name"] if result else "اسم غير معروف"
                    
                    wives.append({
                        "code": r["code"], 
                        "name": wife_name
                    })

            husbands = []
            if gender == "أنثى" and member.get("h_code"):
                cur.execute("SELECT public.get_full_name(%s, NULL, TRUE) AS husband_name", (member["h_code"],))
                result = cur.fetchone()
                husband_name = result["husband_name"] if result else "اسم غير معروف"
                
                husbands = [{
                    "code": member["h_code"], 
                    "name": husband_name
                }]

            cur.execute("SELECT code, name FROM family_name WHERE f_code = %s OR m_code = %s", (code, code))
            children = [{"code": r["code"], "name": r["name"],} for r in cur.fetchall()]

    response = templates.TemplateResponse("family/details.html", {
        "request": request, "user": user, "member": member, "info": info,
        "picture_url": picture_url, 
        "full_name": full_name_no_nick,     
        "nick_name": display_nick_name,     
        "mother_full_name": mother_full_name, 
        "wives": wives,
        "husbands": husbands, "children": children, "gender": gender
    })
    set_cache_headers(response)
    return response

    

# ====================== إضافة عضو جديد ======================
@router.get("/add", response_class=HTMLResponse)
async def add_name_form(request: Request):
    user = request.session.get("user")
    if not user or not can(user, "add_member"):
        return RedirectResponse("/names")
    csrf_token = generate_csrf_token()
    request.session["csrf_token"] = csrf_token
    response = templates.TemplateResponse("family/add_name.html", {
        "request": request, "user": user, "csrf_token": csrf_token, "error": None
    })
    set_cache_headers(response)
    return response

@router.post("/add")
async def add_name(
    request: Request,
    code: str = Form(...), name: str = Form(...),
    f_code: Optional[str] = Form(None), m_code: Optional[str] = Form(None),
    w_code: Optional[str] = Form(None), h_code: Optional[str] = Form(None),
    relation: Optional[str] = Form(None), level: Optional[int] = Form(None),
    nick_name: Optional[str] = Form(None), gender: Optional[str] = Form(None),
    d_o_b: Optional[str] = Form(None), d_o_d: Optional[str] = Form(None),
    email: Optional[str] = Form(None), phone: Optional[str] = Form(None),
    address: Optional[str] = Form(None), p_o_b: Optional[str] = Form(None),
    status: Optional[str] = Form(None),
    picture: Optional[UploadFile] = File(None)
):
    user = request.session.get("user")
    if not user or not can(user, "add_member"):
        return RedirectResponse("/names")

    form = await request.form()
    verify_csrf_token(request, form.get("csrf_token"))

    # تنظيف أولي
    code = code.strip().upper()
    name = name.strip()
    f_code = f_code.strip().upper() if f_code else None
    m_code = m_code.strip().upper() if m_code else None
    w_code = w_code.strip().upper() if w_code else None
    h_code = h_code.strip().upper() if h_code else None
    relation = html.escape(relation.strip()) if relation else None
    nick_name = nick_name.strip() if nick_name else None 
    gender = gender.strip() if gender else None
    d_o_b = d_o_b.strip() if d_o_b else None
    d_o_d = d_o_d.strip() if d_o_d else None
    email = email.strip().lower() if email else None
    phone = phone.strip() if phone else None
    address = html.escape(address.strip()) if address else None
    p_o_b = html.escape(p_o_b.strip()) if p_o_b else None
    status = status.strip() if status else None

    error = None
    success = None

    # ================================
    # 1. الكود: A0-000-001 فقط 
    # ================================
    if not re.fullmatch(r"[A-Z]\d{0,3}-\d{3}-\d{3}", code):
        error = "صيغة الكود غير صحيحة!<br>الصيغة الصحيحة: <strong>A0-000-001</strong> أو <strong>Z99-999-999</strong>"

    # ================================
    # 2. الاسم: حروف عربية + مسافات فقط 
    # ================================
    elif not re.fullmatch(r"[\u0600-\u06FF\s]+", name):
        error = "الاسم يجب أن يحتوي على حروف عربية فقط (ممنوع الأرقام والرموز)"

    # ================================
    # 3. المستوى
    # ================================
    elif level is None or level < 1:
        error = "المستوى مطلوب ويجب أن يكون رقم موجب"

    # ================================
    # 4. اللقب (إذا وُجد)
    # ================================
    elif nick_name and not re.fullmatch(r"[\u0600-\u06FF\s]+", nick_name):
        error = "اللقب يجب أن يكون حروف عربية فقط (مثل: أبو أحمد، أم علي)"

    # ================================
    # 5. مكان الميلاد (إذا وُجد)
    # ================================
    elif p_o_b and (p_o_b[0].isdigit() or re.search(r"^[\s\-\_\.\@\#\!\$\%\^\&\*\(\)]", p_o_b)):
        error = "مكان الميلاد لا يجب أن يبدأ برمز أو رقم (مثال صحيح: الرياض، صنعاء، القاهرة)"

    # ================================
    # 6. العنوان (إذا وُجد)
    # ================================
    elif address and (address[0].isdigit() or re.search(r"^[\s\-\_\.\@\#\!\$\%\^\&\*\(\)]", address)):
        error = "العنوان لا يجب أن يبدأ برمز أو رقم (ابدأ بالحي أو المدينة)"

    # ================================
    # 7. الإيميل (إذا وُجد)
    # ================================
    elif email and not re.fullmatch(r"[^@]+@[^@]+\.[^@]+", email):
        error = "البريد الإلكتروني غير صالح (مثال: name@example.com)"

    # ================================
    # 8. الهاتف (إذا وُجد)
    # ================================
    elif phone and not re.fullmatch(r"[\d\s\-\+\(\)]{8,20}", phone):
        error = "رقم الهاتف غير صالح (استخدم أرقام، مسافات، +، -، () فقط)"

    # ================================
    # 9. التواريخ (لا تكون في المستقبل + تاريخ الوفاة بعد الميلاد)
    # ================================
    from datetime import date
    today = date.today()

    if d_o_b:
        try:
            dob = date.fromisoformat(d_o_b)
            if dob > today:
                error = "تاريخ الميلاد لا يمكن أن يكون في المستقبل"
        except ValueError:
            error = "تاريخ الميلاد غير صالح"

    if not error and d_o_d:
        try:
            dod = date.fromisoformat(d_o_d)
            if dod > today:
                error = "تاريخ الوفاة لا يمكن أن يكون في المستقبل"
            if d_o_b and dod < date.fromisoformat(d_o_b):
                error = "تاريخ الوفاة لا يمكن أن يكون قبل تاريخ الميلاد"
        except ValueError:
            error = "تاريخ الوفاة غير صالح"

    # ================================
    # 10. كود الأب/الأم/الزوج/الزوجة
    # ================================
    parent_pattern = r"[A-Z]\d{0,3}-\d{3}-\d{3}"
    if f_code and not re.fullmatch(parent_pattern, f_code):
        error = f"كود الأب غير صحيح (مثال: {code.split('-')[0]}0-000-001)"
    elif m_code and not re.fullmatch(parent_pattern, m_code):
        error = "كود الأم غير صحيح"
    elif h_code and not re.fullmatch(parent_pattern, h_code):
        error = "كود الزوج غير صحيح"
    elif w_code and not re.fullmatch(parent_pattern, w_code):
        error = "كود الزوجة غير صحيح"

    # ================================
    # 11. تحقق من تكرار الكود في قاعدة البيانات
    # ================================
    elif not error:
        with get_db_context() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT 1 FROM family_name WHERE code = %s", (code,))
                if cur.fetchone():
                    error = "هذا الكود مستخدم من قبل! اختر كودًا آخر."

    # ================================
    # 12. رفع الصورة (نوع الملف فقط)
    # ================================
    if not error and picture and picture.filename:
        allowed = {'.jpg', '.jpeg', '.png', '.webp'}
        ext = os.path.splitext(picture.filename)[1].lower()
        if ext not in allowed:
            error = "نوع الصورة غير مدعوم! استخدم: JPG، PNG، WebP فقط"

    # ================================
    # إذا كل شيء تمام → احفظ
    # ================================
    if not error:
        try:
            with get_db_context() as conn:
                with conn.cursor() as cur:
                    cur.execute("""
                        INSERT INTO family_name 
                        (code, name, f_code, m_code, w_code, h_code, relation, level, nick_name)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """, (code, name, f_code, m_code, w_code, h_code, relation, level, nick_name))

                    cur.execute("""
                        INSERT INTO family_info 
                        (code_info, gender, d_o_b, d_o_d, email, phone, address, p_o_b, status)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                        ON CONFLICT (code_info) DO NOTHING
                    """, (code, gender, d_o_b, d_o_d, email, phone, address, p_o_b, status))

                    if picture and picture.filename:
                        safe_filename = f"{code}{ext}"
                        pic_path = os.path.join(UPLOAD_DIR, safe_filename)
                        with open(pic_path, "wb") as f:
                            shutil.copyfileobj(picture.file, f)
                        cur.execute("""
                            INSERT INTO family_picture (code_pic, pic_path) VALUES (%s, %s)
                            ON CONFLICT (code_pic) DO UPDATE SET pic_path = EXCLUDED.pic_path
                        """, (code, pic_path))

                    conn.commit()
                    success = f"تم حفظ {name} بنجاح!"

                    # تفريغ النموذج بعد النجاح
                    code = name = f_code = m_code = w_code = h_code = relation = nick_name = ""
                    level = gender = d_o_b = d_o_d = email = phone = address = p_o_b = status = None
            
            # توجيه بعد النجاح
            return RedirectResponse(f"/names/details/{code}", status_code=303)

        except Exception as e:
            error = "حدث خطأ أثناء الحفظ. حاول مرة أخرى."

    # إرجاع الصفحة دائمًا
    csrf_token = generate_csrf_token()
    request.session["csrf_token"] = csrf_token

    return templates.TemplateResponse("family/add_name.html", {
        "request": request, "user": user, "csrf_token": csrf_token,
        "error": error, "success": success,
        "form_data": {
            "code": code if error else "",
            "name": name if error else "",
            "f_code": f_code if error else "",
            "m_code": m_code if error else "",
            "w_code": w_code if error else "",
            "h_code": h_code if error else "",
            "relation": relation or "",
            "level": str(level) if level and error else "",
            "nick_name": nick_name or "",
            "gender": gender or "",
            "d_o_b": d_o_b or "",
            "d_o_d": d_o_d or "",
            "email": email or "",
            "phone": phone or "",
            "address": address or "",
            "p_o_b": p_o_b or "",
            "status": status or "",
        }
    })

# ====================== تعديل عضو ======================
@router.get("/edit/{code}", response_class=HTMLResponse)
async def edit_name_form(request: Request, code: str):
    user = request.session.get("user")
    if not user or not can(user, "edit_member"):
        return RedirectResponse("/names")

    csrf_token = generate_csrf_token()
    request.session["csrf_token"] = csrf_token

    with get_db_context() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("SELECT * FROM family_name WHERE code = %s", (code,))
            member = cur.fetchone()

            if not member:
                return templates.TemplateResponse("family/edit_name.html", {
                    "request": request, "user": user, "code": code,
                    "csrf_token": csrf_token, "error": "العضو غير موجود أو تم حذفه"
                })

            cur.execute("SELECT * FROM family_info WHERE code_info = %s", (code,))
            info = cur.fetchone() or {}

            cur.execute("SELECT pic_path FROM family_picture WHERE code_pic = %s", (code,))
            pic = cur.fetchone()
            picture_url = pic["pic_path"] if pic else None

    # 💡 تم إزالة دالة get_full_name القديمة من هنا، ويمكنك جلب الاسم الكامل في القالب
    response = templates.TemplateResponse("family/edit_name.html", {
        "request": request, "user": user, "member": member, "info": info,
        "picture_url": picture_url, "code": code, 
        "csrf_token": csrf_token, "error": None
    })
    set_cache_headers(response)
    return response

@router.post("/edit/{code}")
async def update_name(request: Request, 
                      code: str, name: str = Form(...), 
                      f_code: str = Form(None), m_code: str = Form(None),
                      w_code: str = Form(None), h_code: str = Form(None),
                      relation: str = Form(None), level: str = Form(None), 
                      nick_name: str = Form(None), gender: str = Form(None),
                      d_o_b: str = Form(None), d_o_d: str = Form(None),
                      email: str = Form(None), phone: str = Form(None),
                      address: str = Form(None), p_o_b: str = Form(None),
                      status: str = Form(None), picture: UploadFile = File(None)):
    
    user = request.session.get("user")
    if not user or not can(user, "edit_member"):
        return RedirectResponse("/names")

    form = await request.form()
    verify_csrf_token(request, form.get("csrf_token"))

    error = None
    level_int = None 
    
    # === 1. التنظيف وتطبيق الـ XSS ===
    
    name = name.strip()
    f_code = f_code.strip().upper() if f_code else None
    m_code = m_code.strip().upper() if m_code else None
    w_code = w_code.strip().upper() if w_code else None
    h_code = h_code.strip().upper() if h_code else None
    relation = html.escape(relation.strip()) if relation else None
    nick_name = nick_name.strip() if nick_name else None
    gender = gender.strip() if gender else None
    d_o_b = d_o_b.strip() if d_o_b else None
    d_o_d = d_o_d.strip() if d_o_d else None
    email = email.strip().lower() if email else None
    phone = phone.strip() if phone else None
    address = html.escape(address.strip()) if address else None
    p_o_b = html.escape(p_o_b.strip()) if p_o_b else None
    status = status.strip() if status else None

    # === 2. التحقق من المدخلات (Input Validation) ===
    
    # 2.1. الاسم
    if not re.fullmatch(r"[\u0600-\u06FF\s]+", name):
        error = "الاسم يجب أن يحتوي على حروف عربية فقط (ممنوع الأرقام والرموز)"

    # 2.2. المستوى
    if not error and level:
        try:
            level_int = int(level)
            if level_int < 1:
                error = "المستوى يجب أن يكون رقماً موجباً."
        except ValueError:
            error = "المستوى يجب أن يكون رقماً صحيحاً."
    elif not error:
        error = "المستوى مطلوب ولا يمكن أن يكون فارغاً."
    
    # 2.3. اللقب
    if not error and nick_name and not re.fullmatch(r"[\u0600-\u06FF\s]+", nick_name):
        error = "اللقب يجب أن يكون حروف عربية فقط (مثل: أبو أحمد، أم علي)"

    # 2.4. مكان الميلاد 
    elif not error and p_o_b and (p_o_b[0].isdigit() or re.search(r"^[\s\-\_\.\@\#\!\$\%\^\&\*\(\)]", p_o_b)):
        error = "مكان الميلاد لا يجب أن يبدأ برمز أو رقم"

    # 2.5. العنوان
    elif not error and address and (address[0].isdigit() or re.search(r"^[\s\-\_\.\@\#\!\$\%\^\&\*\(\)]", address)):
        error = "العنوان لا يجب أن يبدأ برمز أو رقم"

    # 2.6. الإيميل
    elif not error and email and not re.fullmatch(r"[^@]+@[^@]+\.[^@]+", email):
        error = "البريد الإلكتروني غير صالح (مثال: name@example.com)"

    # 2.7. الهاتف
    elif not error and phone and not re.fullmatch(r"[\d\s\-\+\(\)]{8,20}", phone):
        error = "رقم الهاتف غير صالح (استخدم أرقام، مسافات، +، -، () فقط)"

    # 2.8. التواريخ
    from datetime import date
    today = date.today()

    if not error and d_o_b:
        try:
            dob = date.fromisoformat(d_o_b)
            if dob > today:
                error = "تاريخ الميلاد لا يمكن أن يكون في المستقبل"
        except ValueError:
            error = "تاريخ الميلاد غير صالح"

    if not error and d_o_d:
        try:
            dod = date.fromisoformat(d_o_d)
            if dod > today:
                error = "تاريخ الوفاة لا يمكن أن يكون في المستقبل"
            if d_o_b and dod < date.fromisoformat(d_o_b):
                error = "تاريخ الوفاة لا يمكن أن يكون قبل تاريخ الميلاد"
        except ValueError:
            error = "تاريخ الوفاة غير صالح"

    # 2.9. أكواد الأقارب
    parent_pattern = r"[A-Z]\d{0,3}-\d{3}-\d{3}"
    if not error and f_code and not re.fullmatch(parent_pattern, f_code):
        error = f"كود الأب غير صحيح"
    elif not error and m_code and not re.fullmatch(parent_pattern, m_code):
        error = "كود الأم غير صحيح"
    elif not error and h_code and not re.fullmatch(parent_pattern, h_code):
        error = "كود الزوج غير صحيح"
    elif not error and w_code and not re.fullmatch(parent_pattern, w_code):
        error = "كود الزوجة غير صحيح"

    # 2.10. صورة 
    if not error and picture and picture.filename:
        allowed = {'.jpg', '.jpeg', '.png', '.webp'}
        ext = os.path.splitext(picture.filename)[1].lower()
        if ext not in allowed:
            error = "نوع الصورة غير مدعوم! استخدم: JPG، PNG، WebP فقط"

    # === 3. التنفيذ أو إرجاع الخطأ ===
    if not error:
        try:
            with get_db_context() as conn:
                with conn.cursor() as cur:
                    # 3.1 تحديث family_name
                    cur.execute("""
                        UPDATE family_name SET
                        name=%s, f_code=%s, m_code=%s, w_code=%s, h_code=%s,
                        relation=%s, level=%s, nick_name=%s
                        WHERE code=%s
                    """, (name, f_code, m_code, w_code, h_code, relation, level_int, nick_name, code))

                    # 3.2 تحديث أو إدخال family_info
                    cur.execute("SELECT 1 FROM family_info WHERE code_info = %s", (code,))
                    if cur.fetchone():
                        cur.execute("""
                            UPDATE family_info SET gender=%s, d_o_b=%s, d_o_d=%s, email=%s,
                            phone=%s, address=%s, p_o_b=%s, status=%s WHERE code_info=%s
                        """, (gender, d_o_b, d_o_d, email, phone, address, p_o_b, status, code))
                    else:
                        cur.execute("""
                            INSERT INTO family_info (code_info, gender, d_o_b, d_o_d, email, phone, address, p_o_b, status)
                            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                        """, (code, gender, d_o_b, d_o_d, email, phone, address, p_o_b, status))

                    # 3.3 تحديث الصورة
                    if picture and picture.filename:
                        ext = os.path.splitext(picture.filename)[1].lower()
                        safe_filename = f"{code}{ext}"
                        pic_path = os.path.join(UPLOAD_DIR, safe_filename)
                        with open(pic_path, "wb") as f:
                            shutil.copyfileobj(picture.file, f)
                        cur.execute("""
                            INSERT INTO family_picture (code_pic, pic_path) VALUES (%s, %s)
                            ON CONFLICT (code_pic) DO UPDATE SET pic_path = EXCLUDED.pic_path
                        """, (code, pic_path))

                    conn.commit()
                    return RedirectResponse(f"/names/details/{code}", status_code=303) # توجيه بعد النجاح

        except Exception as e:
            error = "حدث خطأ أثناء التحديث. حاول مرة أخرى."

    # إذا حدث خطأ، قم بتحميل بيانات العضو مرة أخرى لعرضها مع الخطأ
    with get_db_context() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("SELECT * FROM family_name WHERE code = %s", (code,))
            member = cur.fetchone()
            cur.execute("SELECT * FROM family_info WHERE code_info = %s", (code,))
            info = cur.fetchone() or {}
            cur.execute("SELECT pic_path FROM family_picture WHERE code_pic = %s", (code,))
            pic = cur.fetchone()
            picture_url = pic["pic_path"] if pic else None

    # إرجاع الصفحة مع رسالة الخطأ
    csrf_token = generate_csrf_token()
    request.session["csrf_token"] = csrf_token
    return templates.TemplateResponse("family/edit_name.html", {
        "request": request, "user": user, "member": member, "info": info,
        "picture_url": picture_url, "code": code,
        "csrf_token": csrf_token, "error": error
    })

# ====================== حذف عضو ======================
@router.post("/delete/{code}")
async def delete_name(request: Request, code: str):
    user = request.session.get("user")
    if not user or not can(user, "delete_member"):
        return RedirectResponse("/names")
    with get_db_context() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM family_picture WHERE code_pic = %s", (code,))
            cur.execute("DELETE FROM family_info WHERE code_info = %s", (code,))
            cur.execute("DELETE FROM family_name WHERE code = %s", (code,))
            cur.execute("DELETE FROM family_search WHERE code = %s", (code,))
            conn.commit()
    return RedirectResponse("/names", status_code=303)

