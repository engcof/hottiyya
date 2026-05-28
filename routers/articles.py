from fastapi import APIRouter, Request, Form, UploadFile, File, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse

from security.session import SessionService
from services.analytics_service import AnalyticsService
from services.article_service import ArticleService
import os
from core.templates import templates
import html 
import re # تم إضافة استيراد المكتبة للتحقق من الصيغة

router = APIRouter(prefix="/articles", tags=["articles"])

# التعبير النمطي الجديد يدعم العربية والإنجليزية والأرقام وعلامات الترقيم الشائعة
VALID_TITLE_REGEX = r"[\u0600-\u06FFa-zA-Z\s\d\.\,\!\؟\-\(\)]+"
    
# Regex شامل يسمح بجميع رموز HTML وعلامات الترقيم والتشكيل العربي
VALID_CONTENT_REGEX = r"[\s\S]*"

# الحل الأفضل هو التأكد فقط من وجود محتوى وعدم وجود وسوم خبيثة (مثل <script>)
def is_safe_html(content):
    forbidden_tags = ["<script", "javascript:", "onclick", "<iframe", "<object"]
    return not any(tag in content.lower() for tag in forbidden_tags)

# === عرض قائمة المقالات (باستخدام الخدمة) ===
@router.get("/", response_class=HTMLResponse)
async def list_articles(request: Request, page: int = 1):
    cxt = SessionService.get_page_context(request,additional_perms=["view_tree", "add_article", "delete_article"])
    
    # استدعاء الخدمة لجلب البيانات والترقيم
    articles, total_pages = ArticleService.get_all_articles(page=page, per_page=12)
     # 2. تجهيز السياق الموحد
    context =  {**cxt}
    
    # 3. تحديث السياق بالبيانات الخاصة بهذه الصفحة
    context.update({
       "articles": articles,
        "page": page,
        "total_pages": total_pages,
        "has_prev": page > 1,
        "has_next": page < total_pages
    })
    response = templates.TemplateResponse("articles/list.html", context)
    SessionService.set_cache_headers(response)
    return response
    
# === 🌟 التوجيه إلى أحدث مقال (مسار ثابت) 🌟 ===
@router.get("/latest")
async def latest_article_redirect():
    latest_id = ArticleService.get_latest_article_id()
    
    if not latest_id:
        # إذا لم يكن هناك مقالات، وجههم إلى صفحة قائمة المقالات
        return RedirectResponse("/articles", status_code=303)
    
    # التوجيه إلى رابط المقال المكتشف
    return RedirectResponse(f"/articles/view/{latest_id}", status_code=303)
                
# === عرض مقال + التعليقات ===
@router.get("/{id:int}", response_class=HTMLResponse)
async def view_article(request: Request, id: int):
    cxt = SessionService.get_page_context(request,additional_perms=["view_tree", "edit_article", "delete_article", "add_comment", "delete_comment"])
    
    article, comments = ArticleService.get_article_details(id)
    
    if not article: raise HTTPException(404, "المقال غير موجود")

   # 2. تجهيز السياق الموحد (سيحتوي على user و can_view و unread_count)
    context =   {**cxt}
    
    # 3. تحديث السياق بالبيانات الخاصة بالصفحة الرئيسية
    context.update({
       "article": article, "comments": comments,
    })
    response = templates.TemplateResponse("articles/detail.html", context)
    SessionService.set_cache_headers(response)
    return response

# === إضافة مقال ===
@router.get("/add", response_class=HTMLResponse)
async def add_article_form(request: Request):
    cxt = SessionService.get_page_context(request,additional_perms=["view_tree", "add_article"])
    user = cxt["user"]
    if not user:
        return RedirectResponse(url="/auth/login/?error=unauthorized", status_code=303)
    # التحقق من الصلاحية
    added = cxt.get("perms", {}).get("add_article", False)
    if not added:
        return RedirectResponse(url="/articles/?error=unauthorized", status_code=303)
  
    
    # 2. تجهيز السياق الموحد (سيحتوي على user و can_view و unread_count)
    context =   {**cxt}
    
    # 3. تحديث السياق بالبيانات الخاصة بالصفحة الرئيسية
    context.update({
       "form_data": {}
    })
    response = templates.TemplateResponse("articles/add.html", context)
    SessionService.set_cache_headers(response)
    return response

