import re  
from fastapi import BackgroundTasks
from fastapi import APIRouter, Request, Form, UploadFile, File, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from urllib.parse import quote
from security.session import set_cache_headers
from security.csrf import generate_csrf_token, verify_csrf_token
from utils.permission import has_permission
from services.analytics import log_action
from services.library_service import LibraryService
import shutil
import os
from core.templates import templates
import html 


router = APIRouter(prefix="/library", tags=["Library"])

# التصنيفات المعتمدة
CATEGORIES = ["كتب دينية", "كتب علمية", "كتب طبية", "كتب هندسية", "كتب ثقافية","كتب مدرسية", "روايات"]
# التعبير النمطي الجديد يدعم العربية والإنجليزية والأرقام وعلامات الترقيم الشائعة
VALID_TITLE_REGEX = r"[\u0600-\u06FFa-zA-Z\s\d\.\,\!\؟\-\(\)]+"

def can(user: dict | None, perm: str) -> bool:
    if not user:
        return False
    if user.get("role") == "admin":
        return True
    user_id = user.get("id")
    return user_id and has_permission(user_id, perm)

@router.get("/", response_class=HTMLResponse)
async def list_library(request: Request, category: str = "الكل", page: int = 1, q: str = None):
    user = request.session.get("user")
    can_add = can(user, "add_book")
    
    PER_PAGE = 10
    # تمرير نص البحث للسيرفس
    books, total_pages = LibraryService.get_books_paginated(category, page, PER_PAGE, q)
    
    csrf_token = generate_csrf_token()
    request.session["csrf_token"] = csrf_token
    
    response = templates.TemplateResponse("library/index.html", {
        "request": request, 
        "user": user, 
        "can_add": can_add,
        "csrf_token": csrf_token,
        "books": books, 
        "categories": CATEGORIES,
        "selected_category": category,
        "current_page": page,
        "total_pages": total_pages,
        "q": q  
    })
    set_cache_headers(response)
    return response
   
   
@router.get("/add", response_class=HTMLResponse)
async def add_book_page(request: Request):
    user = request.session.get("user")
    if not can(user, "add_book"): 
        return RedirectResponse("/library")
    
    csrf_token = generate_csrf_token()
    request.session["csrf_token"] = csrf_token
    return templates.TemplateResponse("library/add.html", {
        "request": request, 
        "user": user, 
        "csrf_token": csrf_token,
        "categories": CATEGORIES}
        )

@router.post("/add")
async def add_book(
    request: Request,
    background_tasks: BackgroundTasks,
    title: str = Form(...),
    author: str = Form(None),
    category: str = Form(...),
    book_file: UploadFile = File(...),
    cover_image: UploadFile = File(None)
):
    user = request.session.get("user")
    if not can(user, "add_book"):
        raise HTTPException(403, "غير مصرح لك بإضافة كتب")
    
    form = await request.form()
    verify_csrf_token(request, form.get("csrf_token"))
    
    title_stripped = title.strip()
    title_safe = html.escape(title_stripped)
    author_safe = html.escape(author.strip()) if author else "غير معروف"
    
    error = None
    if not title_stripped:
        error = "عنوان الكتاب مطلوب."
    elif not re.fullmatch(VALID_TITLE_REGEX, title_stripped):
        error = "العنوان يحتوي على رموز غير مسموح بها."
    
    if error:
        return templates.TemplateResponse("library/add.html", {
            "request": request, "user": user, "error": error, 
            "categories": CATEGORIES, "csrf_token": generate_csrf_token(),
            "title": title, "author": author
        })    

    try:
        # 1. المرحلة السريعة: ضغط الملف واستخراج الغلاف (تعيد المسار المحلي للملف)
        # تم استبدال upload_file بـ process_and_get_metadata
        local_file_path, auto_cover_url, actual_size_str = await LibraryService.process_and_get_metadata(book_file)

        # 2. تحديد الغلاف النهائي (يدوي أو تلقائي)
        final_cover_url = auto_cover_url
        if cover_image and cover_image.filename:
            manual_cover = await LibraryService.upload_cover(cover_image)
            if manual_cover:
                final_cover_url = manual_cover

        # 3. حفظ البيانات في القاعدة فوراً برابط مؤقت (pending)
        # ملاحظة: حذفنا السطر المكرر لـ file_url
        book_id = await LibraryService.add_book(
            title=title_safe,
            author=author_safe,
            category=category,
            file_url="pending", # سيتغير لاحقاً في الخلفية
            cover_url=final_cover_url,
            uploader_id=user["id"],
            file_size=actual_size_str 
        )

        # 4. تشغيل الرفع الحقيقي للسحابة في الخلفية (لن ينتظر المستخدم)
        background_tasks.add_task(
            LibraryService.background_upload, 
            local_file_path,   # المسار المحلي الذي نتج عن المعالجة
            book_file.filename, 
            book_id
        )

        # 5. تسجيل النشاط
        log_action(user["id"], "إضافة كتاب", f"بدأ {user['username']} رفع كتاب: {title_safe}")

        # إعادة المستخدم للمكتبة فوراً
        return RedirectResponse("/library", status_code=303)

    except Exception as e:
        print(f"❌ Error during processing: {e}")
        return templates.TemplateResponse("library/add.html", {
            "request": request, "user": user, 
            "error": "حدث خطأ أثناء معالجة الملف، تأكد من صلاحية الملف والتوكن.",
            "categories": CATEGORIES, "csrf_token": generate_csrf_token()
        })
   

