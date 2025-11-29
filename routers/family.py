from datetime import datetime
from fastapi import APIRouter, Request, Form, UploadFile, File, HTTPException, Depends
from fastapi.responses import HTMLResponse, RedirectResponse
from services.family_service import get_full_name
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

    members = []
    total = 0

    with get_db_context() as conn:
        with conn.cursor() as cur:

            if q and q.strip():
                phrase = q.strip()

                # -----------------------
                # 1) البحث بالكود
                # -----------------------
                if "-" in phrase:
                    cur.execute("""
                        SELECT code, full_name, nick_name
                        FROM family_search
                        WHERE code ILIKE %s
                        ORDER BY code
                        LIMIT %s OFFSET %s
                    """, (f"%{phrase}%", ITEMS_PER_PAGE, offset))
                    rows = cur.fetchall()

                    cur.execute("""
                        SELECT COUNT(*)
                        FROM family_search
                        WHERE code ILIKE %s
                    """, (f"%{phrase}%",))
                    total = cur.fetchone()[0]

                # -----------------------
                # 2) البحث باللقب
                # -----------------------
                elif len(phrase.split()) == 1:
                    cur.execute("""
                        SELECT code, full_name, nick_name
                        FROM family_search
                        WHERE nick_name ILIKE %s
                        ORDER BY full_name
                        LIMIT %s OFFSET %s
                    """, (f"%{phrase}%", ITEMS_PER_PAGE, offset))
                    rows = cur.fetchall()

                    cur.execute("""
                        SELECT COUNT(*)
                        FROM family_search
                        WHERE nick_name ILIKE %s
                    """, (f"%{phrase}%",))
                    total = cur.fetchone()[0]

                # -----------------------
                # 3) البحث بجملة كاملة (Full Text Search)
                # -----------------------
                else:
                    clean_phrase = " ".join(phrase.split())
                    normalized_input = normalize_arabic(clean_phrase)
                    
                    cur.execute("""
                        SELECT code, full_name, nick_name
                        FROM family_search
                        WHERE normalized_full_name ILIKE %s
                        ORDER BY full_name
                        LIMIT %s OFFSET %s
                    """, (f"%{normalized_input}%", ITEMS_PER_PAGE, offset))

                    cur.execute("""
                        SELECT COUNT(*)
                        FROM family_search
                        WHERE normalized_full_name ILIKE %s
                    """, (f"%{normalized_input}%",))

                    # --- البحث بجملة كاملة بنفس الترتيب فقط ---
                    clean_phrase = " ".join(phrase.split())  # إزالة المسافات الزائدة

                    cur.execute("""
                        SELECT code, full_name, nick_name
                        FROM family_search
                        WHERE full_name ILIKE %s
                        ORDER BY full_name
                        LIMIT %s OFFSET %s
                    """, (f"%{clean_phrase}%", ITEMS_PER_PAGE, offset))

                    rows = cur.fetchall()

                    cur.execute("""
                        SELECT COUNT(*)
                        FROM family_search
                        WHERE full_name ILIKE %s
                    """, (f"%{clean_phrase}%",))

                    total = cur.fetchone()[0]

                   

                    

            else:
                # بدون بحث
                cur.execute("""
                    SELECT code, name, nick_name 
                    FROM family_name 
                    WHERE level >= 2
                    ORDER BY name 
                    LIMIT %s OFFSET %s
                """, (ITEMS_PER_PAGE, offset))
                rows = cur.fetchall()

                cur.execute("SELECT COUNT(*) FROM family_name WHERE level >= 2")
                total = cur.fetchone()[0]
            members = []
            # بناء القائمة النهائية
            for code, name, nick_name in rows:
                # جلب الاسم الكامل (حسب الدالة الموجودة لديك)
                display_name = get_full_name(code, max_length=7, include_nick=False)
                
                # تنظيف الاسم من التشكيل
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
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("SELECT * FROM family_name WHERE code = %s", (code,))
            member = cur.fetchone()
            if not member:
                raise HTTPException(status_code=404, detail="العضو غير موجود")

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

            full_name = get_full_name(code, include_nick=True)  # اللقب هنا
            mother_full_name = get_full_name(member["m_code"], include_nick=True) if member.get("m_code") else ""

            wives = []
            if gender == "ذكر":
                cur.execute("SELECT code FROM family_name WHERE h_code = %s", (code,))
                wives = [{"code": r["code"], "name": get_full_name(r["code"], include_nick=True)} for r in cur.fetchall()]

            husbands = []
            if gender == "أنثى" and member.get("h_code"):
                husbands = [{"code": member["h_code"], "name": get_full_name(member["h_code"], include_nick=True)}]

            cur.execute("SELECT code , name FROM family_name WHERE f_code = %s OR m_code = %s", (code, code))
            children = [{"code": r["code"], "name": r["name"],} for r in cur.fetchall()]

    response = templates.TemplateResponse("family/details.html", {
        "request": request, "user": user, "member": member, "info": info,
        "picture_url": picture_url, "full_name": full_name,
        "mother_full_name": mother_full_name, "wives": wives,
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
    relation = relation.strip() if relation else None
    nick_name = nick_name.strip() if nick_name else None
    gender = gender.strip() if gender else None
    d_o_b = d_o_b.strip() if d_o_b else None
    d_o_d = d_o_d.strip() if d_o_d else None
    email = email.strip().lower() if email else None
    phone = phone.strip() if phone else None
    address = address.strip() if address else None
    p_o_b = p_o_b.strip() if p_o_b else None
    status = status.strip() if status else None

    error = None
    success = None

    # ================================
    # 1. الكود: A0-000-001 فقط (لا يوجد شيء بعد الشرطة الثانية)
    # ================================
    if not re.fullmatch(r"[A-Z]\d{0,3}-\d{3}-\d{3}", code):
        error = "صيغة الكود غير صحيحة!<br>الصيغة الصحيحة: <strong>A0-000-001</strong> أو <strong>Z99-999-999</strong>"

    # ================================
    # 2. الاسم: حروف عربية + مسافات فقط (ممنوع أرقام أو رموز)
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
    # 10. كود الأب/الأم/الزوج/الزوجة (إن وُجد يجب نفس صيغة الكود الرئيسي)
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
                            ON CONFLICT (code_pic) DO UPDATE SET pic_path = %s
                        """, (code, pic_path, pic_path))

                    conn.commit()
                    success = f"تم حفظ {name} بنجاح!"

                    # تفريغ النموذج بعد النجاح
                    code = name = f_code = m_code = w_code = h_code = relation = nick_name = ""
                    level = gender = d_o_b = d_o_d = email = phone = address = p_o_b = status = None

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

    response = templates.TemplateResponse("family/edit_name.html", {
        "request": request, "user": user, "member": member, "info": info,
        "picture_url": picture_url, "code": code, "full_name": get_full_name(code),
        "csrf_token": csrf_token, "error": None
    })
    set_cache_headers(response)
    return response

@router.post("/edit/{code}")
async def update_name(request: Request, 
                      code: str, name: str = Form(...), 
                      f_code: str = Form(None), m_code: str = Form(None),
                      w_code: str = Form(None), h_code: str = Form(None),
                      relation: str = Form(None), level: int = Form(None),
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

    # تنظيف البيانات (نفس اللي فوق)
    name = name.strip()
    f_code = f_code.strip() if f_code else None
    m_code = m_code.strip() if m_code else None
    w_code = w_code.strip() if w_code else None
    h_code = h_code.strip() if h_code else None
    relation = relation.strip() if relation else None
    nick_name = nick_name.strip() if nick_name else None
    gender = gender.strip() if gender else None
    d_o_b = d_o_b.strip() if d_o_b else None
    d_o_d = d_o_d.strip() if d_o_d else None
    email = email.strip() if email else None
    phone = phone.strip() if phone else None
    address = address.strip() if address else None
    p_o_b = p_o_b.strip() if p_o_b else None
    status = status.strip() if status else None

    try:
        with get_db_context() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    UPDATE family_name SET
                    name=%s, f_code=%s, m_code=%s, w_code=%s, h_code=%s,
                    relation=%s, level=%s, nick_name=%s
                    WHERE code=%s
                """, (name, f_code, m_code, w_code, h_code, relation, level, nick_name, code))

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

                if picture and picture.filename:
                    pic_path = os.path.join(UPLOAD_DIR, picture.filename)
                    with open(pic_path, "wb") as f:
                        shutil.copyfileobj(picture.file, f)
                    cur.execute("""
                        INSERT INTO family_picture (code_pic, pic_path) VALUES (%s, %s)
                        ON CONFLICT (code_pic) DO UPDATE SET pic_path = %s
                    """, (code, pic_path, pic_path))

                conn.commit()
        return RedirectResponse("/names", status_code=303)

    except Exception as e:
        # إرجاع الخطأ في نفس الصفحة
        csrf_token = generate_csrf_token()
        request.session["csrf_token"] = csrf_token

        with get_db_context() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("SELECT * FROM family_name WHERE code = %s", (code,))
                member = cur.fetchone() or {}
                cur.execute("SELECT * FROM family_info WHERE code_info = %s", (code,))
                info = cur.fetchone() or {}
                cur.execute("SELECT pic_path FROM family_picture WHERE code_pic = %s", (code,))
                pic = cur.fetchone()
                picture_url = pic["pic_path"] if pic else None

        return templates.TemplateResponse("family/edit_name.html", {
            "request": request, "user": user, "member": member, "info": info,
            "picture_url": picture_url, "code": code, "full_name": get_full_name(code),
            "csrf_token": csrf_token, "error": "فشل في حفظ التعديلات، تأكد من البيانات"
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
            conn.commit()
    return RedirectResponse("/names", status_code=303)



# ====================== استيراد البيانات (أدمن فقط) ======================
@router.get("/import-data", response_class=HTMLResponse)
async def import_page(request: Request):
    user = request.session.get("user")
    if user.get("role") != "admin":
        raise HTTPException(status_code=403)
    return templates.TemplateResponse("family/import_data.html", {"request": request, "user": user})

@router.post("/import-data")
async def import_data(
    request: Request,
    dump_file: UploadFile = File(...),
    password: str = Form(...),
):
    user = request.session.get("user")
    if not user or user.get("role") != "admin" or password != IMPORT_PASSWORD:
        raise HTTPException(status_code=403, detail="كلمة المرور غير صحيحة أو ليس لديك صلاحية")

    if not dump_file.filename.lower().endswith(('.dump', '.sql')):
        return templates.TemplateResponse("family/import_data.html", {
            "request": request, "user": user,
            "message": "الملف لازم يكون بصيغة .dump أو .sql"
        })

    # حفظ الملف مؤقتًا
    file_path = f"/tmp/{dump_file.filename}"
    try:
        contents = await dump_file.read()
        with open(file_path, "wb") as f:
            f.write(contents)
    except Exception:
        return templates.TemplateResponse("family/import_data.html", {
            "request": request, "user": user,
            "message": "فشل في حفظ الملف المؤقت"
        })

    message = ""
    try:
        database_url = os.getenv("DATABASE_URL")

        # إعطاء وقت كافي جدًا (10 دقايق)
        cmd = ["pg_restore", "--verbose", "--clean", "--if-exists", "--no-owner", "--no-acl", 
            "--dbname", database_url, file_path] if file_path.endswith('.dump') \
            else ["psql", database_url, "-f", file_path]

        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=600  # من 120 → 600
        )

        if result.returncode == 0:
            message = "تم استيراد البيانات بنجاح! العائلة كلها موجودة الآن"
        else:
            message = f"فشل الاستيراد:<br><pre>{result.stderr.replace(chr(10), '<br>')[-1500:]}</pre>"

    except subprocess.TimeoutExpired:
        message = "انتهت المهلة! لكن عادةً بيكون الاستيراد اكتمل جزئيًا. جرب تاني أو قسم الملف."
    except Exception as e:
        message = f"خطأ: {str(e)}"
    finally:
        if os.path.exists(file_path):
            os.remove(file_path)    
    
   

    return templates.TemplateResponse("family/import_data.html", {
        "request": request,
        "user": user,
        "message": message
    })


# ====================== تصدير البيانات (أدمن فقط) ======================

@router.get("/export-data")
async def export_data(request: Request, password: str = ""):
    user = request.session.get("user")
    if not user or user.get("role") != "admin" or password != IMPORT_PASSWORD:
        raise HTTPException(status_code=403, detail="كلمة المرور غير صحيحة أو ليس لديك صلاحية")

    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        raise HTTPException(status_code=500, detail="DATABASE_URL مش موجود")

    # ملف بصيغة .dump (الأفضل للنسخ الكاملة)
    export_path = f"/home/engcof/render-backup/عائلة_حطية_كاملة_{datetime.now().strftime('%Y%m%d_%H%M%S')}.dump"

    try:
        cmd = [
            "pg_dump",
            "--verbose",
            "--no-owner",
            "--no-acl",
            "--format=custom",          # صيغة .dump (أفضل وأصغر حجمًا)
            "--file", export_path,
            database_url
        ]

        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=600  # 10 دقايق كفاية حتى لو 100 ألف سجل
        )

        if result.returncode != 0:
            raise Exception(f"pg_dump فشل: {result.stderr[-1500:]}")

        if not os.path.exists(export_path) or os.path.getsize(export_path) < 50000:
            raise Exception("الملف صغير جدًا أو فاضي")

        return FileResponse(
            path=export_path,
            filename=f"عائلة_حطية_كاملة_الداتابيز_{datetime.now().strftime('%Y%m%d_%H%M')}.dump",
            media_type="application/octet-stream"
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"فشل التصدير: {str(e)}")
    finally:
        if os.path.exists(export_path):
            try:
                os.remove(export_path)
            except:
                pass            