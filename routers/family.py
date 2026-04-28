# المكتبات القياسية (Standard Library)
import html 
import os
import re
from typing import Optional
from datetime import date 
from fastapi.responses import StreamingResponse

# المكتبات الخارجية (Third-party)
from fastapi import APIRouter, Request, Form, UploadFile, File, HTTPException, Query, Response
from fastapi.responses import HTMLResponse, RedirectResponse
from dotenv import load_dotenv

# المكتبات المحلية (Local Imports)
from core.templates import templates, get_global_context
from security.csrf import generate_csrf_token, verify_csrf_token
from security.session import set_cache_headers
from utils.has_permissions import can
from utils.time_utils import calculate_age_details
from services.analytics import log_action
from services.family_service import FamilyService


load_dotenv()
IMPORT_PASSWORD = os.getenv("IMPORT_PASSWORD", "change_me_in_production")

router = APIRouter(prefix="/names", tags=["family"])

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
async def show_names(
    request: Request, 
    page: int = Query(1, ge=1), 
    q: str = Query(None),
    success: Optional[str] = Query(None)
):
    user = request.session.get("user")
    if not user or not can(user, "view_tree"):
        return RedirectResponse("/?error=no_permission")

    can_add    = can(user, "add_member")
    can_edit   = can(user, "edit_member")
    can_delete = can(user, "delete_member")

    csrf_token = generate_csrf_token() 
    request.session["csrf_token"] = csrf_token

    # معالجة رسائل النجاح
    success_message = None
    if success == "member_deleted":
        success_message = "✅ تم حذف العضو بنجاح."
    elif success == "member_updated":
        success_message = "✅ تم تحديث بيانات العضو بنجاح."

    # 💡 استدعاء الكلاس FamilyService
    search_query = q.strip() if q else None
    
    # لاحظ أننا نستخدم FamilyService دائماً الآن
    members, current_page, totals_pages, total_count = FamilyService.search_and_fetch_names(search_query or "", page)
        
    # منطق الترقيم (Pagination)
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
    
    # 2. تجهيز السياق الموحد (سيحتوي على user و can_view و unread_count)
    context = get_global_context(request)
    
    # 3. تحديث السياق بالبيانات الخاصة بالصفحة الرئيسية
    context.update({
       "members": members,
        "current_page": current_page, "totals_pages": totals_pages,     
        "page_numbers": page_numbers, "q": q,
        "csrf_token": csrf_token, "can_add": can_add, "can_edit": can_edit,
        "can_delete": can_delete, "success": success_message
    })
    
    response = templates.TemplateResponse("family/names.html", context)
    set_cache_headers(response)
    return response
   
