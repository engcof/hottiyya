# المكتبات القياسية (Standard Library)
import html 
import os
import re
from typing import Optional
from datetime import date 

# المكتبات الخارجية (Third-party)
from fastapi import APIRouter, Request, Form, UploadFile, File, HTTPException, Query
from fastapi.responses import HTMLResponse, RedirectResponse
from dotenv import load_dotenv

# المكتبات المحلية (Local Imports)
from core.templates import templates
from security.csrf import  verify_csrf_token
from security.session import set_cache_headers,get_page_context
from utils.time_utils import calculate_age_details
from services.analytics import log_action
from services.family_service import FamilyService

import urllib.parse

load_dotenv()
IMPORT_PASSWORD = os.getenv("IMPORT_PASSWORD", "change_me_in_production")

router = APIRouter(prefix="/family", tags=["family"])

UPLOAD_DIR = "static/uploads"
os.makedirs(UPLOAD_DIR, exist_ok=True)

# ضعه داخل دالة add_name أو update_name
def validate_parent_code(code_value, code_name):
    parent_pattern = r"[A-Z]\d{0,3}-\d{3}-\d{3}"
    if code_value and not re.fullmatch(parent_pattern, code_value):
        return f"كود {code_name} غير صحيح"
    return None

# ====================== قائمة الأعضاء ======================
@router.get("/", response_class=HTMLResponse)
async def show_family(
    request: Request, 
    page: int = Query(1, ge=1), 
    q: str = Query(None),
    success: Optional[str] = Query(None)
):
    cxt = get_page_context(request, additional_perms=["view_tree", "add_member", "edit_member", "delete_member"])
    
    if not cxt or not cxt.get("user"):
        return RedirectResponse("/auth/login?error=unauthorized")
   
    # معالجة رسائل النجاح التنبيهية
    success_message = None
    if success == "member_deleted":
        success_message = "✅ تم حذف العضو بنجاح."
    elif success == "member_updated":
        success_message = "✅ تم تحديث بيانات العضو بنجاح."
    elif success == "member_added":
        success_message = "✅ تم إضافة العضو بنجاح."

    # تنظيف وتجهيز نص البحث
    search_query = q.strip() if (q and q.strip() != "" and q != "None") else ""
    
    # جلب البيانات من طبقة الخدمة الموحدة
    members, current_page, totals_pages, total_count = FamilyService.search_and_fetch_family(search_query, page)
        
    # منطق الترقيم الديناميكي (Pagination)
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
    
    # تحديث قاموس السياق وإرساله للقالب
    context = {**cxt}
    context.update({
        "members": members,
        "current_page": current_page, 
        "totals_pages": totals_pages,     
        "page_numbers": page_numbers, 
        "q": search_query, # نمرر النص المنظف لضمان عدم تمرير None أو النصوص الفارغة
        "success": success_message
    })
    
    response = templates.TemplateResponse("family/family.html", context)
    set_cache_headers(response)
    return response 

# ====================== تفاصيل العضو ======================
@router.get("/details/{code}", response_class=HTMLResponse)
async def name_details(
    request: Request, 
    code: str,
    page: int = Query(1), # استقبال رقم الصفحة من الرابط للمحافظة على حالة التصفح
    q: str = Query("")    # استقبال نص البحث من الرابط للمحافظة على حالة التصفح
):
    
    cxt = get_page_context(request, additional_perms=["view_tree", "edit_member"])
    user = cxt["user"]
    if not user: 
        return RedirectResponse("/auth/login")

    has_view_perm = cxt.get("perms", {}).get("view_tree", False)
    if not has_view_perm:
        raise HTTPException(status_code=403, detail="لا تملك صلاحية الاطلاع")
   
    details = FamilyService.get_member_details(code)
    if not details:
        raise HTTPException(status_code=404, detail="العضو غير موجود")
    
    member_data = details["member"] 
    
    # حساب العمر بناءً على التواريخ المسجلة
    age_details = calculate_age_details(member_data.get("d_o_b"), member_data.get("d_o_d"))
    db_age = member_data.get("age_at_death")
    if db_age is not None and str(db_age).isdigit():
        age_details["age_at_death"] = int(db_age)

    # تجهيز السياق الموحد والمحدث
    context = {**cxt}
    context.update({
        "member": member_data,     
        "info": member_data,       
        "full_name": details["full_name"],
        "mother_full_name": details["mother_name"],
        "children": details["children"],
        "picture_url": details["picture_url"],
        "age_details": age_details,
        "gender": member_data.get("gender"),
        "wives": details.get("wives", []), 
        "husbands": details.get("husbands", []),
        "current_page": page,
        "search_query": q.strip() if q else ""
    })
    
    response = templates.TemplateResponse("family/details.html", context)
    set_cache_headers(response)
    return response  

