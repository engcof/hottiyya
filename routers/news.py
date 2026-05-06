from fastapi import APIRouter, Request, Form, UploadFile, File, HTTPException,Query
from fastapi.responses import HTMLResponse, RedirectResponse

from services.news_service import NewsService
from services.analytics import log_action
from security.csrf import verify_csrf_token
from security.session import set_cache_headers,get_page_context
from core.templates import templates

import os
import html 
import re   

router = APIRouter(prefix="/news", tags=["news"])

UPLOAD_DIR = "static/uploads/news"
os.makedirs(UPLOAD_DIR, exist_ok=True)

# التعبير النمطي الجديد يدعم العربية والإنجليزية والأرقام وعلامات الترقيم الشائعة
VALID_REGEX = r"[\u0600-\u06FFa-zA-Z\s\d\.\,\!\؟\-\(\)]+"
    
# Regex شامل يسمح بجميع رموز HTML وعلامات الترقيم والتشكيل العربي
VALID_CONTENT_REGEX = r"[\s\S]*"

# الحل الأفضل هو التأكد فقط من وجود محتوى وعدم وجود وسوم خبيثة (مثل <script>)
def is_safe_html(content):
    forbidden_tags = ["<script", "javascript:", "onclick", "<iframe", "<object"]
    return not any(tag in content.lower() for tag in forbidden_tags)

# === عرض الأخبار (القائمة) ===
@router.get("/", response_class=HTMLResponse)
async def list_news(request: Request, page: int = Query(1, ge=1), q: str = Query(None)):
    cxt = get_page_context(request,additional_perms=["view_tree", "add_news", "delete_news", "edit_news"])
    
    # 1. جلب البيانات من السيرفس
    limit = 10
    news, total = NewsService.get_all_news(page=page, limit=limit, q=q)
    total_pages = (total + limit - 1) // limit

    # 2. تجهيز السياق الموحد
    context = {**cxt}  # نبدأ بنسخة من السياق الأساسي الذي يحتوي على بيانات المستخدم والصلاحيات العامة
    
    # 3. تحديث السياق بالبيانات الخاصة بهذه الصفحة
    context.update({
        "news": news,         
        "current_page": page,
        "total_pages": total_pages,
        "q": q
    })
    
    # 4. إرسال القالب (لاحظ تمرير context فقط)
    response = templates.TemplateResponse("news/list.html", context)
    set_cache_headers(response)
    return response

# === عرض تفاصيل الخبر ===
@router.get("/{id:int}", response_class=HTMLResponse)
async def view_news(request: Request, id: int):
    cxt = get_page_context(request,additional_perms=["view_tree", "add_news", "delete_news", "edit_news"])
    
    # جلب الخبر من السيرفس
    item = NewsService.get_news_by_id(id)
    if not item:
        raise HTTPException(404, "الخبر غير موجود")
            
    # 2. تجهيز السياق الموحد (سيحتوي على user و can_view و unread_count)
    context =   {**cxt}
    
    # 3. تحديث السياق بالبيانات الخاصة بالصفحة الرئيسية
    context.update({
       "item": item,
    })
    response = templates.TemplateResponse("news/detail.html", context)
    set_cache_headers(response)
    return response

# === إضافة خبر ===
@router.get("/add", response_class=HTMLResponse)
async def add_news_form(request: Request):
    cxt = get_page_context(request,additional_perms=["view_tree", "add_news"])
    user = cxt["user"]
    if not user:
        return RedirectResponse(url="/auth/login/?error=unauthorized", status_code=303)

    # التحقق من الصلاحية
    added = cxt.get("perms", {}).get("add_news", False)
    if not added:
        return RedirectResponse(url=f"/news?error=unauthorized", status_code=303)
    
    context =   {**cxt}
    
    # 3. تحديث السياق بالبيانات الخاصة بالصفحة الرئيسية
    context.update({
          "form_data": {} # إضافة form_data فارغة
    })
    response = templates.TemplateResponse("news/add.html", context)
    set_cache_headers(response)
    return response