@router.post("/add")
async def add_article(request: Request, title: str = Form(...),content: str = Form(...), image: UploadFile = File(None)):
    cxt = SessionService.get_page_context(request,additional_perms=["add_article"])
    user = cxt["user"]
    edited = cxt.get("perms", {}).get("add_article", False)
    if not edited:
        raise HTTPException(status_code=403, detail="لا تملك صلاحية النشر")
    # التحقق من CSRF والنظافة (كما في كودك)
    form = await request.form()
    SessionService.verify_csrf_token(request, form.get("csrf_token"))
    
    error = None

    # 1. التحقق من عدم فراغ العنوان والمحتوى
    title_stripped = title.strip()
    content_stripped = content.strip() # لا تستخدم html.escape هنا للمحتوى!
   
    # 1. التحقق من الأخطاء (التصحيح)
    if not title_stripped:
        error = "عنوان المقال مطلوب."
    elif not re.fullmatch(VALID_TITLE_REGEX, title_stripped):
        error = "العنوان يحتوي على رموز غير مسموح بها."
    elif not content_stripped or len(content_stripped) < 10:
        error = "محتوى المقال قصير جداً أو فارغ."
    # التحقق من الأمان عبر الدالة التي كتبناها
    elif not is_safe_html(content_stripped):
        error = "المحتوى يحتوي على وسوم غير مسموح بها (مثل script أو iframe)."
    # فحص الـ Regex للمحتوى (تأكد أنه يشمل رموز HTML كما في ردنا السابق)
    elif not re.fullmatch(VALID_CONTENT_REGEX, content_stripped):
        error = "المحتوى يحتوي على رموز غير مسموح بها."

    image_url = None
    if image and image.filename:
        # إذا كان هناك خطأ، لن يتم الرفع على أي حال، لكن نستمر في الفحص
        pass
        
    if error:
        print(f"⚠️ Validation Error: {error}") # أضف هذا السطر للتشخيص
        context =   {**cxt}
    
        # 3. تحديث السياق بالبيانات الخاصة بالصفحة الرئيسية
        context.update({
            "error": error,
            "form_data": {"title": title, "content": content} 
        })
        response = templates.TemplateResponse("articles/add.html", context)
        SessionService.set_cache_headers(response)
        return response
    try:
        # في حالة أردت التأكد من إغلاق الملف يدوياً (اختياري لأن FastAPI يقوم بذلك أحياناً)
     
        article_id = ArticleService.create_article(
            title=html.escape(title_stripped), # العنوان فقط نقوم بعمل escape له لأنه نص عادي
            content=content_stripped,          # المحتوى يبقى HTML ليظهر التنسيق
            author_id=user["id"],
            image_file=image.file if image and image.filename else None
        )
      
        if image:
            await image.close() # إغلاق الملف بعد الانتهاء

        # 2. ✅ إضافة العملية لسجل النشاطات
        AnalyticsService.log_action(
            user_id=user["id"], 
            action="إضافة مقال", 
            details=f"تم نشر مقال جديد بعنوان: {title}"
        )    
        return RedirectResponse(f"/articles/{article_id}", status_code=303)
        
    except Exception as e:
        print(f"❌ Error: {e}")
        raise HTTPException(500, "حدث خطأ أثناء حفظ المقال")    
  
