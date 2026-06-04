from fastapi import APIRouter, Request, Form, UploadFile, File, HTTPException, BackgroundTasks
from fastapi.responses import HTMLResponse, RedirectResponse, StreamingResponse
import re
import html 
import os
from typing import Optional

import urllib

import httpx
from security.session import SessionService
from services.analytics_service import AnalyticsService
from services.library_service import LibraryService
from core.templates import templates

router = APIRouter(prefix="/library", tags=["Library"])

CATEGORIES = ["كتب دينية", "كتب علمية", "كتب طبية", "كتب هندسية", "كتب ثقافية", "مقرارات ومناهج سودانية", "روايات"]
VALID_TITLE_REGEX = r"^[\u0600-\u06FFa-zA-Z0-9\s\.\,\!\؟\-\(\)\[\]\{\}]+$"
ALLOWED_EXTENSIONS = {'.pdf', '.doc', '.docx', '.ppt', '.pptx'}
MAX_FILE_SIZE_BYTES = 40 * 1024 * 1024  # 40 ميجابايت كحد أقصى للحماية

@router.get("/", response_class=HTMLResponse)
async def list_library(request: Request, category: str = "الكل", page: int = 1, q: str = None):
    cxt = SessionService.get_page_context(request, additional_perms=["view_tree", "add_book", "edit_book", "delete_book"])
    
    PER_PAGE = 10
    books, total_pages, page_numbers = LibraryService.get_books_paginated(category, page, PER_PAGE, q)
   
    context = {**cxt}
    context.update({
        "books": books, 
        "categories": CATEGORIES,
        "selected_category": category,
        "page_numbers": page_numbers, 
        "current_page": page,
        "total_pages": total_pages,
        "q": q  
    })
    
    response = templates.TemplateResponse("library/index.html", context)
    SessionService.set_cache_headers(response)
    return response
    
@router.get("/add", response_class=HTMLResponse)
async def add_book_page(request: Request, from_page: str = "library"):
    cxt = SessionService.get_page_context(request, additional_perms=["view_tree", "add_book"])
    user = cxt["user"]
    if not user:
        return RedirectResponse(url="/auth/login/?error=unauthorized", status_code=303)

    if not cxt.get("perms", {}).get("add_book", False):
        return RedirectResponse(url=f"/library?error=unauthorized", status_code=303)
   
    context = {**cxt}
    context.update({
         "categories": CATEGORIES,
         "from_page": from_page
    })
    response = templates.TemplateResponse("library/add.html", context)
    SessionService.set_cache_headers(response)
    return response

