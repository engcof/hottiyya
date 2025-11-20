# app/routes/family.py → النسخة النهائية المُراجعة والمُحسّنة
from fastapi import APIRouter, Request, Form, UploadFile, File, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from services.family_service import get_full_name
from security.csrf import generate_csrf_token, verify_csrf_token
from postgresql import get_db_context
from psycopg2.extras import RealDictCursor
from fastapi.templating import Jinja2Templates
from utils.permissions import has_permission
from security.session import set_cache_headers
import shutil
import os

router = APIRouter(prefix="/names", tags=["family"])
templates = Jinja2Templates(directory="templates")
UPLOAD_DIR = "static/uploads"
os.makedirs(UPLOAD_DIR, exist_ok=True)

def can(user: dict, perm: str) -> bool:
    if not user:
        return False
    if user.get("role") == "admin":
        return True
    return bool(user.get("id") and has_permission(user.get("id"), perm))

# ====================== قائمة الأعضاء ======================
@router.get("/", response_class=HTMLResponse)
async def show_names(request: Request, page: int = 1, q: str = None):
    user = request.session.get("user")
    if not user:
        return RedirectResponse("/auth/login")

    can_add = can(user, "add_member")
    can_edit = can(user, "edit_member")
    can_delete = can(user, "delete_member")

    ITEMS_PER_PAGE = 18
    offset = (page - 1) * ITEMS_PER_PAGE
    members = []
    total_pages = 1
    total = 0

    with get_db_context() as conn:
        with conn.cursor() as cur:

            if q and q.strip():
                # ====== وضع البحث ======
                keywords = [kw.strip() for kw in q.strip().split() if kw.strip()]

                cur.execute("""
                    SELECT code, name, nick_name 
                    FROM family_name 
                    WHERE level > 0
                    ORDER BY name
                """)
                all_members = cur.fetchall()

                filtered = []
                for code, name, nick_name in all_members:
                    full_name = get_full_name(code, max_length=None, include_nick=False).lower()
                    nickname_str = (nick_name or "").lower()
                    code_str = code.lower()

                    if all(kw.lower() in full_name or kw.lower() in nickname_str or kw.lower() in code_str for kw in keywords):
                        filtered.append((code, name, nick_name))

                # ترتيب حسب عدد الكلمات المتطابقة
                filtered.sort(key=lambda x: sum(
                    kw.lower() in get_full_name(x[0], max_length=None, include_nick=False).lower()
                    for kw in keywords
                ), reverse=True)

                total = len(filtered)
                rows = filtered[offset:offset + ITEMS_PER_PAGE]

            else:
                # ====== بدون بحث ======
                cur.execute("""
                    SELECT code, name, nick_name 
                    FROM family_name 
                    WHERE level > 0
                    ORDER BY name 
                    LIMIT %s OFFSET %s
                """, (ITEMS_PER_PAGE, offset))
                rows = cur.fetchall()

                cur.execute("SELECT COUNT(*) FROM family_name WHERE level > 0")
                total = cur.fetchone()[0]

            # ====== بناء القائمة النهائية (هنا المفتاح!) ======
            for code, name, nick_name in rows:
                display_name = get_full_name(code, max_length=7, include_nick=False)
                members.append({
                    "code": code,
                    "full_name": display_name,
                    "nick_name": nick_name.strip() if nick_name else None
                })

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

# باقي الكود (إضافة، تعديل، حذف) → **ممتاز وما يحتاجش تعديل**

# ====================== إضافة عضو ======================
@router.get("/add", response_class=HTMLResponse)
async def add_name_form(request: Request):
    user = request.session.get("user")
    if not user or not can(user, "add_member"):
        return RedirectResponse("/names")

    csrf_token = generate_csrf_token()
    request.session["csrf_token"] = csrf_token

    response = templates.TemplateResponse("family/add_name.html", {
        "request": request, "user": user, "error": None, "csrf_token": csrf_token
    })
    set_cache_headers(response)
    return response

@router.post("/add")
async def add_name(
    request: Request,
    code: str = Form(...), name: str = Form(...),
    f_code: str = Form(None), m_code: str = Form(None),
    w_code: str = Form(None), h_code: str = Form(None),
    relation: str = Form(None), level: int = Form(None),
    nick_name: str = Form(None), gender: str = Form(None),
    d_o_b: str = Form(None), d_o_d: str = Form(None),
    email: str = Form(None), phone: str = Form(None),
    address: str = Form(None), p_o_b: str = Form(None),
    status: str = Form(None), picture: UploadFile = File(None)
):
    user = request.session.get("user")
    if not user or not can(user, "add_member"):
        return RedirectResponse("/names")

    form = await request.form()
    verify_csrf_token(request, form.get("csrf_token"))

    # تنظيف البيانات
    code = code.strip()
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

    error = None
    success = None

    # التحقق من الحقول الإجبارية
    if not code or not name:
        error = "الكود والاسم مطلوبان!"
    elif level is None:
        error = "يجب إدخال المستوى (level)!"
    else:
        try:
            with get_db_context() as conn:
                with conn.cursor() as cur:
                    # التحقق من تكرار الكود
                    cur.execute("SELECT 1 FROM family_name WHERE code = %s", (code,))
                    if cur.fetchone():
                        error = "الكود مستخدم مسبقاً!"
                    else:
                        # إضافة العضو
                        cur.execute("""
                            INSERT INTO family_name (code, name, f_code, m_code, w_code, h_code, relation, level, nick_name)
                            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                        """, (code, name, f_code, m_code, w_code, h_code, relation, level, nick_name))

                        cur.execute("""
                            INSERT INTO family_info (code_info, gender, d_o_b, d_o_d, email, phone, address, p_o_b, status)
                            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                            ON CONFLICT (code_info) DO NOTHING
                        """, (code, gender, d_o_b, d_o_d, email, phone, address, p_o_b, status))

                        if picture and picture.filename:
                            pic_path = os.path.join(UPLOAD_DIR, f"{code}_{picture.filename}")
                            with open(pic_path, "wb") as f:
                                shutil.copyfileobj(picture.file, f)
                            cur.execute("""
                                INSERT INTO family_picture (code_pic, pic_path) 
                                VALUES (%s, %s) ON CONFLICT (code_pic) DO UPDATE SET pic_path = %s
                            """, (code, pic_path, pic_path))

                        conn.commit()
                        success = f"تم إضافة {name} بنجاح!"

                        # تصفير النموذج بعد النجاح
                        code = name = f_code = m_code = w_code = h_code = relation = nick_name = ""
                        level = gender = d_o_b = d_o_d = email = phone = address = p_o_b = status = None

        except Exception as e:
            error = "حدث خطأ أثناء الحفظ، تأكد من البيانات وحاول مرة أخرى"

    # تحديث CSRF دائمًا
    csrf_token = generate_csrf_token()
    request.session["csrf_token"] = csrf_token

    return templates.TemplateResponse("family/add_name.html", {
        "request": request,
        "user": user,
        "error": error,
        "success": success,
        "csrf_token": csrf_token,
        # إعادة تمرير القيم لو في خطأ
        "form_data": {
            "code": code, "name": name, "f_code": f_code, "m_code": m_code,
            "w_code": w_code, "h_code": h_code, "relation": relation,
            "level": level, "nick_name": nick_name, "gender": gender,
            "d_o_b": d_o_b, "d_o_d": d_o_d, "email": email,
            "phone": phone, "address": address, "p_o_b": p_o_b, "status": status
        } if error else None
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
async def update_name(request: Request, code: str,
                      name: str = Form(...), f_code: str = Form(None), m_code: str = Form(None),
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