# === تعديل مقال ===
@router.get("/edit/{id:int}", response_class=HTMLResponse)
async def edit_article_form(request: Request, id: int):
    cxt = SessionService.get_page_context(request,additional_perms=["view_tree", "edit_article"])
    if not cxt:
        return RedirectResponse(url="/articles/?error=unauthorized", status_code=303)

    # التحقق من الصلاحية
    edited = cxt.get("perms", {}).get("edit_article", False)
    if not edited:
        return RedirectResponse(url="/articles/?error=unauthorized", status_code=303)

    articl= ArticleService.get_article_by_id(id)
    
    if not articl:
        raise HTTPException(404, "المقال غير موجود أثناء التعديل.")
               
    context =   {**cxt}
    
    # 3. تحديث السياق بالبيانات الخاصة بالصفحة الرئيسية
    context.update({
        "article": articl,      
    })
    response = templates.TemplateResponse("articles/edit.html", context)
    SessionService.set_cache_headers(response)
    return response
    
  
# === حفظ التعديلات ===
@router.post("/edit/{id:int}")
async def update_article(
    request: Request, 
    id: int, 
    title: str = Form(...), 
    content: str = Form(...), 
    image: UploadFile = File(None)
):
    cxt = SessionService.get_page_context(request,additional_perms=[ "edit_article"])
    user = cxt["user"]
    # 🛡️ خط الدفاع الأخير: إذا حاول شخص تجاوز الـ GET وإرسال الطلب مباشرة
    is_allowed = cxt.get("perms", {}).get("edit_article", False)
    if not is_allowed:
        raise HTTPException(status_code=403, detail="لا تملك صلاحية التعديل")

    form = await request.form()
    SessionService.verify_csrf_token(request, form.get("csrf_token"))

    error = None

    # 1. التحقق من عدم فراغ العنوان والمحتوى
    title_stripped = title.strip()
    content_stripped = content.strip() # لا تستخدم html.escape هنا للمحتوى!

    # 1. التحقق من الأخطاء (التصحيح)
    if not title_stripped:
        error = "عنوان المقال مطلوب."
    elif not re.fullmatch(VALID_TITLE_REGEX, title_stripped):
        error = "العنوان يحتوي على رموز غير مسموح بها."
    elif not content_stripped or len(content_stripped) < 10:
        error = "محتوى المقال قصير جداً أو فارغ."
    # التحقق من الأمان عبر الدالة التي كتبناها
    elif not is_safe_html(content_stripped):
        error = "المحتوى يحتوي على وسوم غير مسموح بها (مثل script أو iframe)."
    # فحص الـ Regex للمحتوى (تأكد أنه يشمل رموز HTML كما في ردنا السابق)
    elif not re.fullmatch(VALID_CONTENT_REGEX, content_stripped):
        error = "المحتوى يحتوي على رموز غير مسموح بها."


    # في حالة وجود خطأ، يجب إعادة تحميل النموذج مع البيانات المدخلة
    if error:
        
        # استخدام السيرفس بدلاً من الاستعلام المباشر
        articl= ArticleService.get_article_by_id(id)
        
        if not articl:
            raise HTTPException(404, "المقال غير موجود أثناء التعديل.")
     
        
        # استبدال العنوان والمحتوى بالمدخلات الجديدة لعرض الخطأ
        articl['title'] = title
        articl['content'] = content
        context =   {**cxt}
    
        # 3. تحديث السياق بالبيانات الخاصة بالصفحة الرئيسية
        context.update({
            "article": articl,
           "error": error
        })
        response = templates.TemplateResponse("articles/edit.html", context)
        SessionService.set_cache_headers(response)
        return response
       
    # استكمال عملية حفظ التعديلات
    await ArticleService.update_article(
        article_id=id, 
        title=html.escape(title_stripped),
        content=content_stripped , 
        image_file=image if image and image.filename else None
    )
    # 🌟 إضافة سجل النشاطات (Analytics) 
    AnalyticsService.log_action(
        user_id=user["id"], 
        action="تعديل مقال", 
        details=f"قام {user['username']} بتعديل المقال رقم ({id}) بعنوان: {title[:50]}..."
    )
    return RedirectResponse(f"/articles/{id}", status_code=303)