@router.post("/add")
async def add_news(
    request: Request,
    title: str = Form(...),
    content: str = Form(...),
    author: str = Form(...),
    image: UploadFile = File(None) # هذا الحقل سيستقبل الصورة أو الفيديو
):
    cxt = get_page_context(request,additional_perms=[ "add_news"])
    user = cxt["user"]
    if not user :
        return RedirectResponse(url="/auth/login/?error=unauthorized", status_code=303)

    added = cxt.get("perms", {}).get("add_news", False)
    if not added:
        raise HTTPException(status_code=403, detail="لا تملك صلاحية الإضافة")
    
    form = await request.form()
    verify_csrf_token(request, form.get("csrf_token"))

    # التنظيف والتحقق
    title_stripped = title.strip()
    content_stripped = content.strip()
    author_stripped = author.strip()
    
    error = None
    
    # 1. التحقق من الأخطاء (التصحيح)
    if not title_stripped:
        error ="عنوان الخبر مطلوب."
    elif not re.fullmatch(VALID_REGEX, title_stripped):
        error = "العنوان يحتوي على رموز غير مسموح بها."
    # التحقق من الأمان عبر الدالة التي كتبناها
    elif not is_safe_html(content_stripped):
        error = "المحتوى يحتوي على وسوم غير مسموح بها."
     # فحص الـ Regex للمحتوى (تأكد أنه يشمل رموز HTML كما في ردنا السابق)
    elif not re.fullmatch(VALID_CONTENT_REGEX, content_stripped):
        error = "المحتوى يحتوي على رموز غير مسموح بها."
    elif not author_stripped:
        error = "اسم الكاتب مطلوب."
    # التحقق من نظافة الكاتب
    elif not re.fullmatch(VALID_REGEX, author_stripped):
        error = "اسم الكاتب يحتوي على رموز غير مسموح بها."

    # في حال وجود خطأ، نعيد المستخدم إلى نموذج الإضافة مع رسالة الخطأ وبياناته
    if error:
        context =   {**cxt}
    
        # 3. تحديث السياق بالبيانات الخاصة بالصفحة الرئيسية
        context.update({
            "error": error,
            "form_data": {
                "title": html.escape(title), 
                "content": content, # المحتوى نتركه كما هو لأننا نستخدم دالة safe_html
                "author": html.escape(author)
            }
        })
        response = templates.TemplateResponse("news/add.html", context)
        set_cache_headers(response)
        return response
      
    try:
        # استخدام السيرفس للحفظ والرفع للسحابة
        news_id = NewsService.create_news(
            title=title_stripped,
            content=content_stripped,
            author=author_stripped,
            media_file=image.file if image and image.filename else None
        )

        # تسجيل النشاط في السجل الشامل
        log_action(
            user_id=user["id"],
            action="إضافة خبر",
            details=f"قام {user['username']} بنشر خبر جديد بعنوان: {title[:50]}..."
        )

        return RedirectResponse(f"/news/{news_id}", status_code=303)
    except Exception as e:
        print(f"❌ Error: {e}")
        raise HTTPException(500, "حدث خطأ أثناء حفظ الخبر")
    
# === تعديل الخبر ===
@router.get("/edit/{id:int}", response_class=HTMLResponse)
async def edit_news_form(request: Request, id: int):
    cxt = get_page_context(request,additional_perms=["edit_news"])
    user = cxt["user"]
    if not user :
        return RedirectResponse(url="/auth/login/?error=unauthorized", status_code=303)
    # التحقق من الصلاحية
    edited = cxt.get("perms", {}).get("edit_news", False)
    if not edited:
        return RedirectResponse(url=f"/news?error=unauthorized", status_code=303)
    
    # استخدام السيرفس بدلاً من الاستعلام المباشر
    item = NewsService.get_news_by_id(id)
    
    if not item:
        raise HTTPException(404, "الخبر غير موجود أثناء التعديل.")
    
    context =   {**cxt}
    
    # 3. تحديث السياق بالبيانات الخاصة بالصفحة الرئيسية
    context.update({
          "item": item,
    })
    response = templates.TemplateResponse("news/edit.html", context)
    set_cache_headers(response)
    return response