@router.post("/add")
async def add_book(
    request: Request,
    background_tasks: BackgroundTasks,
    title: str = Form(...),
    author: str = Form(None),
    category: str = Form(...),
    allow_download: Optional[str] = Form(None), # 💡 إصلاح ثغرة الـ Checkbox بالاستقبال النصي المرن
    book_file: UploadFile = File(...),
    cover_image: UploadFile = File(None)
):
    cxt = SessionService.get_page_context(request, additional_perms=["add_book"])
    user = cxt["user"]
    if not user:
        return RedirectResponse(url="/auth/login/?error=unauthorized", status_code=303)

    if not cxt.get("perms", {}).get("add_book", False):
        raise HTTPException(status_code=403, detail="لا تملك صلاحية الإضافة")

    form = await request.form()
    SessionService.verify_csrf_token(request, form.get("csrf_token"))
    
    # تحويل حالة الـ Checkbox إلى متغيّر منطقي حقيقي
    is_download_allowed = True if allow_download == "on" else False
    
    title_stripped = title.strip()
    author_stripped = author.strip() if author else "غير معروف"
    
    # 🚨 1. جدار الحماية للباكيند: فحص الامتداد والحجم قبل استهلاك الموارد
    file_ext = os.path.splitext(book_file.filename).lower()
    if file_ext not in ALLOWED_EXTENSIONS:
        return await return_with_error(request, cxt, "صيغة الملف غير مدعومة! المسموح: PDF, Word, PowerPoint", title_stripped, author_stripped)
        
    # قراءة حجم الملف التقريبي لحماية الهارد ديسك
    book_file.file.seek(0, os.SEEK_END)
    file_size = book_file.file.tell()
    book_file.file.seek(0)  # إعادة المؤشر للبداية لقراءته لاحقاً
    
    if file_size > MAX_FILE_SIZE_BYTES:
        return await return_with_error(request, cxt, "حجم الملف كبير جداً! الحد الأقصى المسموح به هو 40 ميجابايت.", title_stripped, author_stripped)

    # 🚨 2. فحص نمط العنوان ضد محاولات الحقن
    if not title_stripped:
        return await return_with_error(request, cxt, "عنوان الكتاب مطلوب.", title_stripped, author_stripped)
    elif not re.fullmatch(VALID_TITLE_REGEX, title_stripped):
        return await return_with_error(request, cxt, "العنوان يحتوي على رموز غير مسموح بها.", title_stripped, author_stripped)
    
    if category not in CATEGORIES:
        return await return_with_error(request, cxt, "التصنيف المختار غير مدرج بالنظام.", title_stripped, author_stripped)

    try:
        # معالجة سريعة واستخراج البيانات الوصفية محلياً
        local_file_path, auto_cover_url, actual_size_str = await LibraryService.process_and_get_metadata(book_file)

        final_cover_url = auto_cover_url
        if cover_image and cover_image.filename:
            manual_cover = await LibraryService.upload_cover(cover_image)
            if manual_cover:
                final_cover_url = manual_cover

        # تخزين البيانات نظيفة في قاعدة البيانات
        book_id = await LibraryService.add_book(
            title=title_stripped,
            author=author_stripped,
            category=category,
            allow_download=is_download_allowed,
            file_url="pending", 
            cover_url=final_cover_url,
            uploader_id=user["id"],
            file_size=actual_size_str 
        )

        # الترحيل الفوري للمهمة الثقيلة لتعمل في الخلفية
        background_tasks.add_task(
            LibraryService.background_upload, 
            local_file_path,   
            book_file.filename, 
            book_id
        )

        AnalyticsService.log_action(user["id"], "إضافة كتاب", f"بدأ {user['username']} رفع كتاب: {title_stripped}")
        return RedirectResponse("/library", status_code=303)

    except Exception as e:
        print(f"❌ Error during processing: {e}")
        return await return_with_error(request, cxt, "حدث خطأ غير متوقع في الخادم أثناء معالجة الملف.", title_stripped, author_stripped)

async def return_with_error(request, cxt, error_msg, title, author):
    """دالة مساعدة لإرجاع رسالة الخطأ مع الحفاظ على المدخلات واضحة"""
    context = {**cxt}
    context.update({
        "categories": CATEGORIES, 
        "error": error_msg, 
        "title": title, 
        "author": author,
        "from_page": request.query_params.get("from", "library")
    })
    response = templates.TemplateResponse("library/add.html", context)
    SessionService.set_cache_headers(response)
    return response

@router.get("/edit/{book_id}", response_class=HTMLResponse)
async def edit_book_page(request: Request, book_id: int):
    cxt = SessionService.get_page_context(request, additional_perms=["edit_book"])
    user = cxt["user"]
    if not user:
        return RedirectResponse(url="/auth/login/?error=unauthorized", status_code=303)
        
    if not cxt.get("perms", {}).get("edit_book", False):
        return RedirectResponse(url="/library?error=unauthorized", status_code=303)
    
    book = LibraryService.get_book_by_id(book_id)
    if not book:
        raise HTTPException(status_code=404, detail="الكتاب غير موجود")

    # التقاط مسار العودة الذكي (من الصفحة الشخصية أو المكتبة)
    from_page = request.query_params.get("from", "library")

    context = {**cxt}
    context.update({
        "book": book,
        "categories": CATEGORIES,
        "from_page": from_page,
        "error": request.query_params.get("error_msg", None) # عرض الأخطاء المرتدة إن وجدت
    })
    response = templates.TemplateResponse("library/edit.html", context)
    SessionService.set_cache_headers(response)
    return response
    

