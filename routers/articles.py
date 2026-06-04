from fastapi import APIRouter, Request, Form, UploadFile, File, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
import os
import re
import html 
import nh3  # 🛡️ المكتبة الأقوى لتطهير الـ HTML وحماية XSS
from security.session import SessionService
from services.analytics_service import AnalyticsService
from services.article_service import ArticleService
from core.templates import templates

router = APIRouter(prefix="/articles", tags=["articles"])

VALID_TITLE_REGEX = r"^[\u0600-\u06FFa-zA-Z0-9\s\.\,\!\؟\-\(\)\[\]\{\}]+$"
ALLOWED_IMAGE_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.webp', '.gif'}
MAX_IMAGE_SIZE_BYTES = 5 * 1024 * 1024  # 5 ميجابايت كحد أقصى للغلاف

# 🛡️ إعداد الوسوم والسمات المسموح بها داخل المقال الإخباري والمحرر
ALLOWED_TAGS = {"p", "b", "i", "u", "h2", "h3", "span", "div", "ul", "ol", "li", "br", "font"}
ALLOWED_ATTRIBUTES = {
    "span": {"style"},
    "div": {"style", "class"},
    "font": {"color", "size", "style"}
}

# === عرض قائمة المقالات ===
@router.get("/", response_class=HTMLResponse)
async def list_articles(request: Request, page: int = 1):
    cxt = SessionService.get_page_context(request, additional_perms=["view_tree", "add_article", "delete_article"])
    articles, total_pages = ArticleService.get_all_articles(page=page, per_page=12)
    
    context = {**cxt}
    context.update({
        "articles": articles,
        "page": page,
        "total_pages": total_pages,
        "has_prev": page > 1,
        "has_next": page < total_pages,
        "error": request.query_params.get("error", None)
    })
    response = templates.TemplateResponse("articles/list.html", context)
    SessionService.set_cache_headers(response)
    return response

# === التوجيه إلى أحدث مقال ===
@router.get("/latest")
async def latest_article_redirect():
    latest_id = ArticleService.get_latest_article_id()
    if not latest_id:
        return RedirectResponse("/articles", status_code=303)
    return RedirectResponse(f"/articles/{latest_id}", status_code=303)
                
# === عرض مقال + التعليقات ===
@router.get("/{id:int}", response_class=HTMLResponse)
async def view_article(request: Request, id: int):
    cxt = SessionService.get_page_context(request, additional_perms=["view_tree", "edit_article", "delete_article", "add_comment", "delete_comment"])
    article, comments = ArticleService.get_article_details(id)
    
    if not article: 
        raise HTTPException(404, "المقال غير موجود")

    context = {**cxt}
    context.update({
       "article": article, 
       "comments": comments,
    })
    response = templates.TemplateResponse("articles/detail.html", context)
    SessionService.set_cache_headers(response)
    return response

# === صفحة إضافة مقال ===
@router.get("/add", response_class=HTMLResponse)
async def add_article_form(request: Request):
    cxt = SessionService.get_page_context(request, additional_perms=["view_tree", "add_article"])
    if not cxt.get("user") or not cxt.get("perms", {}).get("add_article", False):
        return RedirectResponse(url="/articles/?error=unauthorized", status_code=303)
  
    context = {**cxt}
    context.update({"form_data": {}})
    response = templates.TemplateResponse("articles/add.html", context)
    SessionService.set_cache_headers(response)
    return response

