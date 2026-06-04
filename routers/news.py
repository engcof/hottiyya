from fastapi import APIRouter, Request, Form, UploadFile, File, HTTPException, Query
from fastapi.responses import HTMLResponse, RedirectResponse
from services.news_service import NewsService
from services.analytics_service import AnalyticsService
from security.session import SessionService
from core.templates import templates
import os
import html 
import re   
import nh3 

router = APIRouter(prefix="/news", tags=["news"])

VALID_REGEX = r"[\u0600-\u06FFa-zA-Z\s\d\.\,\!\؟\-\(\)]+"

def sanitize_html_content(content: str) -> str:
    """
    تطهير صارم ومحترف للنصوص الغنية باستخدام مكتبة nh3 لمنع الـ XSS نهائياً.
    تسمح فقط بوسوم التنسيق الأساسية الآمنة وتجرد أي سمات خطيرة (مثل onclick أو javascript:).
    """
    # تحديد الوسوم المسموح بها لتنسيق المقال داخل المحرر
    allowed_tags = {
        'h2', 'h3', 'p', 'b', 'i', 'strong', 'em', 
        'ul', 'ol', 'li', 'span', 'br', 'div'
    }
    
    # تنظيف النص الغني عبر المكتبة مباشرة
    return nh3.clean(
        content,
        tags=allowed_tags,
        link_rel="noopener noreferrer" # ميزة أمنية إضافية للروابط الخارجية إن وجدت
    )

# === عرض الأخبار (القائمة) ===
@router.get("/", response_class=HTMLResponse)
async def list_news(request: Request, page: int = Query(1, ge=1), q: str = Query(None)):
    cxt = SessionService.get_page_context(request, additional_perms=["view_tree", "add_news", "delete_news", "edit_news"])
    
    limit = 10
    news, total = NewsService.get_all_news(page=page, limit=limit, q=q)
    total_pages = (total + limit - 1) // limit

    context = {**cxt}
    context.update({
        "news": news,         
        "current_page": page,
        "total_pages": total_pages,
        "q": q or ""
    })
    
    response = templates.TemplateResponse("news/list.html", context)
    SessionService.set_cache_headers(response)
    return response

# === عرض تفاصيل الخبر ===
@router.get("/{id:int}", response_class=HTMLResponse)
async def view_news(request: Request, id: int):
    cxt = SessionService.get_page_context(request, additional_perms=["view_tree", "add_news", "delete_news", "edit_news"])
    
    item = NewsService.get_news_by_id(id)
    if not item:
        raise HTTPException(404, "الخبر غير موجود")
            
    context = {**cxt}
    context.update({"item": item})
    
    response = templates.TemplateResponse("news/detail.html", context)
    SessionService.set_cache_headers(response)
    return response

# === إضافة خبر ===
@router.get("/add", response_class=HTMLResponse)
async def add_news_form(request: Request):
    cxt = SessionService.get_page_context(request, additional_perms=["add_news"])
    user = cxt["user"]
    if not user:
        return RedirectResponse(url="/auth/login/?error=unauthorized", status_code=303)

    if not cxt.get("perms", {}).get("add_news", False):
        return RedirectResponse(url="/news?error=unauthorized", status_code=303)
    
    context = {**cxt}
    context.update({"form_data": {}})
    
    response = templates.TemplateResponse("news/add.html", context)
    SessionService.set_cache_headers(response)
    return response

@router.post("/add")
async def add_news(
    request: Request,
    title: str = Form(...),
    content: str = Form(...),
    image: UploadFile = File(None)
):
    cxt = SessionService.get_page_context(request, additional_perms=["add_news"])
    user = cxt["user"]
    if not user:
        return RedirectResponse(url="/auth/login/?error=unauthorized", status_code=303)

    if not cxt.get("perms", {}).get("add_news", False):
        raise HTTPException(status_code=403, detail="لا تملك صلاحية الإضافة")
    
    form = await request.form()
    SessionService.verify_csrf_token(request, form.get("csrf_token"))

    title_stripped = title.strip()
    content_stripped = content.strip()
    # 🛡️ الحماية من التزوير: الكاتب يؤخذ إجبارياً من الجلسة الموثقة وليس من مدخلات الفورم المخترقة
    author_verified = user["username"]
    
    error = None
    
    if not title_stripped:
        error = "عنوان الخبر مطلوب."
    elif not re.fullmatch(VALID_REGEX, title_stripped):
        error = "العنوان يحتوي على رموز غير مسموح بها."
        
    # تطهير المحتوى آمنًا وحمايته من الـ XSS
    sanitized_content = sanitize_html_content(content_stripped)
    
    # فحص الفراغ الحقيقي للمحتوى المقصوص لتفادي تلاعب المحرر بالنصوص الفارغة
    clean_text_check = re.sub(r'<[^>]*>', '', sanitized_content).strip()
    if not clean_text_check or clean_text_check == "اكتب تفاصيل الخبر هنا...":
        error = "محتوى الخبر فارغ أو غير صالح."

    if error:
        context = {**cxt}
        context.update({
            "error": error,
            "form_data": {
                "title": html.escape(title_stripped), 
                "content": content_stripped
            }
        })
        response = templates.TemplateResponse("news/add.html", context)
        SessionService.set_cache_headers(response)
        return response
      
    try:
        news_id = NewsService.create_news(
            title=title_stripped,
            content=sanitized_content,
            author=author_verified,
            media_file=image.file if image and image.filename else None
        )

        AnalyticsService.log_action(
            user_id=user["id"],
            action="إضافة خبر",
            details=f"قام {user['username']} بنشر خبر جديد بعنوان: {title_stripped[:50]}..."
        )

        return RedirectResponse(f"/news/{news_id}", status_code=303)
    except Exception as e:
        print(f"❌ Error: {e}")
        raise HTTPException(500, "حدث خطأ أثناء حفظ الخبر")
    