@router.post("/edit/{id:int}")
async def update_news(
    request: Request,
    id: int,
    title: str = Form(...),
    content: str = Form(...),
    author: str = Form(...),
    image: UploadFile = File(None),
    page: int = Form(1)
):
    cxt = get_page_context(request,additional_perms=[ "edit_news"])
    user = cxt["user"]
    if not user :
        return RedirectResponse(url="/auth/login/?error=unauthorized", status_code=303)
    
    # 🛡️ خط الدفاع الأخير: إذا حاول شخص تجاوز الـ GET وإرسال الطلب مباشرة
    is_allowed = cxt.get("perms", {}).get("edit_news", False)
    if not is_allowed:
        raise HTTPException(status_code=403, detail="لا تملك صلاحية التعديل")

    # تحقق من CSRF
    form = await request.form()
    verify_csrf_token(request, form.get("csrf_token"))

    # التنظيف والتحقق
    title_stripped = title.strip()
    content_stripped = content.strip()
    author_stripped = author.strip()
    
    error = None

   # 1. التحقق من الأخطاء (التصحيح)
    if not title_stripped:
        error ="عنوان الخبر مطلوب."
    elif not re.fullmatch(VALID_REGEX, title_stripped):
        error = "العنوان يحتوي على رموز غير مسموح بها."
    # التحقق من الأمان عبر الدالة التي كتبناها
    elif not is_safe_html(content_stripped):
        error = "المحتوى يحتوي على وسوم غير مسموح بها (مثل script أو iframe)."
    # فحص الـ Regex للمحتوى (تأكد أنه يشمل رموز HTML كما في ردنا السابق)
    elif not re.fullmatch(VALID_CONTENT_REGEX, content_stripped):
        error = "المحتوى يحتوي على رموز غير مسموح بها."
    elif not author_stripped:
        error = "اسم الكاتب مطلوب."
    # التحقق من نظافة الكاتب
    elif not re.fullmatch(VALID_REGEX, author_stripped):
        error = "اسم الكاتب يحتوي على رموز غير مسموح بها."

    # في حال وجود خطأ، نعيد المستخدم إلى نموذج التعديل مع رسالة الخطأ وبياناته
    if error:
            
      # استخدام السيرفس بدلاً من الاستعلام المباشر
        item = NewsService.get_news_by_id(id)
        
        if not item:
            raise HTTPException(404, "الخبر غير موجود أثناء التعديل.")
        
        # تحديث الحقول بقيم الـ Form الجديدة لعرضها للمستخدم
        item['title'] = title
        item['content'] = content
        item['author'] = author
        context =   {**cxt}
    
        # 3. تحديث السياق بالبيانات الخاصة بالصفحة الرئيسية
        context.update({
             "item": item,
            "error": error
        })
        response = templates.TemplateResponse("news/edit.html", context)
        set_cache_headers(response)
        return response

    try:
        # استخدام السيرفس المحدث
        success = NewsService.update_news(
            news_id=id,
            title=html.escape(title.strip()),
            content=content_stripped,
            author=html.escape(author.strip()),
            media_file=image.file if image and image.filename else None
        )
        
        if success:
            # تسجيل النشاط في السجل الشامل
            log_action(
                user_id=user["id"],
                action="تعديل خبر",
                details=f"قام {user['username']} بتعديل الخبر رقم ({id}) بعنوان: {title_stripped[:30]}..."
            ) 
            return RedirectResponse(f"/news?page={page}", status_code=303)
        raise HTTPException(404, "الخبر غير موجود")
    except Exception as e:
        print(f"❌ Error during update: {e}")
        raise HTTPException(500, "حدث خطأ داخلي أثناء التحديث")

@router.post("/delete/{id:int}")
async def delete_news(request: Request, id: int):
    cxt = get_page_context(request,additional_perms=["delete_news"])
    user = cxt["user"]
    if not user :
        return RedirectResponse(url="/auth/login/?error=unauthorized", status_code=303)
    
    # 🛡️ خط الدفاع الأخير: إذا حاول شخص تجاوز الـ GET وإرسال الطلب مباشرة
    is_allowed = cxt.get("perms", {}).get("delete_news", False)
    if not is_allowed:
        raise HTTPException(status_code=403, detail="لا تملك صلاحية الحذف")

    # التحقق من CSRF
    form = await request.form()
    verify_csrf_token(request, form.get("csrf_token"))

    try:
        # تنفيذ الحذف عبر السيرفس
        success = NewsService.delete_news(id)
        
        if success:
            # تسجيل العملية في السجل الشامل
            log_action(
                user_id=user["id"],
                action="حذف خبر",
                details=f"قام {user['username']} بحذف الخبر رقم ({id}) نهائياً مع ملفاته."
            )
            return RedirectResponse("/news", status_code=303)
           
        else:
            raise HTTPException(404, "الخبر غير موجود")
            
    except Exception as e:
        print(f"❌ Error during deletion: {e}")
        raise HTTPException(500, "حدث خطأ أثناء محاولة حذف الخبر")