@router.post("/delete/{book_id}")
async def delete_book(request: Request, book_id: int):
    user = request.session.get("user")
    if not can(user, "delete_book"):
        raise HTTPException(403, "غير مصرح لك بالحذف")
    
    form = await request.form()
    verify_csrf_token(request, form.get("csrf_token")) 
    # تنفيذ الحذف واسترجاع بيانات الكتاب للسجل
    deleted_book = LibraryService.delete_book(book_id)
    
    if deleted_book:
        log_action(
            user_id=user["id"],
            action="حذف كتاب",
            details=f"قام {user['username']} بحذف كتاب: {deleted_book['title']} من المكتبة"
        )

    return RedirectResponse("/library", status_code=303)

@router.get("/admin/system-cleanup")
async def admin_system_cleanup(request: Request):
    # التأكد من الصلاحيات
    user = request.session.get("user")
    if not user or user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="غير مصرح لك")

    # استدعاء الخدمة
    count = LibraryService.cleanup_orphaned_cloudinary_files()
    
    return {"status": "success", "deleted_files_count": count}


@router.get("/view/{book_id}", response_class=HTMLResponse)
async def view_book(request: Request, book_id: int):
    # 1. جلب البيانات من السيرفس (تأكد من تحديث دالة increment_view لتعيد dict)
    book_data = LibraryService.increment_view(book_id)
    
    if not book_data or book_data['file_url'] in ['pending', 'error']:
        return RedirectResponse(url="/library?error=not_ready")

    file_url = book_data['file_url']
    book_title = book_data['title']

    if "drive.google.com" in file_url:
        import urllib.parse as urlparse
        url_data = urlparse.urlparse(file_url)
        query = urlparse.parse_qs(url_data.query)
        file_id = query.get('id', [None])[0]
        
        # استخدام رابط الـ preview المباشر لضمان التوافق مع iframe ومنع خطأ 400
        embed_url = f"https://drive.google.com/file/d/{file_id}/preview"
        
        # تصحيح المسار: حذف المائلة الأولى "library/..." وليس "/library/..."
        return templates.TemplateResponse("library/viewer_google.html", {
            "request": request,
            "embed_url": embed_url,
            "book_id": book_id,
            "book_title": book_title
        })
    
    else:
        # تصحيح المسار لـ Cloudinary أيضاً
        return templates.TemplateResponse("library/viewer_pdfjs.html", {
            "request": request,
            "file_url": file_url,
            "book_id": book_id,
            "book_title": book_title
        })
    
@router.get("/download/{book_id}")
async def download_book(book_id: int):
    book_data = LibraryService.increment_download(book_id)
    if not book_data:
        raise HTTPException(status_code=404)

    file_url = book_data['file_url']
    
    # التحميل المباشر من Cloudinary بدون تعديلات في الرابط لتجنب خطأ 400
    if "cloudinary" in file_url:
        final_url = file_url.replace('/upload/', '/upload/fl_attachment/')
    else:
        final_url = file_url

    return RedirectResponse(url=final_url)

@router.get("/admin/fix-errors")
async def admin_fix_errors(request: Request):
    """حذف كل سجلات الكتب التي فشل رفعها (status: error)"""
    user = request.session.get("user")
    if not user or user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="غير مصرح لك")

    # استدعاء الدالة الجديدة التي أضفناها في LibraryService
    success = LibraryService.cleanup_error_records()
    
    if success:
        return {"status": "success", "message": "تم تنظيف سجلات الأخطاء بنجاح"}
    else:
        return {"status": "error", "message": "فشل تنظيف السجلات، تحقق من الاتصال بقاعدة البيانات"}