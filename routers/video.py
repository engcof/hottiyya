import re
from typing import Optional
from fastapi import APIRouter, Request, Form, HTTPException, Query, File, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse
from services.gallery_service import GalleryService
from urllib.parse import urlparse
from core.templates import templates
from security.session import SessionService
from services.video_service import upload_video_to_cloudinary, VideoService
from services.analytics_service import AnalyticsService

router = APIRouter(prefix="/video", tags=["video"])

# 1. عرض المعرض (تم تحديثه لإضافة CSRF والصلاحيات للواجهة)
@router.get("/", response_class=HTMLResponse)
async def get_video(
    request: Request, 
    category: str = Query(None), 
    page: int = Query(1, ge=1),
    success: Optional[str] = Query(None)
):
    cxt = SessionService.get_page_context(request,additional_perms=["view_tree", "add_video", "delete_video"])
    per_page = 18
    
    # جلب الفيديوهات والعدد الإجمالي
    videos, total_videos = VideoService.get_all_videos(category, page, per_page)

   
    # حساب إجمالي الصفحات
    import math
    total_pages = math.ceil(total_videos / per_page)

   

    # تجهيز رسائل النجاح
    messages = {
        "added": "✅ تم إضافة الفيديو بنجاح.",
        "deleted": "✅ تم حذف الفيديو بنجاح."
    }
    
    # 2. تجهيز السياق الموحد (سيحتوي على user و can_view و unread_count)
    context = {**cxt}
    
    # 3. تحديث السياق بالبيانات الخاصة بالصفحة الرئيسية
    context.update({
      "videos": videos,
        "selected_category": category,
        "current_page": page,
        "total_pages": total_pages,
        "total_videos": total_videos,
        "success": messages.get(success)
    })
    response = templates.TemplateResponse("video/index.html", context)
    SessionService.set_cache_headers(response)
    return response

@router.get("/add", response_class=HTMLResponse)
async def add_video_page(request: Request):
    cxt = SessionService.get_page_context(request, additional_perms=["view_tree", "add_video"])
    if not cxt:
        return RedirectResponse(url="/video/?error=unauthorized", status_code=303)

    # التحقق من الصلاحية
    added = cxt.get("perms", {}).get("add_video", False)
    if not added:
         return RedirectResponse(url="/video/?error=unauthorized", status_code=303)

    response = templates.TemplateResponse("video/add.html", cxt) # نمرر cxt مباشرة لأنه يحتوي على csrf_token
    SessionService.set_cache_headers(response)
    return response


@router.post("/add")
async def add_video_action(
    request: Request,
    title: str = Form(...),
    category: str = Form(...),
    video_file: UploadFile = File(...),
    
):
    cxt = SessionService.get_page_context(request,additional_perms=[ "add_video"])
    user = cxt["user"]
    added = cxt.get("perms", {}).get("add_video", False)
    if not added:
        raise HTTPException(status_code=403, detail="لا تملك صلاحية الإضافة ")
    
    form = await request.form()
    SessionService.verify_csrf_token(request, form.get("csrf_token"))
    
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
            AnalyticsService.log_action(user.get("id"), "إضافة فيديو", f"تم رفع فيديو جديد بعنوان: {title}")
            return RedirectResponse(url="/video/?success=added", status_code=303)

    except Exception as e:
        print(f"❌ خطأ في معالجة رفع الفيديو: {e}")
        return RedirectResponse(url="/video/add?error=system_error", status_code=303)

    return RedirectResponse(url="/video/add?error=db_error", status_code=303)

@router.post("/delete/{video_id}")
async def delete_video_action(request: Request, video_id: int):
    cxt = SessionService.get_page_context(request,additional_perms=["view_tree", "delete_video"])
    user = cxt["user"]
    perms = cxt.get("perms", {})
    deleted = perms.get("delete_video", False)

    if not deleted:
        raise HTTPException(status_code=403, detail="غير مسموح لك.")
    
    form = await request.form()
    SessionService.verify_csrf_token(request, form.get("csrf_token"))

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
            AnalyticsService.log_action(user.get("id"), "حذف فيديو", f"تم حذف: {video_to_delete.get('title')}")
            return RedirectResponse(url="/video/?success=deleted", status_code=303)

    except Exception as e:
        print(f"❌ خطأ حرج في الحذف: {str(e)}")
        return RedirectResponse(url="/video/?error=delete_failed", status_code=303)

    return RedirectResponse(url="/video/?error=system_error", status_code=303)