@router.post("/edit/{book_id}")
async def edit_book(
    request: Request,
    book_id: int,
    title: str = Form(...),
    author: str = Form(None),
    category: str = Form(...),
    allow_download: Optional[str] = Form(None), # 💡 تم الإصلاح: استقبال نصي مرن لحل مشكلة الـ Checkbox
    from_page: str = Form("library", alias="from") # 💡 حفظ مسار العودة الذكي بعد ضغط الحفظ
):
    cxt = SessionService.get_page_context(request, additional_perms=["edit_book"])
    user = cxt["user"]
    if not user:
        return RedirectResponse(url="/auth/login/?error=unauthorized", status_code=303)
        
    if not cxt.get("perms", {}).get("edit_book", False):
        raise HTTPException(status_code=403, detail="لا تملك صلاحية التعديل")

    form = await request.form()
    SessionService.verify_csrf_token(request, form.get("csrf_token"))
    
    # تحويل حالة صندوق الاختيار منطقياً
    is_download_allowed = True if allow_download == "on" else False
    
    title_stripped = title.strip()
    author_stripped = author.strip() if author else "غير معروف"

    # 🚨 جدار الحماية: التحقق من صحة المدخلات ونظافتها
    if not title_stripped:
        return RedirectResponse(f"/library/edit/{book_id}?from={from_page}&error_msg=عنوان الكتاب مطلوب", status_code=303)
    
    if not re.fullmatch(VALID_TITLE_REGEX, title_stripped):
        return RedirectResponse(f"/library/edit/{book_id}?from={from_page}&error_msg=العنوان يحتوي على رموز غير مسموح بها", status_code=303)
        
    if category not in CATEGORIES:
        return RedirectResponse(f"/library/edit/{book_id}?from={from_page}&error_msg=التصنيف غير مدعوم", status_code=303)

    # 🚨 حفظ البيانات نظيفة دون حشو تفادياً لخراب عمليات البحث الذكي
    success = LibraryService.update_book(book_id, title_stripped, author_stripped, category, is_download_allowed)
    
    if success:
        AnalyticsService.log_action(user["id"], "تعديل كتاب", f"قام {user['username']} بتعديل بيانات الكتاب: {title_stripped}")
        
        # التوجيه الذكي: إذا كان قادماً من الصفحة الشخصية يعود إليها، وإلا يعود للمكتبة
        target_url = "/profile" if from_page == "profile" else "/library?success=updated"
        return RedirectResponse(target_url, status_code=303)
    else:
        return RedirectResponse(f"/library/edit/{book_id}?from={from_page}&error_msg=failed", status_code=303)

@router.post("/delete/{book_id}")
async def delete_book(request: Request, book_id: int):
    cxt = SessionService.get_page_context(request,additional_perms=["delete_book"])
    user = cxt["user"]
    if not user :
        return RedirectResponse(url="/auth/login/?error=unauthorized", status_code=303)
    # 🛡️ خط الدفاع الأخير: إذا حاول شخص تجاوز الـ GET وإرسال الطلب مباشرة
    is_allowed = cxt.get("perms", {}).get("delete_book", False)
    if not is_allowed:
        raise HTTPException(status_code=403, detail="لا تملك صلاحية الحذف")

    form = await request.form()
    SessionService.verify_csrf_token(request, form.get("csrf_token")) 
    # تنفيذ الحذف واسترجاع بيانات الكتاب للسجل
    deleted_book = LibraryService.delete_book(book_id)
    
    if deleted_book:
        AnalyticsService.log_action(
            user_id=user["id"],
            action="حذف كتاب",
            details=f"قام {user['username']} بحذف كتاب: {deleted_book['title']} من المكتبة"
        )

    return RedirectResponse("/library", status_code=303)

@router.get("/admin/system-cleanup")
async def admin_system_cleanup(request: Request):
    # التأكد من الصلاحيات
    cxt = SessionService.get_page_context(request)
    user = cxt["user"]
    isad = cxt["is_admin"]
    if not isad:
        raise HTTPException(status_code=403, detail="غير مصرح لك")

    # استدعاء الخدمة
    count = LibraryService.cleanup_orphaned_cloudinary_files()
    
    return {"status": "success", "deleted_files_count": count}

