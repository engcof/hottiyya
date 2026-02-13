import re
from typing import Optional
from fastapi import APIRouter, Request, Form, HTTPException, Query, File, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse
from services.gallery_service import GalleryService
from urllib.parse import urlparse
from core.templates import templates
from security.csrf import generate_csrf_token, verify_csrf_token
from security.session import set_cache_headers
from utils.permission import can
from services.video_service import upload_video_to_cloudinary, VideoService
from services.analytics import log_action

router = APIRouter(prefix="/video", tags=["video"])

# 1. عرض المعرض (تم تحديثه لإضافة CSRF والصلاحيات للواجهة)
@router.get("/", response_class=HTMLResponse)
async def get_video(
    request: Request, 
    category: str = Query(None), 
    page: int = Query(1, ge=1),
    success: Optional[str] = Query(None)
):
    user = request.session.get("user")
    per_page = 18
    
    # جلب الفيديوهات والعدد الإجمالي
    videos, total_videos = VideoService.get_all_videos(category, page, per_page)

   
    # حساب إجمالي الصفحات
    import math
    total_pages = math.ceil(total_videos / per_page)

    # توليد توكن الأمان لكل جلسة
    csrf_token = generate_csrf_token()
    request.session["csrf_token"] = csrf_token

    # تجهيز رسائل النجاح
    messages = {
        "added": "✅ تم إضافة الفيديو بنجاح.",
        "deleted": "✅ تم حذف الفيديو بنجاح."
    }
    
    response = templates.TemplateResponse("video/index.html", {
        "request": request,
        "user": user,
        "videos": videos,
        "selected_category": category,
        "csrf_token": csrf_token,
        "current_page": page,
        "total_pages": total_pages,
        "total_videos": total_videos,
        "can_add": can(user, "add_video"),
        "can_edit": can(user, "edit_video"),
        "can_delete": can(user, "delete_video"),
        "success": messages.get(success)
    })
    set_cache_headers(response)
    return response

@router.get("/add", response_class=HTMLResponse)
async def add_video_page(request: Request):
    user = request.session.get("user")
    
    # التحقق من الصلاحية قبل عرض الصفحة
    if not can(user, "add_video"):
        return RedirectResponse(url="/video/?error=unauthorized", status_code=303)

    # توليد توكن الأمان للنموذج
    csrf_token = generate_csrf_token()
    request.session["csrf_token"] = csrf_token

    return templates.TemplateResponse("video/add.html", {
        "request": request,
        "user": user,
        "csrf_token": csrf_token,
        "title": "إضافة فيديو جديد"
    })

@router.post("/add")
async def add_video_action(
    request: Request,
    title: str = Form(...),
    category: str = Form(...),
    video_file: UploadFile = File(...),
    csrf_token: str = Form(...)
):
    user = request.session.get("user")
    
    form = await request.form()
    verify_csrf_token(request, form.get("csrf_token"))
    
    if not can(user, "add_video"):
        raise HTTPException(status_code=403, detail="غير مسموح لك بإجراء هذه العملية.")
    
     
    title = title.strip()
    if not title or len(title) < 3:
        raise HTTPException(status_code=400, detail="العنوان قصير جداً")
    
   
    if title[0].isdigit() or re.search(r"^[\s\-\_\.\@\#\!\$\%\^\&\*\(\)]", title):
        raise HTTPException(status_code=400, detail="العنوان لا يجب أن يبدأ برمز أو رقم (ابدأ بوصف واضح)")
    

    try:
        # 2. رفع الفيديو إلى Cloudinary باستخدام الخدمة التي صممتها
        # نستخدم await read() لقراءة الملف المرفوع
        video_content = await video_file.read()
        video_url = upload_video_to_cloudinary(video_content)

        if not video_url:
            return RedirectResponse(url="/video/add?error=upload_failed", status_code=303)

        # 3. حفظ البيانات في قاعدة البيانات
        video_id = VideoService.add_video_to_db(
            title=title,
            video_url=video_url,
            category=category,
            user_id=user.get("id")
        )

        if video_id:
            # 4. تسجيل العملية في سجل النشاطات لضمان الرقابة
            log_action(user.get("id"), "إضافة فيديو", f"تم رفع فيديو جديد بعنوان: {title}")
            return RedirectResponse(url="/video/?success=added", status_code=303)

    except Exception as e:
        print(f"❌ خطأ في معالجة رفع الفيديو: {e}")
        return RedirectResponse(url="/video/add?error=system_error", status_code=303)

    return RedirectResponse(url="/video/add?error=db_error", status_code=303)

@router.post("/delete/{video_id}")
async def delete_video_action(request: Request, video_id: int):
    user = request.session.get("user")
    
    if not can(user, "delete_video"):
        raise HTTPException(status_code=403, detail="غير مسموح لك.")
    
    form = await request.form()
    verify_csrf_token(request, form.get("csrf_token"))

    try:
        # 1. انتبه هنا: الدالة ترجع (قائمة، عدد) لذا نستخدم الفاصلة لاستلامهما
        videos_list, total_count = VideoService.get_all_videos(per_page=1000) # جلب الكل للبحث
        
        # 2. البحث عن الفيديو في القائمة المستلمة (وهي قائمة قواميس الآن)
        video_to_delete = next((v for v in videos_list if int(v.get('id')) == video_id), None)

        if not video_to_delete:
            print(f"⚠️ لم يتم العثور على الفيديو {video_id} في القائمة")
            # محاولة حذف اضطرارية من القاعدة مباشرة حتى لو لم يظهر في القائمة
            if VideoService.delete_video_from_db(video_id):
                 return RedirectResponse(url="/video/?success=deleted", status_code=303)
            return RedirectResponse(url="/video/?error=not_found", status_code=303)

        # 3. استخراج الرابط والحذف من Cloudinary
        video_url = video_to_delete.get('video_url', '')
        if video_url:
            # تنظيف الرابط لاستخراج public_id
            # الرابط عادة: .../v12345/folder/name.mp4 -> نحتاج folder/name
            file_parts = video_url.split('/')
            file_name_with_ext = file_parts[-1].split('.')[0]
            # نستخدم المجلد الافتراضي الذي رفعنا عليه
            public_id = f"hottiyya_videos/{file_name_with_ext}"
            VideoService.delete_video_from_cloudinary(public_id)

        # 4. الحذف النهائي من قاعدة البيانات
        if VideoService.delete_video_from_db(video_id):
            log_action(user.get("id"), "حذف فيديو", f"تم حذف: {video_to_delete.get('title')}")
            return RedirectResponse(url="/video/?success=deleted", status_code=303)

    except Exception as e:
        print(f"❌ خطأ حرج في الحذف: {str(e)}")
        return RedirectResponse(url="/video/?error=delete_failed", status_code=303)

    return RedirectResponse(url="/video/?error=system_error", status_code=303)

