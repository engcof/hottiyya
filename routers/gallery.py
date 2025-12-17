import re
from typing import Optional
from fastapi import APIRouter, Request, Form, HTTPException, Query, File, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse
from services.gallery_service import GalleryService
from urllib.parse import urlparse
from core.templates import templates
from security.csrf import generate_csrf_token, verify_csrf_token
from security.session import set_cache_headers
from utils.permission import has_permission
from services.gallery_service import upload_to_cloudinary, GalleryService
from services.analytics import log_action

router = APIRouter(prefix="/gallery", tags=["gallery"])

# ====================== مساعد الصلاحيات ======================
def can(user: dict, perm: str) -> bool:
    if not user: return False
    if user.get("role") == "admin": return True
    return bool(user.get("id") and has_permission(user.get("id"), perm))

# 1. عرض المعرض (تم تحديثه لإضافة CSRF والصلاحيات للواجهة)
@router.get("/", response_class=HTMLResponse)
async def get_gallery(request: Request, category: str = Query(None), success: Optional[str] = Query(None)):
    user = request.session.get("user")
    images = GalleryService.get_all_images(category)

    can_add    = can(user, "add_gallery")
    can_edit   = can(user, "edit_gallery")
    can_delete = can(user, "delete_gallery")

    # توليد توكن الأمان لكل جلسة
    csrf_token = generate_csrf_token()
    request.session["csrf_token"] = csrf_token

    # تجهيز رسائل النجاح
    messages = {
        "added": "✅ تم إضافة الصورة بنجاح.",
        "deleted": "✅ تم حذف الصورة بنجاح."
    }
    
    response = templates.TemplateResponse("gallery/index.html", {
        "request": request,
        "user": user,
        "images": images,
        "selected_category": category,
        "csrf_token": csrf_token,
        "can_add": can(user, "add_gallery"),
        "can_edit": can(user, "edit_gallery"),
        "can_delete": can(user, "delete_gallery"),
        "success": messages.get(success)
    })
    set_cache_headers(response)
    return response

@router.get("/add", response_class=HTMLResponse)
async def add_image_page(request: Request):
    user = request.session.get("user")
    if not user:
        return RedirectResponse("/login")

    # توليد توكن جديد وتخزينه في الجلسة
    from security.csrf import generate_csrf_token
    csrf_token = generate_csrf_token()
    request.session["csrf_token"] = csrf_token

    return templates.TemplateResponse("gallery/add.html", {
        "request": request,
        "user": user,
        "csrf_token": csrf_token  # إرساله للقالب ليتم وضعه في الـ hidden input
    })

@router.post("/add")
async def add_new_image(
    request: Request,
    title: str = Form(...),
    image: UploadFile = File(...), # تغيير من str إلى UploadFile
    category: str = Form(None),
    csrf_token: str = Form(...)
):
    user = request.session.get("user")
    
    form = await request.form()
    verify_csrf_token(request, form.get("csrf_token"))

    # 1. فحص الصلاحية والـ CSRF
    if not user or not can(user, "add_gallery"):
        raise HTTPException(status_code=403, detail="ليس لديك صلاحية")
   
    # 2. تنظيف العنوان والتحقق منه
    title = title.strip()
    if not title or len(title) < 3:
        raise HTTPException(status_code=400, detail="العنوان قصير جداً")
    
   
    if title[0].isdigit() or re.search(r"^[\s\-\_\.\@\#\!\$\%\^\&\*\(\)]", title):
        raise HTTPException(status_code=400, detail="العنوان لا يجب أن يبدأ برمز أو رقم (ابدأ بوصف واضح)")
    

   

    # 3. الرفع إلى Cloudinary أولاً
    # نمرر ملف الصورة المرفوع إلى الدالة التي أنشأناها في gallery_service
    try:
        
        
        # نستخدم image.file للحصول على تدفق البيانات (stream)
        cloudinary_url = upload_to_cloudinary(image.file)
        
        if not cloudinary_url:
            raise HTTPException(status_code=500, detail="فشل رفع الصورة إلى التخزين السحابي")

        # 4. الحفظ في قاعدة البيانات باستخدام الرابط الناتج
        GalleryService.add_image(
            title=title, 
            image_url=cloudinary_url, # الرابط الذي جاء من Cloudinary
            user_id=user['id'], 
            category=category
        )

        # 5. تسجيل النشاط (البصمة الاحترافية لـ engcof)
        log_action(
            user_id=user['id'],
            action="إضافة صورة",
            details=f"تم رفع صورة بعنوان '{title}' بنجاح إلى المعرض"
        )

        return RedirectResponse(url="/gallery?success=added", status_code=303)

    except Exception as e:
        print(f"Error: {e}")
        raise HTTPException(status_code=500, detail="حدث خطأ أثناء معالجة الصورة")
    
   


@router.post("/delete/{image_id}")
async def delete_photo(request: Request, image_id: int):
    user = request.session.get("user")
    # فحص الصلاحية أولاً (فقط engcof أو الأدمن)
    if not can(user, "delete_gallery"):
        raise HTTPException(status_code=403)
    
     # 2. التحقق من CSRF
    form = await request.form()
    verify_csrf_token(request, form.get("csrf_token"))
    try:
        if GalleryService.delete_image(image_id):
            # تسجيل بصمة engcof في السجل
            log_action(
                user_id=user['id'],
                action="حذف صورة",
                details=f"تم حذف مادة من المعرض (ID: {image_id}) وإزالتها من التخزين السحابي"
            )
            return RedirectResponse("/gallery?success=deleted", status_code=303)
    except Exception as e:
        # في حال فشل الحذف، لن يتم تسجيل أي نشاط في السجل الشامل
        raise HTTPException(status_code=500, detail=f"فشل الحذف للصورة {image_id}.")    