# ====================== إضافة عضو جديد ======================
@router.get("/add", response_class=HTMLResponse)
async def add_name_form(request: Request):
    cxt = get_page_context(request, additional_perms=["view_tree", "add_member"])
    if not cxt:
        return RedirectResponse(url="/family/?error=unauthorized", status_code=303)

    # التحقق من الصلاحية
    added = cxt.get("perms", {}).get("add_member", False)
    if not added:
         return RedirectResponse(url="/family/?error=unauthorized", status_code=303)
    
    empty_form_data = {
        "code": "", "name": "", "f_code": "", "m_code": "", "w_code": "", "h_code": "", 
        "relation": "", "level": "", "nick_name": "", "gender": "", "d_o_b": "", 
        "d_o_d": "", "email": "", "phone": "", "address": "", "p_o_b": "", "status": ""
    }

    context = {**cxt}
    context.update({
        "error": None,
        "form_data": empty_form_data
    })
    response = templates.TemplateResponse("family/add_name.html", context)
    set_cache_headers(response)
    return response
  

@router.post("/add")
async def add_name(
    request: Request,
    code: str = Form(...), 
    name: str = Form(...),
    f_code: Optional[str] = Form(None), 
    m_code: Optional[str] = Form(None),
    w_code: Optional[str] = Form(None), 
    h_code: Optional[str] = Form(None),
    relation: Optional[str] = Form(None), 
    level: Optional[str] = Form(None), 
    nick_name: Optional[str] = Form(None), 
    gender: Optional[str] = Form(None),
    d_o_b: Optional[str] = Form(None), 
    d_o_d: Optional[str] = Form(None),
    email: Optional[str] = Form(None), 
    phone: Optional[str] = Form(None),
    address: Optional[str] = Form(None), 
    p_o_b: Optional[str] = Form(None),
    status: Optional[str] = Form(None),
    picture: Optional[UploadFile] = File(None)
):
    cxt = get_page_context(request, additional_perms=["add_member"])
    user = cxt.get("user")
    if not user:
        return RedirectResponse("/family", status_code=303)
   
    added = cxt.get("perms", {}).get("add_member", False)
    if not added:
        raise HTTPException(status_code=403, detail="لا تملك صلاحية الإضافة")
    
    form = await request.form()
    verify_csrf_token(request, form.get("csrf_token"))

    # غسيل وتنظيف البيانات الصارم لمنع ثغرات الحشو وXSS وقيم الفراغات النصية
    code = code.strip().upper() if code else ""
    name = html.escape(name.strip()) if name else ""
    
    # تحويل السلاسل الفارغة تلقائياً إلى قِيَم لقاعدة البيانات الحقيقية None لعدم إتلاف الروابط
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
    success = None

    # ================================
    # التحقق من المدخلات الأساسية
    # ================================
    if not re.fullmatch(r"[A-Z]\d{0,3}-\d{3}-\d{3}", code):
        error = "صيغة الكود غير صحيحة!<br>الصيغة الصحيحة: <strong>A0-000-001</strong>"

    elif not name or name == "":
        error = "الاسم حقل مطلوب ولا يمكن تركه فارغاً"

    # فك تشفير حماية الفحص للاسم للتأكد الخالي من الرموز الخبيثة
    elif not re.fullmatch(r"[\u0600-\u06FF\s]+", html.unescape(name)):
        error = "الاسم يجب أن يحتوي على حروف عربية فقط (ممنوع الأرقام والرموز)"

    # التحقق من المستوى (الجيل)
    if not error:
        if level and level.strip():
            try:
                level_int = int(level)
                if level_int < 1:
                    error = "المستوى يجب أن يكون رقماً موجباً."
            except ValueError:
                error = "المستوى يجب أن يكون رقماً صحيحاً."
        else:
            error = "المستوى مطلوب ولا يمكن أن يكون فارغاً."

    # اللقب
    if not error and nick_name:
        if not re.fullmatch(r"[\u0600-\u06FF\s]+", html.unescape(nick_name)):
            error = "اللقب يجب أن يكون حروف عربية فقط (مثل: أبو أحمد)"

    # مكان الميلاد
    if not error and p_o_b:
        clean_pob = html.unescape(p_o_b)
        if clean_pob[0].isdigit() or re.search(r"^[\s\-\_\.\@\#\!\$\%\^\&\*\(\)]", clean_pob):
            error = "مكان الميلاد لا يجب أن يبدأ برمز أو رقم"

    # العنوان
    if not error and address:
        clean_addr = html.unescape(address)
        if clean_addr[0].isdigit() or re.search(r"^[\s\-\_\.\@\#\!\$\%\^\&\*\(\)]", clean_addr):
            error = "العنوان لا يجب أن يبدأ برمز أو رقم"

    # البريد الإلكتروني
    if not error and email:
        if not re.fullmatch(r"[^@]+@[^@]+\.[^@]+", email):
            error = "البريد الإلكتروني غير صالح (مثال: name@example.com)"

    # الهاتف
    if not error and phone:
        if not re.fullmatch(r"[\d\s\-\+\(\)]{8,20}", phone):
            error = "رقم الهاتف غير صالح"

    # التواريخ والأعمار
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

    # كود الأب/الأم/الزوج/الزوجة (تستدعى فقط إذا كانت مدخلة)
    if not error and f_code:
        if f_code_error := validate_parent_code(f_code, "الأب"): error = f_code_error
    if not error and m_code:
        if m_code_error := validate_parent_code(m_code, "الأم"): error = m_code_error
    if not error and h_code:
        if h_code_error := validate_parent_code(h_code, "الزوج"): error = h_code_error
    if not error and w_code:
        if w_code_error := validate_parent_code(w_code, "الزوجة"): error = w_code_error

    # تحقق من عدم تكرار الكود الشخصي
    if not error:
        if FamilyService.is_code_exists(code):
            error = "هذا الكود مستخدم من قبل! اختر كودًا آخر."

    # رفع وصلاحية الصورة الشخصية
    ext = None
    if not error and picture and picture.filename:
        allowed = {'.jpg', '.jpeg', '.png', '.webp'}
        ext = os.path.splitext(picture.filename)[1].lower()
        if ext not in allowed:
            error = "نوع الصورة غير مدعوم! استخدم: JPG، PNG، WebP فقط"

    # ================================
    # مسار الحفظ النهائي
    # ================================
    if not error:
        try:
            member_data = {
                "code": code, "name": name, "f_code": f_code, "m_code": m_code,
                "w_code": w_code, "h_code": h_code, "relation": relation, "level": level_int,
                "nick_name": nick_name, "d_o_b": d_o_b, "d_o_d": d_o_d, "gender": gender, 
                "email": email, "phone": phone, "address": address, "p_o_b": p_o_b, "status": status
            }

            FamilyService.add_new_member(member_data, picture, ext)
            log_action(user['id'], "إضافة فرد", f"تم إضافة {html.unescape(name)}")

            success = f"تم حفظ {html.unescape(name)} بنجاح!"
            
            # تصفير استمارة الإدخال للجاهزية لعضو آخر
            empty_form_data = {key: "" for key in ["code", "name", "f_code", "m_code", "w_code", "h_code", 
                                                "relation", "level", "nick_name", "gender", "d_o_b", 
                                                "d_o_d", "email", "phone", "address", "p_o_b", "status"]}
            
            context = {**cxt}
            context.update({
                "error": None, "success": success, "form_data": empty_form_data 
            })
            response = templates.TemplateResponse("family/add_name.html", context)
            set_cache_headers(response)
            return response
           
        except Exception as e:
           print(f"DATABASE ERROR: {e}")
           error = f"حدث خطأ أثناء الحفظ في قاعدة البيانات: {str(e)}"
           
    # مسار الفشل الموحد وإعادة الحفاظ على ما كتبه المستخدم لمنع الإحباط إعادة الملء
    context = {**cxt}
    context.update({
        "error": error, 
        "success": None,
        "form_data": { 
            "code": code, "name": html.unescape(name), "f_code": f_code or "",
            "m_code": m_code or "", "w_code": w_code or "", "h_code": h_code or "",
            "relation": relation or "", "level": level or "", 
            "nick_name": html.unescape(nick_name) if nick_name else "", "gender": gender or "",
            "d_o_b": d_o_b or "", "d_o_d": d_o_d or "", "email": email or "", "phone": phone or "",
            "address": html.unescape(address) if address else "", "p_o_b": html.unescape(p_o_b) if p_o_b else "",
            "status": status or ""
        }
    })
    response = templates.TemplateResponse("family/add_name.html", context)
    set_cache_headers(response)
    return response


