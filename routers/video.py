import re
from typing import Optional
import math
from fastapi import APIRouter, Request, Form, HTTPException, Query, File, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse
from core.templates import templates
from security.session import SessionService
from services.video_service import upload_video_to_cloudinary, VideoService
from services.analytics_service import AnalyticsService
from urllib.parse import quote

router = APIRouter(prefix="/video", tags=["video"])

ALLOWED_VIDEO_EXTENSIONS = {".mp4", ".m4v", ".mov", ".avi", ".webm"}
ALLOWED_VIDEO_MIME_TYPES = {"video/mp4", "video/x-m4v", "video/quicktime", "video/x-msvideo", "video/webm"}

@router.get("/", response_class=HTMLResponse)
async def get_video(
    request: Request, 
    category: str = Query(None), 
    page: int = Query(1, ge=1),
    success: Optional[str] = Query(None)
):
    cxt = SessionService.get_page_context(request, additional_perms=["view_tree", "add_video", "delete_video"])
    per_page = 18
    
    videos, total_videos = VideoService.get_all_videos(category, page, per_page)
    total_pages = math.ceil(total_videos / per_page) if total_videos > 0 else 1

    messages = {
        "added": "✅ تم إضافة الفيديو بنجاح.",
        "deleted": "✅ تم حذف الفيديو بنجاح."
    }
    
    context = {**cxt}
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
    if not cxt or not cxt.get("perms", {}).get("add_video", False):
        return RedirectResponse(url="/video/?error=unauthorized", status_code=303)

    response = templates.TemplateResponse("video/add.html", cxt)
    SessionService.set_cache_headers(response)
    return response

@router.post("/add")
async def add_video_action(
    request: Request,
    title: str = Form(...),
    category: str = Form(...),
    video_file: UploadFile = File(...)
):
    cxt = SessionService.get_page_context(request, additional_perms=["add_video"])
    user = cxt["user"]
    if not cxt.get("perms", {}).get("add_video", False):
        raise HTTPException(status_code=403, detail="لا تملك صلاحية الإضافة")
    
    form = await request.form()
    SessionService.verify_csrf_token(request, form.get("csrf_token"))
    
    title = title.strip()
    if not title or len(title) < 3:
        raise HTTPException(status_code=400, detail="العنوان قصير جداً")
    
    if title[0].isdigit() or re.search(r"^[\s\-\_\.\@\#\!\$\%\^\&\*\(\)]", title):
        raise HTTPException(status_code=400, detail="العنوان لا يجب أن يبدأ برمز أو رقم")
    
    # 🔒 التحقق الخلفي من نوع الملف وامتداده لحماية السيرفر
    file_ext = f".{video_file.filename.split('.')[-1]}".lower() if "." in video_file.filename else ""
    if file_ext not in ALLOWED_VIDEO_EXTENSIONS or video_file.content_type not in ALLOWED_VIDEO_MIME_TYPES:
        raise HTTPException(status_code=400, detail="صيغة الملف غير مدعومة! يسمح بالفيديوهات القياسية فقط.")

    video_url = None
    try:
        # 🚀 إصلاح ثغرة الذاكرة الحرج: نمرر تدفق الملف من القرص دون تحميله في الـ RAM
        await video_file.seek(0)
        video_url = upload_video_to_cloudinary(video_file.file)

        if not video_url:
            return RedirectResponse(url="/video/add?error=upload_failed", status_code=303)

        # حفظ السجل
        video_id = VideoService.add_video_to_db(
            title=title,
            video_url=video_url,
            category=category,
            user_id=user.get("id")
        )

        if video_id:
            AnalyticsService.log_action(user.get("id"), "إضافة فيديو", f"تم رفع فيديو جديد بعنوان: {title}")
            return RedirectResponse(url="/video/?success=added", status_code=303)
        
        # إذا لم يتم استرجاع معرف، نثير استثناء لتنظيف الملف سحابياً
        raise Exception("Failed to save video record in database")

    except Exception as e:
        print(f"❌ خطأ حرج في معالجة رفع الفيديو: {e}")
        # 🧹 تنظيف السحابة فوراً من مخلفات الفيديو اليتيم
        if video_url:
            try:
                file_name = video_url.split('/')[-1].split('.')[0]
                VideoService.delete_video_from_cloudinary(f"hottiyya_videos/{file_name}")
            except Exception as clean_err:
                print(f"⚠️ فشل تنظيف الفيديو التالف سحابياً: {clean_err}")
                
        return RedirectResponse(url="/video/add?error=system_error", status_code=303)

@router.post("/delete/{video_id}")
async def delete_video_action(request: Request, video_id: int):
    cxt = SessionService.get_page_context(request, additional_perms=["view_tree", "delete_video"])
    user = cxt["user"]
    if not cxt.get("perms", {}).get("delete_video", False):
        raise HTTPException(status_code=403, detail="غير مسموح لك.")
    
    form = await request.form()
    SessionService.verify_csrf_token(request, form.get("csrf_token"))

    try:
        # 🚀 إصلاح ثغرة الأداء القاتلة: نجلب الفيديو المستهدف حصراً بالـ id بدلاً من جلب 1000 سجل
        video = VideoService.get_video_by_id(video_id)

        if not video:
            return RedirectResponse(url="/video/?error=not_found", status_code=303)

        video_url = video.get('video_url', '')
        if video_url:
            file_parts = video_url.split('/')
            file_name_with_ext = file_parts[-1].split('.')[0]
            public_id = f"hottiyya_videos/{file_name_with_ext}"
            # حذف الفيديو من السحابة
            VideoService.delete_video_from_cloudinary(public_id)

        # الحذف النهائي من قاعدة البيانات
        if VideoService.delete_video_from_db(video_id):
            AnalyticsService.log_action(user.get("id"), "حذف فيديو", f"تم حذف فيديو: {video.get('title')}")
            return RedirectResponse(url="/video/?success=deleted", status_code=303)

    except Exception as e:
        print(f"❌ خطأ حرج في الحذف: {str(e)}")
        return RedirectResponse(url="/video/?error=delete_failed", status_code=303)

    return RedirectResponse(url="/video/?error=system_error", status_code=303)