@router.post("/add")
async def add_article(
    request: Request, 
    title: str = Form(...),
    content: str = Form(...), 
    image: UploadFile = File(None)
):
    cxt = SessionService.get_page_context(request, additional_perms=["add_article"])
    user = cxt["user"]
    if not user or not cxt.get("perms", {}).get("add_article", False):
        raise HTTPException(status_code=403, detail="لا تملك صلاحية النشر")
        
    form = await request.form()
    SessionService.verify_csrf_token(request, form.get("csrf_token"))
    
    title_stripped = title.strip()
    content_stripped = content.strip()
    
    # تنظيف المحتوى وحمايته من XSS بشكل احترافي مع الإبقاء على ستايلات الألوان والخطوط
    clean_html_content = nh3.clean(
        content_stripped,
        tags=ALLOWED_TAGS,
        attributes=ALLOWED_ATTRIBUTES
    )

    error = None
    if not title_stripped:
        error = "عنوان المقال مطلوب."
    elif not re.fullmatch(VALID_TITLE_REGEX, title_stripped):
        error = "العنوان يحتوي على رموز غير مسموح بها."
    elif not content_stripped or len(content_stripped) < 10 or content_stripped == "اكتب محتوى مقالك هنا...":
        error = "محتوى المقال قصير جداً أو فارغ."

    # الفحص الأمني للغلاف المرفوع إن وجد
    if image and image.filename:
        ext = os.path.splitext(image.filename).lower()
        if ext not in ALLOWED_IMAGE_EXTENSIONS:
            error = "امتداد الصورة غير مدعوم! المسموح: JPG, PNG, WEBP, GIF"
        
        # فحص الحجم
        image.file.seek(0, os.SEEK_END)
        if image.file.tell() > MAX_IMAGE_SIZE_BYTES:
            error = "حجم صورة الغلاف كبير جداً! الحد الأقصى 5 ميجابايت."
        image.file.seek(0)

    if error:
        context = {**cxt}
        context.update({
            "error": error,
            "form_data": {"title": title, "content": content} 
        })
        return templates.TemplateResponse("articles/add.html", context)

    try:
        # العنوان يتم تخزينه نظيفاً وسيتكفل جينجا بحمايته، والمحتوى يمر مطهراً ومصفى بالكامل
        article_id = await ArticleService.create_article(
            title=title_stripped, 
            content=clean_html_content,          
            author_id=user["id"],
            image_file=image if image and image.filename else None
        )
      
        AnalyticsService.log_action(user["id"], "إضافة مقال", f"تم نشر مقال جديد بعنوان: {title_stripped}")    
        return RedirectResponse(f"/articles/{article_id}", status_code=303)
        
    except Exception as e:
        print(f"❌ Error: {e}")
        raise HTTPException(500, "حدث خطأ داخلي أثناء حفظ المقال")    

# === تعديل مقال ===
@router.get("/edit/{id:int}", response_class=HTMLResponse)
async def edit_article_form(request: Request, id: int):
    cxt = SessionService.get_page_context(request, additional_perms=["view_tree", "edit_article"])
    if not cxt.get("user") or not cxt.get("perms", {}).get("edit_article", False):
        return RedirectResponse(url="/articles/?error=unauthorized", status_code=303)

    article = ArticleService.get_article_by_id(id)
    if not article:
        raise HTTPException(404, "المقال غير موجود.")
               
    context = {**cxt}
    context.update({"article": article})
    response = templates.TemplateResponse("articles/edit.html", context)
    SessionService.set_cache_headers(response)
    return response
    
@router.post("/edit/{id:int}")
async def update_article(
    request: Request, 
    id: int, 
    title: str = Form(...), 
    content: str = Form(...), 
    image: UploadFile = File(None)
):
    cxt = SessionService.get_page_context(request, additional_perms=["edit_article"])
    user = cxt["user"]
    if not user or not cxt.get("perms", {}).get("edit_article", False):
        raise HTTPException(status_code=403, detail="لا تملك صلاحية التعديل")

    form = await request.form()
    SessionService.verify_csrf_token(request, form.get("csrf_token"))

    title_stripped = title.strip()
    content_stripped = content.strip()
    
    clean_html_content = nh3.clean(content_stripped, tags=ALLOWED_TAGS, attributes=ALLOWED_ATTRIBUTES)

    error = None
    if not title_stripped:
        error = "عنوان المقال مطلوب."
    elif not re.fullmatch(VALID_TITLE_REGEX, title_stripped):
        error = "العنوان يحتوي على رموز غير مسموح بها."
    elif not content_stripped or len(content_stripped) < 10:
        error = "محتوى المقال قصير جداً."

    if image and image.filename:
        ext = os.path.splitext(image.filename).lower()
        if ext not in ALLOWED_IMAGE_EXTENSIONS:
            error = "امتداد الصورة غير مدعوم."
        image.file.seek(0, os.SEEK_END)
        if image.file.tell() > MAX_IMAGE_SIZE_BYTES:
            error = "حجم صورة الغلاف كبير جداً (الحد الأقصى 5 ميجابايت)."
        image.file.seek(0)

    if error:
        article = ArticleService.get_article_by_id(id)
        if not article: raise HTTPException(404, "المقال غير موجود")
        article['title'] = title
        article['content'] = content
        
        context = {**cxt}
        context.update({"article": article, "error": error})
        return templates.TemplateResponse("articles/edit.html", context)
       
    await ArticleService.update_article(
        article_id=id, 
        title=title_stripped,
        content=clean_html_content, 
        image_file=image if image and image.filename else None
    )
    
    AnalyticsService.log_action(user["id"], "تعديل مقال", f"قام {user['username']} بتعديل المقال رقم ({id})")
    return RedirectResponse(f"/articles/{id}", status_code=303)

