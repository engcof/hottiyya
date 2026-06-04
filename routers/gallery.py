import re
from typing import Optional
from fastapi import APIRouter, Request, Form, HTTPException, Query, File, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse
from services.gallery_service import GalleryService, upload_to_cloudinary
from core.templates import templates
from security.session import SessionService
from services.analytics_service import AnalyticsService

router = APIRouter(prefix="/gallery", tags=["gallery"])

# قائمة بالامتدادات المسموح بها أمنياً لمعرض الصور
ALLOWED_IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".gif", ".webp"}
ALLOWED_MIME_TYPES = {"image/jpeg", "image/png", "image/gif", "image/webp"}

@router.get("/", response_class=HTMLResponse)
async def get_gallery(
    request: Request, 
    category: str = Query(None), 
    page: int = Query(1, ge=1),
    success: Optional[str] = Query(None)
):
    cxt = SessionService.get_page_context(request, additional_perms=["view_tree", "add_gallery", "delete_gallery"])
    per_page = 12
    
    images, total_images = GalleryService.get_all_images(category, page, per_page)
    total_pages = (total_images + per_page - 1) // per_page if total_images > 0 else 1
    categories = GalleryService.get_categories()

    messages = {"added": "✅ تم إضافة الصورة بنجاح.", "deleted": "✅ تم حذف الصورة بنجاح."}
    
    context = {**cxt}
    context.update({
        "images": images,
        "selected_category": category,
        "categories": categories,
        "current_page": page,
        "total_pages": total_pages,
        "page_numbers": range(1, total_pages + 1),
        "success": messages.get(success)
    })
    response = templates.TemplateResponse("gallery/index.html", context)
    SessionService.set_cache_headers(response)
    return response

@router.get("/add", response_class=HTMLResponse)
async def add_image_page(request: Request):
    cxt = SessionService.get_page_context(request, additional_perms=["view_tree", "add_gallery"])
    if not cxt or not cxt.get("perms", {}).get("add_gallery", False):
        return RedirectResponse(url="/gallery/?error=unauthorized", status_code=303)

    response = templates.TemplateResponse("gallery/add.html", cxt)
    SessionService.set_cache_headers(response)
    return response

@router.post("/add")
async def add_new_image(
    request: Request,
    title: str = Form(...),
    image: UploadFile = File(...),
    category: str = Form(None),
    csrf_token: str = Form(...)
):
    cxt = SessionService.get_page_context(request, additional_perms=["add_gallery"])
    user = cxt["user"]
    if not cxt.get("perms", {}).get("add_gallery", False):
        raise HTTPException(status_code=403, detail="لا تملك صلاحية الإضافة")
    
    form = await request.form()
    SessionService.verify_csrf_token(request, form.get("csrf_token"))

    title = title.strip()
    if not title or len(title) < 3:
        return templates.TemplateResponse("gallery/add.html", {**cxt, "error": "العنوان قصير جداً"})
      
    if title[0].isdigit() or re.search(r"^[\s\-\_\.\@\#\!\$\%\^\&\*\(\)]", title):
        raise HTTPException(status_code=400, detail="العنوان لا يجب أن يبدأ برمز أو رقم")
    
    # 🔒 فحص الامتداد ونوع الملف (مهم جداً لسد ثغرة رفع الملفات الخبيثة)
    file_ext = f".{image.filename.split('.')[-1]}".lower() if "." in image.filename else ""
    if file_ext not in ALLOWED_IMAGE_EXTENSIONS or image.content_type not in ALLOWED_MIME_TYPES:
        return templates.TemplateResponse("gallery/add.html", {**cxt, "error": "نوع الملف غير مدعوم! يسمح فقط بالصور المعتادة."})

    cloudinary_url = None
    image_id = None
    try:
        await image.seek(0)
        # رفع الصورة للسحابة
        cloudinary_url = upload_to_cloudinary(image.file)
        
        if not cloudinary_url:
            return templates.TemplateResponse("gallery/add.html", {**cxt, "error": "فشل الاتصال بالسحابة، حاول مجدداً"})
          
        # الحفظ في قاعدة البيانات
        image_id = GalleryService.add_image(
            title=title, 
            image_url=cloudinary_url, 
            user_id=user['id'], 
            category=category
        )

        AnalyticsService.log_action(
            user_id=user['id'],
            action="إضافة صورة",
            details=f"تم رفع صورة بعنوان '{title}' بنجاح إلى المعرض"
        )
        return RedirectResponse(url="/gallery?success=added", status_code=303)

    except Exception as e:
        print(f"🔥 Server Internal Error: {e}")
        # 🧹 حماية المنظومة من الملفات اليتيمة إذا فشلت قاعدة البيانات بعد الرفع
        if cloudinary_url:
            try:
                from services.gallery_service import extract_public_id
                import cloudinary.uploader
                pub_id = extract_public_id(cloudinary_url)
                if pub_id:
                    cloudinary.uploader.destroy(pub_id)
            except Exception as clean_err:
                print(f"⚠️ فشل تنظيف السحابة: {clean_err}")

        return templates.TemplateResponse("gallery/add.html", {**cxt, "error": "حدث خطأ فني أثناء حفظ البيانات"})

@router.post("/delete/{image_id}")
async def delete_photo(
    request: Request, 
    image_id: int, 
    page: int = Query(1), 
    category: str = Query(None)
):
    cxt = SessionService.get_page_context(request, additional_perms=["delete_gallery"])
    user = cxt["user"]
    if not cxt.get("perms", {}).get("delete_gallery", False):
        raise HTTPException(status_code=403, detail="لا تملك الصلاحية لحذف الصورة.")
    
    form = await request.form()
    SessionService.verify_csrf_token(request, form.get("csrf_token"))
    
    try:
        if GalleryService.delete_image(image_id):
            AnalyticsService.log_action(
                user_id=user['id'],
                action="حذف صورة",
                details=f"تم حذف مادة من المعرض (ID: {image_id})"
            )
            
            # بناء رابط رجوع آمن وخالٍ من المشاكل البصرية
            redirect_url = f"/gallery?success=deleted&page={page}"
            if category and category != "None":
                from urllib.parse import quote
                redirect_url += f"&category={quote(category)}"
                
            return RedirectResponse(url=redirect_url, status_code=303)
    except Exception as e:
        print(f"Delete Error: {e}")
        raise HTTPException(status_code=500, detail="فشل الحذف الفني للصورة.")