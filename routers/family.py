# المكتبات القياسية (Standard Library)
import html 
import os
import re
from typing import Optional
from datetime import date 
import urllib.parse

# المكتبات الخارجية (Third-party)
from fastapi import APIRouter, Request, Form, UploadFile, File, HTTPException, Query
from fastapi.responses import HTMLResponse, RedirectResponse
from dotenv import load_dotenv

# المكتبات المحلية (Local Imports)
from core.templates import templates
from security.session import SessionService
from utils.time_utils import calculate_age_details
from services.analytics_service import AnalyticsService
from services.family_service import FamilyService

load_dotenv()
IMPORT_PASSWORD = os.getenv("IMPORT_PASSWORD", "change_me_in_production")

router = APIRouter(prefix="/family", tags=["family"])

# 🔒 القيود الأمنية الصارمة للمملفات
ALLOWED_IMAGE_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.webp'}
ALLOWED_IMAGE_MIME_TYPES = {"image/jpeg", "image/png", "image/webp"}
MAX_IMAGE_SIZE = 5 * 1024 * 1024  # 5 ميجابايت كحد أقصى للصورة الشخصية
PARENT_CODE_PATTERN = r"^[A-Z]\d{1,3}-\d{3}-\d{3}$"  

def validate_parent_code(code_value: Optional[str], code_name: str) -> Optional[str]:
    if code_value and not re.fullmatch(PARENT_CODE_PATTERN, code_value):
        return f"صيغة كود {code_name} غير صحيحة (مثال: A0-000-001)"
    return None

def clean_search_query(q: Optional[str]) -> str:
    """تنظيف نصوص البحث لمنع ثغرات التوجيه وكسر السطور HTTP Response Splitting"""
    if not q or q.strip() == "" or q == "None":
        return ""
    cleaned = re.sub(r"[\r\n\x00-\x1F\x7F]", "", q.strip())
    return cleaned