# === حذف مقال ===
@router.post("/delete/{id:int}")
async def delete_article(request: Request, id: int):
    cxt = SessionService.get_page_context(request, additional_perms=["delete_article"])
    user = cxt["user"]
    if not user or not cxt.get("perms", {}).get("delete_article", False):
        raise HTTPException(status_code=403, detail="لا تملك الصلاحية لحذف المقال.")

    form = await request.form()
    SessionService.verify_csrf_token(request, form.get("csrf_token"))

    article_data = ArticleService.get_article_details(id)
    title = article_data[0]['title'] if article_data[0] else "مقال غير معروف"

    # الحذف الآن يعمل بشكل Async تصاعدي لحماية تفرع الشبكة
    await ArticleService.delete_article(id)

    AnalyticsService.log_action(user["id"], "حذف مقال", f"حذف {user['username']} المقال ({id}) بعنوان: {title}")
    return RedirectResponse("/articles", status_code=303)    

# === إضافة تعليق ===
@router.post("/{id:int}/comment")
async def add_comment(request: Request, id: int, content: str = Form(...)):
    cxt = SessionService.get_page_context(request, additional_perms=["add_comment"])
    user = cxt["user"]
    if not user or not cxt.get("perms", {}).get("add_comment", False):
        return RedirectResponse(url=f"/articles/{id}?error=unauthorized", status_code=303)

    form = await request.form()
    SessionService.verify_csrf_token(request, form.get("csrf_token"))

    content_safe = html.escape(content.strip())
    if not content_safe:
        return RedirectResponse(url=f"/articles/{id}?error=empty_comment", status_code=303)
        
    ArticleService.add_comment(id, user["id"], content_safe)
    AnalyticsService.log_action(user["id"], "إضافة تعليق", f"علّق {user['username']} على المقال رقم ({id})")
    return RedirectResponse(f"/articles/{id}#comments", status_code=303)

# === حذف تعليق ===
@router.post("/{article_id:int}/comment/{comment_id:int}/delete")
async def delete_comment(request: Request, article_id: int, comment_id: int):
    cxt = SessionService.get_page_context(request, additional_perms=["delete_comment"])
    user = cxt["user"]
    if not user or not cxt.get("perms", {}).get("delete_comment", False):
         raise HTTPException(status_code=403, detail="غير مصرح لك.")

    form = await request.form()
    SessionService.verify_csrf_token(request, form.get("csrf_token"))

    comment = ArticleService.get_comment_owner(comment_id)
    if not comment: 
        raise HTTPException(404, "التعليق غير موجود")
    
    allowed = (user.get("id") == comment["user_id"] or SessionService.can(user, "delete_comment"))
    if not allowed: 
        raise HTTPException(403, "غير مسموح لك بالحذف")

    ArticleService.delete_comment(comment_id)
    AnalyticsService.log_action(user["id"], "حذف تعليق", f"حذف {user['username']} تعليقاً في المقال ({article_id})")
    return RedirectResponse(f"/articles/{article_id}#comments", status_code=303)