@router.get("/get-next-code")
async def suggest_code(prefix: Optional[str] = None, letter: Optional[str] = None): 
    # 💡 [تصحيح الثغرة] استيعاب المعاملين (prefix و letter) معاً لعدم كسر طلبات الـ JavaScript
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
    cxt = get_page_context(request, additional_perms=["view_tree", "edit_member"])
    if not cxt:
        return RedirectResponse(url="/family/?error=unauthorized", status_code=303)

    edited = cxt.get("perms", {}).get("edit_member", False)
    if not edited:
         return RedirectResponse(url="/family/?error=unauthorized", status_code=303)
  
    details = FamilyService.get_member_for_edit(code)

    if not details:
        return templates.TemplateResponse("family/edit_name.html", {
            **cxt,
            "code": code,
            "error": "العضو غير موجود أو تم حذفه"
        })

    context = {**cxt}
    context.update({
        "member": details["member"], 
        "info": details["info"],
        "picture_url": details["picture_url"], 
        "code": code, 
        "error": None
    })
    response = templates.TemplateResponse("family/edit_name.html", context)
    set_cache_headers(response)
    return response

@router.post("/edit/{code}")
async def update_name(request: Request, 
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
                      page: int = Form(1),    
                      q: str = Form("")):
    
    cxt = get_page_context(request, additional_perms=["edit_member"])
    user = cxt["user"]
    edited = cxt.get("perms", {}).get("edit_member", False)
    if not edited:
        raise HTTPException(status_code=403, detail="لا تملك صلاحية التعديل")

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

    # === 2. التحقق من المدخلات (Input Validation) ===
    if not re.fullmatch(r"[\u0600-\u06FF\s]+", name):
        error = "الاسم يجب أن يحتوي على حروف عربية فقط (ممنوع الأرقام والرموز)"

    if not error and level:
        try:
            level_int = int(level)
            if level_int < 1:
                error = "المستوى يجب أن يكون رقماً موجباً."
        except ValueError:
            error = "المستوى يجب أن يكون رقماً صحيحاً."
    elif not error:
        error = "المستوى مطلوب ولا يمكن أن يكون فارغاً."
    
    if not error and nick_name and not re.fullmatch(r"[\u0600-\u06FF\s]+", nick_name):
        error = "اللقب يجب أن يكون حروف عربية فقط (مثل: أبو أحمد، أم علي)"

    elif not error and p_o_b and (p_o_b[0].isdigit() or re.search(r"^[\s\-\_\.\@\#\!\$\%\^\&\*\(\)]", p_o_b)):
        error = "مكان الميلاد لا يجب أن يبدأ برمز أو رقم"

    elif not error and address and (address[0].isdigit() or re.search(r"^[\s\-\_\.\@\#\!\$\%\^\&\*\(\)]", address)):
        error = "العنوان لا يجب أن يبدأ برمز أو رقم"

    elif not error and email and not re.fullmatch(r"[^@]+@[^@]+\.[^@]+", email):
        error = "البريد الإلكتروني غير صالح (مثال: name@example.com)"

    elif not error and phone and not re.fullmatch(r"[\d\s\-\+\(\)]{8,20}", phone):
        error = "رقم الهاتف غير صالح (استخدم أرقام، مسافات، +، -، () فقط)"

    today = date.today()
    if not error and d_o_b and d_o_b > today:
        error = "تاريخ الميلاد لا يمكن أن يكون في المستقبل"

    if not error and d_o_d:
        if d_o_d > today:
            error = "تاريخ الوفاة لا يمكن أن يكون في المستقبل"
        if d_o_b and d_o_d < d_o_b: 
            error = "تاريخ الوفاة لا يمكن أن يكون قبل تاريخ الميلاد"

    if f_code_error := validate_parent_code(f_code, "الأب"):
        error = f_code_error
    elif m_code_error := validate_parent_code(m_code, "الأم"):
        error = m_code_error
    elif h_code_error := validate_parent_code(h_code, "الزوج"):
        error = h_code_error
    elif w_code_error := validate_parent_code(w_code, "الزوجة"):
        error = w_code_error
 
    ext = None
    if not error and picture and picture.filename:
        allowed = {'.jpg', '.jpeg', '.png', '.webp'}
        ext = os.path.splitext(picture.filename)[1].lower()
        if ext not in allowed:
            error = "نوع الصورة غير مدعوم! استخدم: JPG، PNG، WebP فقط"

    # === 3. التنفيذ أو إرجاع الخطأ ===
    if not error:
        try:
            member_data = {
                "name": name, "f_code": f_code, "m_code": m_code, "w_code": w_code, 
                "h_code": h_code, "relation": relation, "level": level_int, 
                "nick_name": nick_name, "gender": gender, 
                "d_o_b": d_o_b, "d_o_d": d_o_d, 
                "email": email, "phone": phone, "address": address, 
                "p_o_b": p_o_b, "status": status
            }

            # 💡 تم الإصلاح: حذف سطر ext = None الكارثي الذي كان يصفر الامتداد
            FamilyService.update_member_data(code, member_data, picture, ext)
            
            log_action(
                user_id=user['id'], 
                action="تعديل فرد", 
                details=f"تم تعديل بيانات العضو {name} (الكود: {code}) بنجاح"
            )

            redirect_url = f"/family?page={page}"
            if q and q != "None" and q.strip() != "":
                redirect_url += f"&q={urllib.parse.quote(q.strip())}"
            
            return RedirectResponse(url=redirect_url, status_code=303)
          
        except Exception as e:
            print(f"DATABASE ERROR: {e}")
            error = f"حدث خطأ أثناء التحديث: {str(e)}"
        
    # ------------------------------------------------------------------
    # مسار الفشل (Failure Path) - إعادة بناء البيانات لعرضها في القالب مع الخطأ
    # ------------------------------------------------------------------
    details = FamilyService.get_member_for_edit(code)

    if details:
        member = details["member"]
        info = details["info"]
        picture_url = details["picture_url"]
        
        # دمج البيانات المدخلة في النموذج ليراها المستخدم معدلة مع الخطأ
        member["name"] = name
        member["level"] = level
        member["nick_name"] = nick_name
        member["f_code"] = f_code
        member["m_code"] = m_code
        member["w_code"] = w_code
        member["h_code"] = h_code
        member["relation"] = relation
        
        info["gender"] = gender
        info["phone"] = phone
        info["email"] = email
        info["address"] = address
        info["p_o_b"] = p_o_b
        info["status"] = status
        # 💡 تم الإصلاح: إرسال النصوص الأصلية للحقول (str) وليس كائن (date) كي يقرأها حقل الـ HTML بشكل صحيح
        info["d_o_b"] = d_o_b_str 
        info["d_o_d"] = d_o_d_str
    else:
        member = {"code": code, "name": name, "level": level, "nick_name": nick_name, "f_code": f_code, "m_code": m_code, "w_code": w_code, "h_code": h_code, "relation": relation}
        info = {"d_o_b": d_o_b_str, "d_o_d": d_o_d_str, "email": email, "phone": phone, "address": address, "p_o_b": p_o_b, "status": status, "gender": gender}
        picture_url = None

    context = {**cxt}
    context.update({
        "member": member,
        "info": info,
        "picture_url": picture_url,
        "code": code,
        "error": error
    })
    return templates.TemplateResponse("family/edit_name.html", context)

