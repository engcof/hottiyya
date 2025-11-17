# app/routes/family.py
from fastapi import APIRouter, Request, Form, UploadFile, File, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from services.family_service import get_full_name
from security.session import get_current_user
from postgresql import get_db_context
from psycopg2.extras import RealDictCursor
from fastapi.templating import Jinja2Templates
from utils.permissions import has_permission  # ← أضف هذا
import shutil
import os

router = APIRouter(prefix="/names", tags=["family"])
templates = Jinja2Templates(directory="templates")
UPLOAD_DIR = "static/uploads"
os.makedirs(UPLOAD_DIR, exist_ok=True)

# دالة مساعدة للتحقق من الصلاحية (الأدمن عنده كل شيء)
def can(user: dict, perm: str) -> bool:
    if not user:
        return False
    if user.get("role") == "admin":
        return True
    user_id = user.get("id")
    return user_id and has_permission(user_id, perm)

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
    search_query = f"%{q}%" if q else None

    with get_db_context() as conn:
        with conn.cursor() as cur:
            if search_query:
                cur.execute("""
                    SELECT code FROM family_name
                    WHERE code ILIKE %s OR name ILIKE %s
                    ORDER BY code LIMIT %s OFFSET %s
                """, (search_query, search_query, ITEMS_PER_PAGE, offset))
                rows = cur.fetchall()
                cur.execute("SELECT COUNT(*) FROM family_name WHERE code ILIKE %s OR name ILIKE %s", (search_query, search_query))
                total = cur.fetchone()[0]
            else:
                cur.execute("SELECT code FROM family_name ORDER BY code LIMIT %s OFFSET %s", (ITEMS_PER_PAGE, offset))
                rows = cur.fetchall()
                cur.execute("SELECT COUNT(*) FROM family_name")
                total = cur.fetchone()[0]

            total_pages = (total + ITEMS_PER_PAGE - 1) // ITEMS_PER_PAGE
            members = [{"code": r[0], "full_name": get_full_name(r[0])} for r in rows]

    return templates.TemplateResponse("family/names.html", {
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

    

@router.get("/details/{code}", response_class=HTMLResponse)
async def name_details(request: Request, code: str):
    if not request.session.get("user"):
        return RedirectResponse(url="/login", status_code=303)

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
            if not gender and member.get("type"):
                t = member["type"]
                if "ابن" in t or "زوج" in t:
                    gender = "ذكر"
                elif "ابنة" in t or "زوجة" in t:
                    gender = "أنثى"
            full_name = get_full_name(code)
            mother_full_name = get_full_name(member["m_code"]) if member.get("m_code") else ""
            wives = []
            if gender == "ذكر":
                cur.execute("SELECT code FROM family_name WHERE h_code = %s", (code,))
                for w in cur.fetchall():
                    wives.append({"code": w["code"], "name": get_full_name(w["code"])})
            husbands = []
            if gender == "أنثى":
                cur.execute("SELECT code FROM family_name WHERE w_code = %s", (code,))
                for h in cur.fetchall():
                    husbands.append({"code": h["code"], "name": get_full_name(h["code"])})
            cur.execute("SELECT code FROM family_name WHERE f_code = %s OR m_code = %s", (code, code))
            children = [{"code": c["code"], "name": get_full_name(c["code"])} for c in cur.fetchall()]

    return templates.TemplateResponse("family/details.html", {
        "request": request,
        "username": request.session.get("user"),
        "member": member,
        "info": info,
        "picture_url": picture_url,
        "full_name": full_name,
        "mother_full_name": mother_full_name,
        "wives": wives,
        "husbands": husbands,
        "children": children,
        "gender": gender
    })

#=== إضافة عضو ===
@router.get("/add", response_class=HTMLResponse)
async def add_name_form(request: Request):
    user = request.session.get("user")
    if not user or not can(user, "add_member"):
        return RedirectResponse("/names")
    return templates.TemplateResponse("family/add_name.html", {
        "request": request, "user": user, "error": None
    })

@router.post("/names/add")
async def add_name(
    request: Request,
    code: str = Form(...),
    name: str = Form(...),
    f_code: str = Form(None),
    m_code: str = Form(None),
    w_code: str = Form(None),
    h_code: str = Form(None),
    type: str = Form(None),
    level: int = Form(None),
    gender: str = Form(None),
    d_o_b: str = Form(None),
    d_o_d: str = Form(None),
    email: str = Form(None),
    phone: str = Form(None),
    address: str = Form(None),
    p_o_b: str = Form(None),
    picture: UploadFile = File(None),
      **form_data
):
   
    user = request.session.get("user")
    if not user or not can(user, "add_member"):
        return RedirectResponse("/names")

    error = None
    code = code.strip()
    name = name.strip()
    f_code = f_code.strip() if f_code and f_code.strip() else None
    m_code = m_code.strip() if m_code and m_code.strip() else None
    w_code = w_code.strip() if w_code and w_code.strip() else None
    h_code = h_code.strip() if h_code and h_code.strip() else None
    type = type.strip() if type and type.strip() else None
    gender = gender.strip() if gender and gender.strip() else None
    d_o_b = d_o_b.strip() if d_o_b and d_o_b.strip() else None
    d_o_d = d_o_d.strip() if d_o_d and d_o_d.strip() else None
    email = email.strip() if email and email.strip() else None
    phone = phone.strip() if phone and phone.strip() else None
    address = address.strip() if address and address.strip() else None
    p_o_b = p_o_b.strip() if p_o_b and p_o_b.strip() else None

    if not code or not name:
        error = "الكود والاسم مطلوبان!"
        return templates.TemplateResponse("add_name.html", {
            "request": request,
            "username": request.session.get("user"),
            "error": error
        })

    try:
        with get_db_context() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT code FROM family_name WHERE code = %s", (code,))
                if cur.fetchone():
                    error = "الكود مستخدم مسبقاً! اختر كوداً آخر."
                if not error:
                    cur.execute("""
                        INSERT INTO family_name (code, name, f_code, m_code, w_code, h_code, type, level)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                    """, (code, name, f_code, m_code, w_code, h_code, type, level))
                    cur.execute("""
                        INSERT INTO family_info (code_info, gender, d_o_b, d_o_d, email, phone, address, p_o_b)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                    """, (code, gender, d_o_b, d_o_d, email, phone, address, p_o_b))
                    if picture and picture.filename:
                        pic_path = os.path.join(UPLOAD_DIR, picture.filename)
                        with open(pic_path, "wb") as buffer:
                            shutil.copyfileobj(picture.file, buffer)
                        cur.execute("INSERT INTO family_picture (code_pic, pic_path) VALUES (%s, %s)", (code, pic_path))
                    conn.commit()
                    return RedirectResponse("/names", status_code=303)
    except Exception as e:
        error = "حدث خطأ غير متوقع. حاول مرة أخرى."

    return templates.TemplateResponse("family/add_name.html", {
        "request": request,
        "username": request.session.get("user"),
        "error": error
    })

# === تعديل عضو ===
@router.get("/edit/{code}", response_class=HTMLResponse)
async def edit_name_form(request: Request, code: str):
    user = request.session.get("user")
    if not user or not can(user, "edit_member"):
        return RedirectResponse("/names")

    with get_db_context() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            # جلب بيانات العضو
            cur.execute("SELECT * FROM family_name WHERE code = %s", (code,))
            member = cur.fetchone()
            if not member:
                raise HTTPException(status_code=404, detail="العضو غير موجود")

            cur.execute("SELECT * FROM family_info WHERE code_info = %s", (code,))
            info = cur.fetchone() or {}

            cur.execute("SELECT pic_path FROM family_picture WHERE code_pic = %s", (code,))
            pic = cur.fetchone()
            picture_url = pic["pic_path"] if pic else None

    return templates.TemplateResponse("family/edit_name.html", {
        "request": request,
        "user": user,
        "member": member,
        "info": info,
        "picture_url": picture_url,
        "code": code,
        "full_name": get_full_name(code)
    })

@router.post("/names/edit/{code}")
async def update_name(
    request: Request,
    code: str,
    name: str = Form(...),
    f_code: str = Form(None),
    m_code: str = Form(None),
    w_code: str = Form(None),
    h_code: str = Form(None),
    type: str = Form(None),
    level: int = Form(None),
    gender: str = Form(None),
    d_o_b: str = Form(None),
    d_o_d: str = Form(None),
    email: str = Form(None),
    phone: str = Form(None),
    address: str = Form(None),
    p_o_b: str = Form(None),
    picture: UploadFile = File(None),
    **form_data
):
    user = request.session.get("user")
    if not user or not can(user, "edit_member"):
        return RedirectResponse("/names")

    # تنظيف البيانات
    name = name.strip()
    f_code = f_code.strip() if f_code and f_code.strip() else None
    m_code = m_code.strip() if m_code and m_code.strip() else None
    w_code = w_code.strip() if w_code and w_code.strip() else None
    h_code = h_code.strip() if h_code and h_code.strip() else None
    type = type.strip() if type and type.strip() else None
    gender = gender.strip() if gender and gender.strip() else None
    d_o_b = d_o_b.strip() if d_o_b and d_o_b.strip() else None
    d_o_d = d_o_d.strip() if d_o_d and d_o_d.strip() else None
    email = email.strip() if email and email.strip() else None
    phone = phone.strip() if phone and phone.strip() else None
    address = address.strip() if address and address.strip() else None
    p_o_b = p_o_b.strip() if p_o_b and p_o_b.strip() else None

    try:
        with get_db_context() as conn:
            with conn.cursor() as cur:
                # تحديث family_name
                cur.execute("""
                    UPDATE family_name SET 
                    name=%s, f_code=%s, m_code=%s, w_code=%s, h_code=%s, type=%s, level=%s
                    WHERE code=%s
                """, (name, f_code, m_code, w_code, h_code, type, level, code))

                # تحديث أو إضافة family_info
                cur.execute("SELECT code_info FROM family_info WHERE code_info = %s", (code,))
                if cur.fetchone():
                    cur.execute("""
                        UPDATE family_info SET 
                        gender=%s, d_o_b=%s, d_o_d=%s, email=%s, phone=%s, address=%s, p_o_b=%s
                        WHERE code_info=%s
                    """, (gender, d_o_b, d_o_d, email, phone, address, p_o_b, code))
                else:
                    cur.execute("""
                        INSERT INTO family_info 
                        (code_info, gender, d_o_b, d_o_d, email, phone, address, p_o_b)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                    """, (code, gender, d_o_b, d_o_d, email, phone, address, p_o_b))

                # تحديث الصورة
                if picture and picture.filename:
                    pic_path = os.path.join(UPLOAD_DIR, picture.filename)
                    with open(pic_path, "wb") as buffer:
                        shutil.copyfileobj(picture.file, buffer)
                    cur.execute("""
                        INSERT INTO family_picture (code_pic, pic_path) 
                        VALUES (%s, %s)
                        ON CONFLICT (code_pic) DO UPDATE SET pic_path = %s
                    """, (code, pic_path, pic_path))

                conn.commit()
    except Exception as e:
        raise HTTPException(status_code=500, detail="فشل في حفظ التعديلات")

    return RedirectResponse("/names", status_code=303)

# === حذف عضو ===
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