# === حذف مقال ===
@router.post("/delete/{id:int}")
async def delete_article(request: Request, id: int):
    cxt = SessionService.get_page_context(request,additional_perms=["view_tree", "delete_article"])
    user = cxt["user"]
    perms = cxt.get("perms", {})
    deleted = perms.get("delete_article", False)
    if not deleted :
        raise HTTPException(status_code=403, detail="لا تملك الصلاحية لحذف المقال.")

    form = await request.form()
    SessionService.verify_csrf_token(request, form.get("csrf_token"))

    # جلب عنوان المقال قبل الحذف لاستخدامه في سجل النشاطات
    article_data = ArticleService.get_article_details(id)
    title = article_data[0]['title'] if article_data[0] else "مقال غير معروف"

    # تنفيذ عملية الحذف الشاملة
    ArticleService.delete_article(id)

    # 🌟 تسجيل عملية الحذف في السجل
    AnalyticsService.log_action(
        user_id=user["id"], 
        action="حذف مقال", 
        details=f"قام {user['username']} بحذف المقال رقم ({id}) بعنوان: {title} مع كافة ملحقاته"
    )

    return RedirectResponse("/articles", status_code=303)    

# === إضافة تعليق ===
@router.post("/{id:int}/comment")
async def add_comment(request: Request, id: int, content: str = Form(...)):
    cxt = SessionService.get_page_context(request,additional_perms=["view_tree", "add_comment"])
    if not cxt:
        return RedirectResponse(url="/auth/login/?error=unauthorized", status_code=303)

    # التحقق من الصلاحية
    added = cxt.get("perms", {}).get("add_comment", False)
    if not added:
        return RedirectResponse(url=f"/articles/{id}?error=unauthorized", status_code=303)
    user = cxt["user"]
   

    form = await request.form()
    SessionService.verify_csrf_token(request, form.get("csrf_token"))

    content_safe = html.escape(content.strip())
    
    # تنفيذ الإضافة عبر السيرفس
    ArticleService.add_comment(id, user["id"], content_safe)

    # 🌟 تسجيل النشاط
    AnalyticsService.log_action(
        user_id=user["id"],
        action="إضافة تعليق",
        details=f"قام {user['username']} بالتعليق على المقال رقم ({id})"
    )

    return RedirectResponse(f"/articles/{id}#comments", status_code=303)

# === حذف تعليق ===
@router.post("/{article_id:int}/comment/{comment_id:int}/delete")
async def delete_comment(request: Request, article_id: int, comment_id: int):
    cxt = SessionService.get_page_context(request,additional_perms=["view_tree", "delete_comment"])
    user = cxt["user"]
    perms = cxt.get("perms", {})
    deleted = perms.get("delete_comment", False)
    if not deleted :
        raise HTTPException(status_code=403, detail="لا تملك الصلاحية لحذف التعليق.")


    SessionService.verify_csrf_token(request, (await request.form()).get("csrf_token"))

    # جلب بيانات التعليق للتحقق والتسجيل
    comment = ArticleService.get_comment_owner(comment_id)
    if not comment: raise HTTPException(404, "التعليق غير موجود")
    
        
    allowed = (
        user.get("id") == comment["user_id"] or 
        SessionService.can(user, "delete_comment") # دالة can ستغطي الأدمن وصاحب الصلاحية
    )
    if not allowed: raise HTTPException(403, "غير مسموح لك بالحذف")

    # تنفيذ الحذف عبر السيرفس
    ArticleService.delete_comment(comment_id)

    # 🌟 تسجيل النشاط
    AnalyticsService.log_action(
        user_id=user["id"],
        action="حذف تعليق",
        details=f"قام {user['username']} بحذف تعليق في المقال ({article_id}). نص التعليق: {comment['content'][:30]}..."
    )

    return RedirectResponse(f"/articles/{article_id}#comments", status_code=303)