# ====================== تفاصيل العضو ======================
@router.get("/details/{code}", response_class=HTMLResponse)
async def name_details(
    request: Request, 
    code: str,
    page: int = Query(1), # 💡 استقبال رقم الصفحة من الرابط
    q: str = Query("")    # 💡 استقبال نص البحث من الرابط
    ):
    user = request.session.get("user")
    if not user: return RedirectResponse("/auth/login")

    details = FamilyService.get_member_details(code)
    if not details:
        raise HTTPException(status_code=404, detail="العضو غير موجود")
    
    # 💡 استخراج البيانات لتتوافق مع أسماء المتغيرات في القالب
    member_data = details["member"] 
    
    # حساب العمر
    age_details = calculate_age_details(member_data.get("d_o_b"), member_data.get("d_o_d"))
    db_age = member_data.get("age_at_death")
    if db_age is not None and str(db_age).isdigit():
        age_details["age_at_death"] = int(db_age)

    # 2. تجهيز السياق الموحد (سيحتوي على user و can_view و unread_count)
    context = get_global_context(request)
    
    # 3. تحديث السياق بالبيانات الخاصة بالصفحة الرئيسية
    context.update({
        "member": member_data,     # يحتوي على البيانات الأساسية (code, name, etc)
        "info": member_data,       # 💡 نمرر نفس القاموس باسم info لأن القالب يستخدمه
        "full_name": details["full_name"],
        "mother_full_name": details["mother_name"],
        "children": details["children"],
        "picture_url": details["picture_url"],
        "age_details": age_details,
        "gender": member_data.get("gender"),
        "wives": details.get("wives", []), # تأكد من وجودها في السيرفس أو أضفها
        "husbands": details.get("husbands", []),
        "current_page": page,
        "search_query": q
    })
    response = templates.TemplateResponse("family/details.html", context)
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
    
    # 🟢 الحل هنا: تعريف قاموس فارغ لكي لا يظهر خطأ Undefined في القالب
    empty_form_data = {
        "code": "", "name": "", "f_code": "", "m_code": "", "w_code": "", "h_code": "", 
        "relation": "", "level": "", "nick_name": "", "gender": "", "d_o_b": "", 
        "d_o_d": "", "email": "", "phone": "", "address": "", "p_o_b": "", "status": ""
    }

   # 2. تجهيز السياق الموحد (سيحتوي على user و can_view و unread_count)
    context = get_global_context(request)
    
    # 3. تحديث السياق بالبيانات الخاصة بالصفحة الرئيسية
    context.update({
         "csrf_token": csrf_token,
        "error": None,
        "form_data": empty_form_data
    })
    response = templates.TemplateResponse("family/add_name.html", context)
    set_cache_headers(response)
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
    

    level_int = None 

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
    # 3. المستوى (تم تحسينه)
    # ================================
    if not error and level:
        try:
            level_int = int(level)
            if level_int < 1:
                error = "المستوى يجب أن يكون رقماً موجباً."
        except ValueError:
            error = "المستوى يجب أن يكون رقماً صحيحاً."
    elif not error:
        error = "المستوى مطلوب ولا يمكن أن يكون فارغاً."

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
    if f_code_error := validate_parent_code(f_code, "الأب"):
        error = f_code_error
    elif m_code_error := validate_parent_code(m_code, "الأم"):
        error = m_code_error
    elif h_code_error := validate_parent_code(h_code, "الزوج"):
        error = h_code_error
    elif w_code_error := validate_parent_code(w_code, "الزوجة"):
        error = w_code_error

    # === 11. تحقق من تكرار الكود في قاعدة البيانات (باستخدام الخدمة) ===
    elif not error:
        # استخدام دالة الخدمة
        if FamilyService.is_code_exists(code):
            error = "هذا الكود مستخدم من قبل! اختر كودًا آخر."

    # === 12. رفع الصورة (نوع الملف فقط) ===
    ext = None
    if not error and picture and picture.filename:
        allowed = {'.jpg', '.jpeg', '.png', '.webp'}
        ext = os.path.splitext(picture.filename)[1].lower()
        if ext not in allowed:
            error = "نوع الصورة غير مدعوم! استخدم: JPG، PNG، WebP فقط"

    # ================================
    # 13. إذا كل شيء تمام → احفظ (باستخدام الخدمة)
    # ================================
    if not error:
        try:
            member_data = {
                "code": code, 
                "name": name, 
                "f_code": f_code, 
                "m_code": m_code,
                "w_code": w_code, 
                "h_code": h_code, 
                "relation": relation, 
                "level": level_int,  # 👈 تغيير من level إلى level_int لضمان إرسال رقم صحيح
                "nick_name": nick_name, 
                "d_o_b": d_o_b if d_o_b else None, # التأكد من تمرير None إذا كانت فارغة
                "d_o_d": d_o_d if d_o_d else None,
                "gender": gender, 
                "email": email, 
                "phone": phone,
                "address": address, 
                "p_o_b": p_o_b, 
                "status": status
            }
            # 💡 استدعاء الدالة من الكلاس
            # داخل دالة add_name بعد التحقق من الصورة
            ext = os.path.splitext(picture.filename)[1].lower() if picture.filename else None
            FamilyService.add_new_member(member_data, picture, ext) # أضف ext هنا
            log_action(user['id'], "إضافة فرد", f"تم إضافة {name}")

            success = f"تم حفظ {name} بنجاح!"

            # 💡 مسار النجاح: إرجاع نموذج فارغ ورسالة نجاح
            empty_form_data = {key: "" for key in ["code", "name", "f_code", "m_code", "w_code", "h_code", 
                                                "relation", "level", "nick_name", "gender", "d_o_b", 
                                                "d_o_d", "email", "phone", "address", "p_o_b", "status"]}
            
            csrf_token = generate_csrf_token()
            request.session["csrf_token"] = csrf_token
        
            return templates.TemplateResponse("family/add_name.html", {
                "request": request, "user": user, "csrf_token": csrf_token,
                "error": None, "success": success, 
                "form_data": empty_form_data 
            })
            
        except Exception as e:
            # 💡 إذا حدث خطأ في قاعدة البيانات، يتم تعيين رسالة الخطأ والاستمرار في مسار الفشل أدناه
           print(f"DATABASE ERROR: {e}") # 👈 سيظهر لك في الـ Terminal سبب المشكلة بالضبط
           error = f"حدث خطأ أثناء الحفظ: {str(e)}" # سيظهر الخطأ للمستخدم مؤقتاً للتشخيص
           
    # ----------------------------------------------------
    # 💡 مسار الفشل الموحد (Failure Path)
    # يتم تنفيذه إذا كان هناك خطأ في التحقق أو فشل في قاعدة البيانات
    # ----------------------------------------------------
    csrf_token = generate_csrf_token()
    request.session["csrf_token"] = csrf_token

    return templates.TemplateResponse("family/add_name.html", {
        "request": request, "user": user, "csrf_token": csrf_token,
        "error": error, 
        "success": None, # لضمان عدم ظهور رسالة نجاح في حال الخطأ
        "form_data": { # إعادة تعبئة النموذج بالبيانات المدخلة
            "code": code or "", "name": name or "", "f_code": f_code or "",
            "m_code": m_code or "", "w_code": w_code or "", "h_code": h_code or "",
            "relation": relation or "", "level": level or "", 
            "nick_name": nick_name or "", "gender": gender or "",
            "d_o_b": d_o_b or "", "d_o_d": d_o_d or "",
            "email": email or "", "phone": phone or "",
            "address": address or "", "p_o_b": p_o_b or "",
            "status": status or "",
        }
    })