@router.get("/view/{book_id}", response_class=HTMLResponse)
async def view_book(request: Request, book_id: int):
    book_data = LibraryService.increment_view(book_id)
    
    if not book_data or book_data['file_url'] in ['pending', 'error']:
        return RedirectResponse(url="/library?error=not_ready")

    file_url = book_data['file_url']
    book_title = book_data.get('title', 'عرض كتاب')
    # تنظيف الرابط وتجهيزه
    clean_url = file_url.split('?')[0]
    ext = clean_url.split('.')[-1].lower()
    
    # ضمان استخدام https لروابط Cloudinary
    target_url = file_url.replace("http://", "https://") if "cloudinary" in file_url else file_url

    import urllib.parse
    encoded_url = urllib.parse.quote(target_url, safe='')

    # 1. إذا كان الملف من Google Drive (يعمل دائماً)
    if "drive.google.com" in target_url:
        import urllib.parse as urlparse
        url_data = urlparse.urlparse(target_url)
        query = urlparse.parse_qs(url_data.query)
        file_id = query.get('id', [None])[0]
        embed_url = f"https://drive.google.com/file/d/{file_id}/preview"
    
    # 2. ملفات Word/Office من أي مصدر آخر (Cloudinary مثلاً)
    # سنستخدم مشغل Google Viewer بدلاً من Microsoft لأنه يحل مشكلة الأمان في الإنتاج
    elif any(x in ext for x in ['doc', 'docx', 'ppt', 'pptx']):
        embed_url = f"https://docs.google.com/viewer?url={encoded_url}&embedded=true"
    
    # 3. ملفات PDF وكل ما تبقى
    else:
        # استخدام مشغل جوجل لضمان العرض المباشر في الموبايل والكمبيوتر
        embed_url = f"https://docs.google.com/viewer?url={encoded_url}&embedded=true"

    return templates.TemplateResponse("library/viewer_google.html", {
        "request": request, 
        "embed_url": embed_url,
        "book_id": book_id, 
        "book_title": book_title
    })

@router.get("/download/{book_id}")
async def download_book(book_id: int):
    # 1. جلب بيانات الكتاب كاملة من قاعدة البيانات
    book_data = LibraryService.increment_download(book_id)
    if not book_data:
        raise HTTPException(status_code=404, detail="الكتاب غير موجود")

    file_url = book_data['file_url']
    book_title = book_data.get('title', 'book') 
    
    # استخراج وتنظيف الامتداد والاسم
    ext = os.path.splitext(file_url.split('?')[0])[1].lower()
    if not ext:
        ext = ".pdf"
        
    clean_title = re.sub(r'[^\w\s-]', '', book_title).strip().replace(' ', '_')
    download_name = f"{clean_title}{ext}"
    encoded_filename = urllib.parse.quote(download_name)

    # 2. إذا كان الملف مرفوعاً على Cloudinary (الملفات الصغيرة أقل من 10 ميجا)
    if "cloudinary" in file_url:
        
        # دالة البث المصححة هندسياً للاستهلاك الآمن من httpx
        async def file_streamer():
            async with httpx.AsyncClient() as client:
                async with client.stream("GET", file_url) as response:
                    # التحقق من أن خادم Cloudinary استجاب بنجاح قبل بدء البث
                    if response.status_code != 200:
                        raise HTTPException(status_code=400, detail="فشل جلب الملف من خادم التخزين")
                        
                    # الاستماع للبث باستخدام aiter_bytes() الصريحة للأ동 الفوري
                    async for chunk in response.aiter_bytes(chunk_size=128 * 1024): # بث على أجزاء 128 كيلوبايت
                        yield chunk

        headers = {
            "Content-Disposition": f"attachment; filename*=UTF-8''{encoded_filename}",
            "Content-Type": "application/octet-stream"
        }
        # تمرير دالة المولد مباشرة لـ StreamingResponse لتقرأ الـ __aiter__ بشكل سليم
        return StreamingResponse(file_streamer(), headers=headers)

    # 3. إذا كان الملف مرفوعاً على Google Drive (الملفات الكبيرة أكبر من 10 ميجا)
    else:
        return RedirectResponse(url=file_url)

@router.get("/admin/fix-errors")
async def admin_fix_errors(request: Request):
    """حذف كل سجلات الكتب التي فشل رفعها (status: error)"""
    cxt = SessionService.get_page_context(request)
    user = cxt["user"]
    isad = cxt["is_admin"]
    if not isad:
        raise HTTPException(status_code=403, detail="غير مصرح لك")

    # استدعاء الدالة الجديدة التي أضفناها في LibraryService
    success = LibraryService.cleanup_error_records()
    
    if success:
        return {"status": "success", "message": "تم تنظيف سجلات الأخطاء بنجاح"}
    else:
        return {"status": "error", "message": "فشل تنظيف السجلات، تحقق من الاتصال بقاعدة البيانات"}