# ====================== حذف عضو ======================
@router.post("/delete/{code}")
async def delete_name(
    request: Request, 
    code: str,  
    current_page: int = Form(1),    # 💡 استلام رقم الصفحة
   q: str = Form("")
):
    cxt = get_page_context(request, additional_perms=["delete_member"])
    
    # 1. التحقق من الصلاحية
    if not cxt.get("perms", {}).get("delete_member", False):
        raise HTTPException(status_code=403, detail="لا تملك الصلاحية")

    # 2. التحقق من CSRF
    try:
        form = await request.form()
        verify_csrf_token(request, form.get("csrf_token"))
    except Exception:
        raise HTTPException(status_code=400, detail="خطأ في تحقق CSRF")

    try:
        # 3. الحذف والتسجيل
        FamilyService.delete_member(code)
        log_action(cxt["user"]['id'], "حذف فرد", f"الكود: {code}")
        
        # 4. إعادة التوجيه مع استخدام & بدلاً من الفاصلة
        redirect_url = f"/family?page={current_page}"
        if q and q != "None":
            redirect_url += f"&q={urllib.parse.quote(q)}"
        return RedirectResponse(redirect_url + "&success=member_deleted", status_code=303)
        
    except Exception as e:
        print(f"❌ Error during deletion: {e}") # سيظهر لك الخطأ الحقيقي في الـ Terminal
        raise HTTPException(status_code=500, detail="فشل في عملية الحذف من قاعدة البيانات")