@router.get("/get-next-code")
async def suggest_code(prefix: str): # نستخدم prefix بدلاً من letter
    if not prefix:
        return {"next_code": ""}
    
    # نرسل البادئة كاملة للدالة
    next_code = FamilyService.get_next_code(prefix)
    return {"next_code": next_code}

@router.get("/check-code-availability")
async def check_code(code: str):
    exists = FamilyService.is_code_exists(code.strip().upper())
    return {"available": not exists}

# ====================== تعديل عضو ======================
@router.get("/edit/{code}", response_class=HTMLResponse)
async def edit_name_form(request: Request, code: str):
    user = request.session.get("user")
    if not user or not can(user, "edit_member"):
        return RedirectResponse("/names")

    csrf_token = generate_csrf_token()
    request.session["csrf_token"] = csrf_token

    # 1. استدعاء دالة الخدمة لجلب البيانات
    details = FamilyService.get_member_for_edit(code)

    if not details:
        return templates.TemplateResponse("family/edit_name.html", {
            "request": request, "user": user, "code": code,
            "csrf_token": csrf_token, "error": "العضو غير موجود أو تم حذفه"
        })

    # 2. تفريغ البيانات
    member = details["member"]
    info = details["info"]
    picture_url = details["picture_url"]

     # 2. تجهيز السياق الموحد (سيحتوي على user و can_view و unread_count)
    context = get_global_context(request)
    
    # 3. تحديث السياق بالبيانات الخاصة بالصفحة الرئيسية
    context.update({
        "member": member, "info": info,
        "picture_url": picture_url, "code": code, 
        "csrf_token": csrf_token, "error": None
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
                      #d_o_b: str = Form(None), d_o_d: str = Form(None),
                      email: str = Form(None), phone: str = Form(None),
                      address: str = Form(None), p_o_b: str = Form(None),
                      status: str = Form(None), picture: UploadFile = File(None),
                      page: int = Form(1),    # 💡 استلام رقم الصفحة
                      q: str = Form("")):
    
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
    d_o_b_str = d_o_b_str.strip() if d_o_b_str else None
    d_o_d_str = d_o_d_str.strip() if d_o_d_str else None
    #d_o_b = d_o_b.strip() if d_o_b else None
    #d_o_d = d_o_d.strip() if d_o_d else None
    email = email.strip().lower() if email else None
    phone = phone.strip() if phone else None
    address = html.escape(address.strip()) if address else None
    p_o_b = html.escape(p_o_b.strip()) if p_o_b else None
    status = status.strip() if status else None
    try:
        # 💡 استخدم دالة مساعدة لتحويل السلسلة النصية إلى date
        d_o_b = date.fromisoformat(d_o_b_str) if d_o_b_str else None
        d_o_d = date.fromisoformat(d_o_d_str) if d_o_d_str else None
       
    except ValueError:
        error = "صيغة تاريخ الميلاد أو الوفاة غير صحيحة."
        d_o_b = None # لتجنب الخطأ التالي
        d_o_d = None

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
    today = date.today() # 💡 تم حذف الاستيراد المكرر هنا

    if not error and d_o_b: # 💡 d_o_b هنا هو كائن date أو None
        # لم تعد بحاجة لـ try/except أو fromisoformat، لأنها نجحت في الأعلى
        if d_o_b > today:
            error = "تاريخ الميلاد لا يمكن أن يكون في المستقبل"

    if not error and d_o_d: # 💡 d_o_d هنا هو كائن date أو None
        # لم تعد بحاجة لـ try/except أو fromisoformat
        if d_o_d > today:
            error = "تاريخ الوفاة لا يمكن أن يكون في المستقبل"
        
        # 💡 استخدم d_o_b مباشرة للمقارنة
        if d_o_b and d_o_d < d_o_b: 
            error = "تاريخ الوفاة لا يمكن أن يكون قبل تاريخ الميلاد"

    # 2.9. أكواد الأقارب
    if f_code_error := validate_parent_code(f_code, "الأب"):
        error = f_code_error
    elif m_code_error := validate_parent_code(m_code, "الأم"):
        error = m_code_error
    elif h_code_error := validate_parent_code(h_code, "الزوج"):
        error = h_code_error
    elif w_code_error := validate_parent_code(w_code, "الزوجة"):
        error = w_code_error
 
   # 2.10. صورة 
    ext = None
    if not error and picture and picture.filename:
        allowed = {'.jpg', '.jpeg', '.png', '.webp'}
        ext = os.path.splitext(picture.filename)[1].lower()
        if ext not in allowed:
            error = "نوع الصورة غير مدعوم! استخدم: JPG، PNG، WebP فقط"

   # === 3. التنفيذ أو إرجاع الخطأ (باستخدام الخدمة) ===
    if not error:
        try:
            # 💡 تجميع البيانات لإرسالها لطبقة الخدمة
            member_data = {
                "name": name, "f_code": f_code, "m_code": m_code, "w_code": w_code, 
                "h_code": h_code, "relation": relation, "level": level_int, 
                "nick_name": nick_name, "gender": gender, 
                "d_o_b": d_o_b, "d_o_d": d_o_d, 
                "email": email, "phone": phone, "address": address, 
                "p_o_b": p_o_b, "status": status
            }
            # استدعاء دالة الخدمة للتحديث
            ext = os.path.splitext(picture.filename)[1].lower() if picture.filename else None
            FamilyService.update_member_data(code, member_data, picture, ext)

            # 2. 🟢 هنا المكان الصحيح للسجل (بعد نجاح الحفظ فقط)
            log_action(
                user_id=user['id'], 
                action="تعديل فرد", 
                details=f"تم تعديل بيانات العضو {name} (الكود: {code}) بنجاح"
            )

            # 🟢 التعديل المطلوب: العودة لصفحة القائمة مع الحفاظ على الفلتر والصفحة
            redirect_url = f"/names?page={page}"
            if q and q != "None":
                import urllib.parse
                redirect_url += f"&q={urllib.parse.quote(q)}"
            
            return RedirectResponse(url=redirect_url, status_code=303)
          
        except Exception as e:
            # إذا فشلت عملية قاعدة البيانات (حالة استثناء)
            print(f"DATABASE ERROR: {e}") # 👈 سيظهر لك في الـ Terminal سبب المشكلة بالضبط
            error = f"حدث خطأ أثناء التحديث: {str(e)}" # سيظهر الخطأ للمستخدم مؤقتاً للتشخيص
        
    
    # ------------------------------------------------------------------
    # 💡 مسار الفشل (Failure Path)
    # يتم تنفيذه فقط إذا فشل التحقق الأولي أو فشل تحديث قاعدة البيانات
    # ------------------------------------------------------------------
    
    details = FamilyService.get_member_for_edit(code) # استدعاء دالة الخدمة مرة واحدة

    # 💡 يتم تعيين المتغيرات هنا لضمان أن القالب يجدها
    if details:
        member = details["member"]
        info = details["info"]
        picture_url = details["picture_url"]
        member["name"] = name
        member["level"] = level
        member["nick_name"] = nick_name
        info["phone"] = phone
        info["email"] = email
        info["address"] = address
        info["p_o_b"] = p_o_b
        info["status"] = status
    else:
        # إذا لم يتم العثور على العضو (في حالة خطأ حرج)، نستخدم بيانات النموذج الحالية قدر الإمكان
        member = {"code": code, "name": name, "level": level, "nick_name": nick_name}
        info = {"d_o_b": d_o_b, "d_o_d": d_o_d, "email": email, "phone": phone, "address": address, "p_o_b": p_o_b, "status": status}
        picture_url = None


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
async def delete_name(request: Request, code: str, csrf_token: str = Form(...)):
    user = request.session.get("user")
    
    # 1. التحقق من الصلاحيات
    if not user or not can(user, "delete_member"):
        raise HTTPException(status_code=403, detail="لا تملك الصلاحية لحذف الأعضاء")

    # 2. التحقق من CSRF
    form = await request.form()
    verify_csrf_token(request, form.get("csrf_token"))
    try:
        # 💡 الحذف عبر الكلاس
        FamilyService.delete_member(code)
        log_action(user['id'], "حذف فرد", f"الكود: {code}")
        return RedirectResponse("/names?success=member_deleted", status_code=303)
    except Exception:
        raise HTTPException(status_code=500)
  
@router.get("/export/table-backup-txt")
async def export_table_backup():
    content = FamilyService.get_family_table_backup_text()
    
    if not content:
        return Response(content="الجدول فارغ", media_type="text/plain")

    return Response(
        content=content,
        media_type="text/plain; charset=utf-8",
        headers={
            "Content-Disposition": "attachment; filename=family_name_backup.txt"
        }
    )  