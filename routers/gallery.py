import re
from typing import Optional
from urllib import request, request, response
from fastapi import APIRouter, Request, Form, HTTPException, Query, File, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse
from services.gallery_service import GalleryService
from urllib.parse import urlparse
from core.templates import templates,get_global_context
from security.csrf import generate_csrf_token, verify_csrf_token
from security.session import set_cache_headers
from utils.has_permissions import can
from services.gallery_service import upload_to_cloudinary, GalleryService
from services.analytics import log_action

router = APIRouter(prefix="/gallery", tags=["gallery"])


# 1. عرض المعرض 
@router.get("/", response_class=HTMLResponse)
async def get_gallery(
    request: Request, 
    category: str = Query(None), 
    page: int = Query(1, ge=1), # استقبال رقم الصفحة
    success: Optional[str] = Query(None)
):
    user = request.session.get("user")
    per_page = 12
    
    # جلب الصور والإجمالي من السيرفس
    images, total_images = GalleryService.get_all_images(category, page, per_page)
    
    # حساب إجمالي الصفحات
    total_pages = (total_images + per_page - 1) // per_page
    
    # جلب التصنيفات
    categories = GalleryService.get_categories()

    csrf_token = generate_csrf_token()
    request.session["csrf_token"] = csrf_token

    messages = {"added": "✅ تم إضافة الصورة بنجاح.", "deleted": "✅ تم حذف الصورة بنجاح."}
    
   
    # 2. تجهيز السياق الموحد (سيحتوي على user و can_view و unread_count)
    context = get_global_context(request)
    
    # 3. تحديث السياق بالبيانات الخاصة بالصفحة الرئيسية
    context.update({
      "images": images,
        "selected_category": category,
        "categories": categories,
        "current_page": page,
        "total_pages": total_pages,
        "page_numbers": range(1, total_pages + 1),
        "csrf_token": csrf_token,
        "can_add": can(user, "add_gallery"),
        "can_delete": can(user, "delete_gallery"),
        "success": messages.get(success)
    })
    
    response = templates.TemplateResponse("gallery/index.html", context)
    set_cache_headers(response)
    return response

@router.get("/add", response_class=HTMLResponse)
async def add_image_page(request: Request):
    user = request.session.get("user")
    if not user:
        return RedirectResponse("/login")

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
        return templates.TemplateResponse("gallery/add.html", {
            "request": request, "user": user, "error": "العنوان قصير جداً", "csrf_token": generate_csrf_token()
        })
        
   
    if title[0].isdigit() or re.search(r"^[\s\-\_\.\@\#\!\$\%\^\&\*\(\)]", title):
        raise HTTPException(status_code=400, detail="العنوان لا يجب أن يبدأ برمز أو رقم (ابدأ بوصف واضح)")
    

   

    # 3. الرفع إلى Cloudinary أولاً
    # نمرر ملف الصورة المرفوع إلى الدالة التي أنشأناها في gallery_service
    try:
        # تأكيد العودة لبداية الملف لضمان قراءة البيانات كاملة
        await image.seek(0)
        
        # نمرر الملف للدالة المحسنة
        cloudinary_url = upload_to_cloudinary(image.file)
        
        if not cloudinary_url:
            # في حال فشل الرفع، نرجع المستخدم لصفحة الإضافة مع رسالة واضحة
            return templates.TemplateResponse("gallery/add.html", {
                "request": request, 
                "user": request.session.get("user"), 
                "error": "فشل الاتصال بـ Cloudinary، يرجى المحاولة مرة أخرى",
                "csrf_token": generate_csrf_token()
            })

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
        print(f"Server Internal Error: {e}")
        return templates.TemplateResponse("gallery/add.html", {
            "request": request, "user": user, "error": "حدث خطأ فني غير متوقع", "csrf_token": generate_csrf_token()
        })
    

@router.post("/delete/{image_id}")
async def delete_photo(
    request: Request, 
    image_id: int, 
    page: int = Query(1), # استقبال رقم الصفحة الحالية
    category: str = Query(None) # استقبال التصنيف الحالي إن وجد
):
    user = request.session.get("user")
    
    # 1. فحص الصلاحية
    if not can(user, "delete_gallery"):
        raise HTTPException(status_code=403)
    
    # 2. التحقق من CSRF
    form = await request.form()
    verify_csrf_token(request, form.get("csrf_token"))
    
    try:
        if GalleryService.delete_image(image_id):
            # تسجيل النشاط
            log_action(
                user_id=user['id'],
                action="حذف صورة",
                details=f"تم حذف مادة من المعرض (ID: {image_id}) وإزالتها من السحابة"
            )
            
            # بناء رابط العودة الذكي
            redirect_url = f"/gallery?success=deleted&page={page}"
            if category and category != "None":
                redirect_url += f"&category={category}"
                
            return RedirectResponse(url=redirect_url, status_code=303)
            
    except Exception as e:
        print(f"Delete Error: {e}")
        raise HTTPException(status_code=500, detail=f"فشل الحذف للصورة {image_id}.")