# === تعديل الخبر ===
@router.get("/edit/{id:int}", response_class=HTMLResponse)
async def edit_news_form(request: Request, id: int):
    cxt = SessionService.get_page_context(request, additional_perms=["edit_news"])
    user = cxt["user"]
    if not user:
        return RedirectResponse(url="/auth/login/?error=unauthorized", status_code=303)
        
    if not cxt.get("perms", {}).get("edit_news", False):
        return RedirectResponse(url="/news?error=unauthorized", status_code=303)
    
    item = NewsService.get_news_by_id(id)
    if not item:
        raise HTTPException(404, "الخبر غير موجود أثناء التعديل.")
    
    context = {**cxt}
    context.update({"item": item})
    response = templates.TemplateResponse("news/edit.html", context)
    SessionService.set_cache_headers(response)
    return response

@router.post("/edit/{id:int}")
async def update_news(
    request: Request,
    id: int,
    title: str = Form(...),
    content: str = Form(...),
    author: str = Form(...), # مسموح للإدارة تعديل اسم الكاتب الأصلي إن لزم الأمر
    image: UploadFile = File(None),
    page: int = Form(1)
):
    cxt = SessionService.get_page_context(request, additional_perms=["edit_news"])
    user = cxt["user"]
    if not user:
        return RedirectResponse(url="/auth/login/?error=unauthorized", status_code=303)
    
    if not cxt.get("perms", {}).get("edit_news", False):
        raise HTTPException(status_code=403, detail="لا تملك صلاحية التعديل")

    form = await request.form()
    SessionService.verify_csrf_token(request, form.get("csrf_token"))

    title_stripped = title.strip()
    content_stripped = content.strip()
    author_stripped = author.strip()
    
    error = None

    if not title_stripped:
        error = "عنوان الخبر مطلوب."
    elif not re.fullmatch(VALID_REGEX, title_stripped):
        error = "العنوان يحتوي على رموز غير مسموح بها."
    elif not author_stripped:
        error = "اسم الكاتب مطلوب."
    elif not re.fullmatch(VALID_REGEX, author_stripped):
        error = "اسم الكاتب يحتوي على رموز غير مسموح بها."

    sanitized_content = sanitize_html_content(content_stripped)
    clean_text_check = re.sub(r'<[^>]*>', '', sanitized_content).strip()
    if not clean_text_check:
        error = "محتوى الخبر لا يمكن أن يكون فارغاً."

    if error:
        item = NewsService.get_news_by_id(id)
        if not item:
            raise HTTPException(404, "الخبر غير موجود أثناء التعديل.")
        
        item['title'] = title_stripped
        item['content'] = content_stripped
        item['author'] = author_stripped
        
        context = {**cxt}
        context.update({"item": item, "error": error})
        response = templates.TemplateResponse("news/edit.html", context)
        SessionService.set_cache_headers(response)
        return response

    try:
        success = NewsService.update_news(
            news_id=id,
            title=title_stripped,
            content=sanitized_content,
            author=author_stripped,
            media_file=image.file if image and image.filename else None
        )
        
        if success:
            AnalyticsService.log_action(
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
    cxt = SessionService.get_page_context(request, additional_perms=["delete_news"])
    user = cxt["user"]
    if not user:
        return RedirectResponse(url="/auth/login/?error=unauthorized", status_code=303)
    
    if not cxt.get("perms", {}).get("delete_news", False):
        raise HTTPException(status_code=403, detail="لا تملك صلاحية الحذف")

    form = await request.form()
    SessionService.verify_csrf_token(request, form.get("csrf_token"))

    try:
        if NewsService.delete_news(id):
            AnalyticsService.log_action(
                user_id=user["id"],
                action="حذف خبر",
                details=f"قام {user['username']} بحذف الخبر رقم ({id}) نهائياً."
            )
            return RedirectResponse("/news", status_code=303)
        raise HTTPException(404, "الخبر غير موجود")
    except Exception as e:
        print(f"❌ Error during deletion: {e}")
        raise HTTPException(500, "حدث خطأ أثناء محاولة حذف الخبر")