# ====================== قائمة الأعضاء ======================
@router.get("/", response_class=HTMLResponse)
async def show_family(
    request: Request, 
    page: int = Query(1, ge=1), 
    q: str = Query(None),
    success: Optional[str] = Query(None)
):
    cxt = SessionService.get_page_context(request, additional_perms=["view_tree", "add_member", "edit_member", "delete_member"])
    if not cxt or not cxt.get("user"):
        return RedirectResponse("/auth/login?error=unauthorized")
   
    success_message = None
    if success == "member_deleted":
        success_message = "✅ تم حذف العضو بنجاح والملفات المرتبطة به من السحاب."
    elif success == "member_updated":
        success_message = "✅ تم تحديث بيانات العضو وتحديث الصورة بنجاح."
    elif success == "member_added":
        success_message = "✅ تم إضافة العضو ورفع صورته إلى السحاب بنجاح."

    search_query = clean_search_query(q)
    members, current_page, totals_pages, total_count = FamilyService.search_and_fetch_family(search_query, page)
        
    PAGES_TO_SHOW = 7
    page_numbers = set()
    page_numbers.add(1)
    if totals_pages > 1:
        page_numbers.add(totals_pages)
        
    start = max(2, page - PAGES_TO_SHOW // 2)
    end = min(totals_pages - 1, page + PAGES_TO_SHOW // 2)
    
    if start <= 2:
        end = min(totals_pages - 1, PAGES_TO_SHOW + 1)
    if end >= totals_pages - 1:
        start = max(2, totals_pages - PAGES_TO_SHOW)
        
    for p in range(start, end + 1):
        if p > 1 and p < totals_pages:
            page_numbers.add(p)
    page_numbers = sorted(list(page_numbers))
    
    context = {**cxt}
    context.update({
        "members": members, "current_page": current_page, 
        "totals_pages": totals_pages, "page_numbers": page_numbers, 
        "q": search_query, "success": success_message
    })
    
    response = templates.TemplateResponse("family/family.html", context)
    SessionService.set_cache_headers(response)
    return response 

# ====================== تفاصيل العضو ======================
@router.get("/details/{code}", response_class=HTMLResponse)
async def name_details(request: Request, code: str, page: int = Query(1, ge=1), q: str = Query("")):
    cxt = SessionService.get_page_context(request, additional_perms=["view_tree", "edit_member"])
    if not cxt or not cxt.get("user"): 
        return RedirectResponse("/auth/login")

    if not cxt.get("perms", {}).get("view_tree", False):
        raise HTTPException(status_code=403, detail="لا تملك صلاحية الاطلاع")
   
    details = FamilyService.get_member_details(code.strip().upper())
    if not details:
        raise HTTPException(status_code=404, detail="العضو غير موجود")
    
    member_data = details["member"] 
    age_details = calculate_age_details(member_data.get("d_o_b"), member_data.get("d_o_d"))
    db_age = member_data.get("age_at_death")
    if db_age is not None and str(db_age).isdigit():
        age_details["age_at_death"] = int(db_age)

    context = {**cxt}
    context.update({
        "member": member_data, "info": member_data, "full_name": details["full_name"],
        "mother_full_name": details["mother_name"], "father_full_name": details.get("father_full_name", ""),
        "children": details["children"], "picture_url": details["picture_url"], "age_details": age_details,
        "gender": member_data.get("gender"), "wives": details.get("wives", []), "husbands": details.get("husbands", []),
        "current_page": page, "search_query": clean_search_query(q)
    })
    
    response = templates.TemplateResponse("family/details.html", context)
    SessionService.set_cache_headers(response)
    return response  

# ====================== إضافة عضو جديد ======================
@router.get("/add", response_class=HTMLResponse)
async def add_name_form(request: Request):
    cxt = SessionService.get_page_context(request, additional_perms=["view_tree", "add_member"])
    if not cxt or not cxt.get("perms", {}).get("add_member", False):
         return RedirectResponse(url="/family/?error=unauthorized", status_code=303)
    
    empty_form_data = {
        "code": "", "name": "", "f_code": "", "m_code": "", "w_code": "", "h_code": "", 
        "relation": "", "level": "", "nick_name": "", "gender": "", "d_o_b": "", 
        "d_o_d": "", "email": "", "phone": "", "address": "", "p_o_b": "", "status": ""
    }

    context = {**cxt}
    context.update({"error": None, "form_data": empty_form_data})
    response = templates.TemplateResponse("family/add_name.html", context)
    SessionService.set_cache_headers(response)
    return response
  
@router.post("/add")
async def add_name(
    request: Request,
    code: str = Form(...), name: str = Form(...),
    f_code: Optional[str] = Form(None), m_code: Optional[str] = Form(None),
    w_code: Optional[str] = Form(None), h_code: Optional[str] = Form(None),
    relation: Optional[str] = Form(None), level: Optional[str] = Form(None), 
    nick_name: Optional[str] = Form(None), gender: Optional[str] = Form(None),
    d_o_b: Optional[str] = Form(None), d_o_d: Optional[str] = Form(None),
    email: Optional[str] = Form(None), phone: Optional[str] = Form(None),
    address: Optional[str] = Form(None), p_o_b: Optional[str] = Form(None),
    status: Optional[str] = Form(None), picture: Optional[UploadFile] = File(None)
):
    cxt = SessionService.get_page_context(request, additional_perms=["add_member"])
    user = cxt.get("user")
    if not user or not cxt.get("perms", {}).get("add_member", False):
        raise HTTPException(status_code=403, detail="لا تملك صلاحية الإضافة")
    
    form = await request.form()
    SessionService.verify_csrf_token(request, form.get("csrf_token"))

    code = code.strip().upper() if code else ""
    name = html.escape(name.strip()) if name else ""
    f_code = f_code.strip().upper() if (f_code and f_code.strip()) else None
    m_code = m_code.strip().upper() if (m_code and m_code.strip()) else None
    w_code = w_code.strip().upper() if (w_code and w_code.strip()) else None
    h_code = h_code.strip().upper() if (h_code and h_code.strip()) else None
    relation = html.escape(relation.strip()) if (relation and relation.strip()) else None
    nick_name = html.escape(nick_name.strip()) if (nick_name and nick_name.strip()) else None 
    gender = gender.strip() if (gender and gender.strip()) else None
    d_o_b = d_o_b.strip() if (d_o_b and d_o_b.strip()) else None
    d_o_d = d_o_d.strip() if (d_o_d and d_o_d.strip()) else None
    email = email.strip().lower() if (email and email.strip()) else None
    phone = phone.strip() if (phone and phone.strip()) else None
    address = html.escape(address.strip()) if (address and address.strip()) else None
    p_o_b = html.escape(p_o_b.strip()) if (p_o_b and p_o_b.strip()) else None
    status = status.strip() if (status and status.strip()) else None

    level_int = None 
    error = None

    if not re.fullmatch(PARENT_CODE_PATTERN, code):
        error = "صيغة الكود الشخصي غير صحيحة!<br>الصيغة الصحيحة: <strong>A0-000-001</strong>"
    elif not name:
        error = "الاسم حقل مطلوب ولا يمكن تركه فارغاً"
    elif not re.fullmatch(r"[\u0600-\u06FF\s]+", html.unescape(name)):
        error = "الاسم يجب أن يحتوي على حروف عربية فقط"

    if not error:
        if level and level.strip():
            try:
                level_int = int(level)
                if level_int < 1: error = "المستوى يجب أن يكون رقماً موجباً."
            except ValueError: error = "المستوى يجب أن يكون رقماً صحيحاً."
        else: error = "المستوى مطلوب ولا يمكن أن يكون فارغاً."

    if not error and nick_name and not re.fullmatch(r"[\u0600-\u06FF\s]+", html.unescape(nick_name)):
        error = "اللقب يجب أن يكون حروف عربية فقط"
    if not error and p_o_b and (html.unescape(p_o_b)[0].isdigit() or re.search(r"^[\s\-\_\.\@\#\!\$\%\^\&\*\(\)]", html.unescape(p_o_b))):
        error = "مكان الميلاد لا يجب أن يبدأ برمز أو رقم"
    if not error and address and (html.unescape(address)[0].isdigit() or re.search(r"^[\s\-\_\.\@\#\!\$\%\^\&\*\(\)]", html.unescape(address))):
        error = "العنوان لا يجب أن يبدأ برمز أو رقم"
    if not error and email and not re.fullmatch(r"[^@]+@[^@]+\.[^@]+", email):
        error = "البريد الإلكتروني غير صالح"
    if not error and phone and not re.fullmatch(r"[\d\s\-\+\(\)]{8,20}", phone):
        error = "رقم الهاتف غير صالح"

    today = date.today()
    if not error and d_o_b:
        try:
            dob = date.fromisoformat(d_o_b)
            if dob > today: error = "تاريخ الميلاد لا يمكن أن يكون في المستقبل"
        except ValueError: error = "تاريخ الميلاد غير صالح"

    if not error and d_o_d:
        try:
            dod = date.fromisoformat(d_o_d)
            if dod > today: error = "تاريخ الوفاة لا يمكن أن يكون في المستقبل"
            if d_o_b and dod < date.fromisoformat(d_o_b): error = "تاريخ الوفاة لا يمكن أن يكون قبل تاريخ الميلاد"
        except ValueError: error = "تاريخ الوفاة غير صالح"

    if not error and f_code: error = validate_parent_code(f_code, "الأب")
    if not error and m_code: error = validate_parent_code(m_code, "الأم")
    if not error and h_code: error = validate_parent_code(h_code, "الزوج")
    if not error and w_code: error = validate_parent_code(w_code, "الزوجة")

    if not error and FamilyService.is_code_exists(code):
        error = "هذا الكود مستخدم من قبل! اختر كودًا آخر."

    # 🔒 فحص الصورة والتحقق من الحجم والميّم
    ext = None
    if not error and picture and picture.filename:
        ext = os.path.splitext(picture.filename)[1].lower()
        if ext not in ALLOWED_IMAGE_EXTENSIONS or picture.content_type not in ALLOWED_IMAGE_MIME_TYPES:
            error = "نوع الصورة غير مدعوم! استخدم: JPG، PNG، WebP فقط"
        else:
            picture.file.seek(0, os.SEEK_END)
            file_size = picture.file.tell()
            picture.file.seek(0)
            if file_size > MAX_IMAGE_SIZE:
                error = "حجم الصورة كبير جداً! الحد الأقصى المسموح هو 5 ميجابايت"

    if not error:
        try:
            member_data = {
                "code": code, "name": name, "f_code": f_code, "m_code": m_code,
                "w_code": w_code, "h_code": h_code, "relation": relation, "level": level_int,
                "nick_name": nick_name, "d_o_b": d_o_b, "d_o_d": d_o_d, "gender": gender, 
                "email": email, "phone": phone, "address": address, "p_o_b": p_o_b, "status": status
            }

            # ⭐ [التعديل الجوهري]: تمرير الملف إلى خدمة الإضافة السحابية مباشرة
            FamilyService.add_new_member(member_data, picture, ext)
            AnalyticsService.log_action(user['id'], "إضافة فرد", f"تم إضافة {html.unescape(name)}")

            empty_form_data = {key: "" for key in ["code", "name", "f_code", "m_code", "w_code", "h_code", 
                                                "relation", "level", "nick_name", "gender", "d_o_b", 
                                                "d_o_d", "email", "phone", "address", "p_o_b", "status"]}
            
            context = {**cxt}
            context.update({"error": None, "success": f"تم حفظ {html.unescape(name)} ورفع الصورة لسحابة Google Drive بنجاح!", "form_data": empty_form_data})
            response = templates.TemplateResponse("family/add_name.html", context)
            SessionService.set_cache_headers(response)
            return response
           
        except Exception as e:
           print(f"DATABASE ERROR: {e}")
           error = f"حدث خطأ أثناء الحفظ: {str(e)}"
           
    context = {**cxt}
    context.update({
        "error": error, "success": None,
        "form_data": { 
            "code": code, "name": html.unescape(name), "f_code": f_code or "",
            "m_code": m_code or "", "w_code": w_code or "", "h_code": h_code or "",
            "relation": relation or "", "level": level or "", 
            "nick_name": html.unescape(nick_name) if nick_name else "", "gender": gender or "",
            "d_o_b": d_o_b or "", "d_o_d": d_o_d or "", "email": email or "", "phone": phone or "",
            "address": html.unescape(address) if address else "", "p_o_b": html.unescape(p_o_b) if p_o_b else "", "status": status or ""
        }
    })
    response = templates.TemplateResponse("family/add_name.html", context)
    SessionService.set_cache_headers(response)
    return response

@router.get("/get-next-code")
async def suggest_code(prefix: Optional[str] = None, letter: Optional[str] = None): 
    search_term = prefix or letter
    if not search_term:
        return {"next_code": ""}
    next_code = FamilyService.get_next_code(search_term.strip().upper())
    return {"next_code": next_code}

@router.get("/check-code-availability")
async def check_code(code: str):
    exists = FamilyService.is_code_exists(code.strip().upper())
    return {"available": not exists}

@router.get("/edit/{code}", response_class=HTMLResponse)
async def edit_name_form(request: Request, code: str):
    cxt = SessionService.get_page_context(request, additional_perms=["view_tree", "edit_member"])
    if not cxt or not cxt.get("perms", {}).get("edit_member", False):
         return RedirectResponse(url="/family/?error=unauthorized", status_code=303)
  
    details = FamilyService.get_member_for_edit(code.strip().upper())
    if not details:
        return templates.TemplateResponse("family/edit_name.html", {**cxt, "code": code, "error": "العضو غير موجود أو تم حذفه"})

    context = {**cxt}
    context.update({"member": details["member"], "info": details["info"], "picture_url": details["picture_url"], "code": code, "error": None})
    response = templates.TemplateResponse("family/edit_name.html", context)
    SessionService.set_cache_headers(response)
    return response

@router.post("/edit/{code}")
async def update_name(
    request: Request, 
    code: str, name: str = Form(...), 
    f_code: str = Form(None), m_code: str = Form(None),
    w_code: str = Form(None), h_code: str = Form(None),
    relation: str = Form(None), level: str = Form(None), 
    nick_name: str = Form(None), gender: str = Form(None),
    d_o_b_str: Optional[str] = Form(None, alias="d_o_b"), 
    d_o_d_str: Optional[str] = Form(None, alias="d_o_d"),
    email: str = Form(None), phone: str = Form(None),
    address: str = Form(None), p_o_b: str = Form(None),
    status: str = Form(None), picture: UploadFile = File(None),
    page: int = Form(1), q: str = Form("")
):
    cxt = SessionService.get_page_context(request, additional_perms=["edit_member"])
    user = cxt["user"]
    if not cxt.get("perms", {}).get("edit_member", False):
        raise HTTPException(status_code=403, detail="لا تملك صلاحية التعديل")

    form = await request.form()
    SessionService.verify_csrf_token(request, form.get("csrf_token"))

    error = None
    level_int = None 
    
    name = name.strip()
    f_code = f_code.strip().upper() if f_code else None
    m_code = m_code.strip().upper() if m_code else None
    w_code = w_code.strip().upper() if w_code else None
    h_code = h_code.strip().upper() if h_code else None
    relation = html.escape(relation.strip()) if relation else None
    nick_name = nick_name.strip() if nick_name else None
    gender = gender.strip() if gender else None
    d_o_b_str = d_o_b_str.strip() if d_o_b_str else None
    d_o_d_str = d_o_d_str.strip() if d_o_d_str else None
    email = email.strip().lower() if email else None
    phone = phone.strip() if phone else None
    address = html.escape(address.strip()) if address else None
    p_o_b = html.escape(p_o_b.strip()) if p_o_b else None
    status = status.strip() if status else None
    
    try:
        d_o_b = date.fromisoformat(d_o_b_str) if d_o_b_str else None
        d_o_d = date.fromisoformat(d_o_d_str) if d_o_d_str else None
    except ValueError:
        error = "صيغة تاريخ الميلاد أو الوفاة غير صحيحة."
        d_o_b = None
        d_o_d = None

    if not error and not re.fullmatch(r"[\u0600-\u06FF\s]+", name):
        error = "الاسم يجب أن يحتوي على حروف عربية فقط"

    if not error and level:
        try:
            level_int = int(level)
            if level_int < 1: error = "المستوى يجب أن يكون رقماً موجباً."
        except ValueError: error = "المستوى يجب أن يكون رقماً صحيحاً."
    elif not error:
        error = "المستوى مطلوب ولا يمكن أن يكون فارغاً."
    
    if not error and nick_name and not re.fullmatch(r"[\u0600-\u06FF\s]+", nick_name):
        error = "اللقب يجب أن يكون حروف عربية فقط"
    if not error and p_o_b and (p_o_b[0].isdigit() or re.search(r"^[\s\-\_\.\@\#\!\$\%\^\&\*\(\)]", p_o_b)):
        error = "مكان الميلاد لا يجب أن يبدأ برمز أو رقم"
    if not error and address and (address[0].isdigit() or re.search(r"^[\s\-\_\.\@\#\!\$\%\^\&\*\(\)]", address)):
        error = "العنوان لا يجب أن يبدأ برمز أو رقم"
    if not error and email and not re.fullmatch(r"[^@]+@[^@]+\.[^@]+", email):
        error = "البريد الإلكتروني غير صالح"
    if not error and phone and not re.fullmatch(r"[\d\s\-\+\(\)]{8,20}", phone):
        error = "رقم الهاتف غير صالح"

    today = date.today()
    if not error and d_o_b and d_o_b > today: error = "تاريخ الميلاد لا يمكن أن يكون في المستقبل"
    if not error and d_o_d:
        if d_o_d > today: error = "تاريخ الوفاة لا يمكن أن يكون في المستقبل"
        if d_o_b and d_o_d < d_o_b: error = "تاريخ الوفاة لا يمكن أن يكون قبل تاريخ الميلاد"

    if not error:
        if f_code_error := validate_parent_code(f_code, "الأب"): error = f_code_error
        elif m_code_error := validate_parent_code(m_code, "الأم"): error = m_code_error
        elif h_code_error := validate_parent_code(h_code, "الزوج"): error = h_code_error
        elif w_code_error := validate_parent_code(w_code, "الزوجة"): error = w_code_error
 
    ext = None
    if not error and picture and picture.filename:
        ext = os.path.splitext(picture.filename)[1].lower()
        if ext not in ALLOWED_IMAGE_EXTENSIONS or picture.content_type not in ALLOWED_IMAGE_MIME_TYPES:
            error = "نوع الصورة غير مدعوم! استخدم: JPG، PNG، WebP فقط"
        else:
            await picture.seek(0, os.SEEK_END)
            file_size = await picture.tell()
            await picture.seek(0)
            if file_size > MAX_IMAGE_SIZE:
                error = "حجم الصورة كبير جداً! الحد الأقصى 5 ميجابايت"

    if not error:
        try:
            member_data = {
                "name": name, "f_code": f_code, "m_code": m_code, "w_code": w_code, 
                "h_code": h_code, "relation": relation, "level": level_int, 
                "nick_name": nick_name, "gender": gender, "d_o_b": d_o_b, "d_o_d": d_o_d, 
                "email": email, "phone": phone, "address": address, "p_o_b": p_o_b, "status": status
            }

            # ⭐ [التعديل الجوهري]: تمرير كائن الصورة السحابي لخدمة التعديل مباشرة
            FamilyService.update_member_data(code, member_data, picture, ext)
            AnalyticsService.log_action(user['id'], "تعديل فرد", f"تم تعديل بيانات العضو {name} ({code})")

            clean_q = clean_search_query(q)
            redirect_url = f"/family?page={page}"
            if clean_q:
                redirect_url += f"&q={urllib.parse.quote(clean_q)}"
            
            return RedirectResponse(url=redirect_url + "&success=member_updated", status_code=303)
          
        except Exception as e:
            print(f"DATABASE ERROR: {e}")
            error = f"حدث خطأ أثناء التحديث: {str(e)}"
        
    details = FamilyService.get_member_for_edit(code)
    if details:
        member, info, picture_url = details["member"], details["info"], details["picture_url"]
        member["name"] = name
        member["level"] = level
        member["nick_name"] = nick_name
        member["f_code"] = f_code
        member["m_code"] = m_code
        member["w_code"] = w_code
        member["h_code"] = h_code
        member["relation"] = relation
        info.update({"gender": gender, "phone": phone, "email": email, "address": address, "p_o_b": p_o_b, "status": status, "d_o_b": d_o_b_str, "d_o_d": d_o_d_str})
    else:
        member = {"code": code, "name": name, "level": level, "nick_name": nick_name, "f_code": f_code, "m_code": m_code, "w_code": w_code, "h_code": h_code, "relation": relation}
        info = {"d_o_b": d_o_b_str, "d_o_d": d_o_d_str, "email": email, "phone": phone, "address": address, "p_o_b": p_o_b, "status": status, "gender": gender}
        picture_url = None

    context = {**cxt}
    context.update({"member": member, "info": info, "picture_url": picture_url, "code": code, "error": error})
    return templates.TemplateResponse("family/edit_name.html", context)

# ====================== حذف عضو ======================
@router.post("/delete/{code}")
async def delete_name(request: Request, code: str, current_page: int = Form(1), q: str = Form("")):
    cxt = SessionService.get_page_context(request, additional_perms=["delete_member"])
    if not cxt or not cxt.get("perms", {}).get("delete_member", False):
        raise HTTPException(status_code=403, detail="لا تملك الصلاحية")

    form = await request.form()
    SessionService.verify_csrf_token(request, form.get("csrf_token"))

    try:
        FamilyService.delete_member(code.strip().upper())
        AnalyticsService.log_action(cxt["user"]['id'], "حذف فرد", f"الكود: {code}")
        
        clean_q = clean_search_query(q)
        redirect_url = f"/family?page={current_page}"
        if clean_q:
            redirect_url += f"&q={urllib.parse.quote(clean_q)}"
        return RedirectResponse(redirect_url + "&success=member_deleted", status_code=303)
        
    except Exception as e:
        print(f"❌ Error during deletion: {e}")
        raise HTTPException(status_code=500, detail="فشل في عملية الحذف السحابي وقاعدة البيانات")