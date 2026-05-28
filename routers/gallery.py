import re
from typing import Optional
from urllib import request, request, response
from fastapi import APIRouter, Request, Form, HTTPException, Query, File, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse
from services.gallery_service import GalleryService
from urllib.parse import urlparse
from core.templates import templates
from security.session import SessionService
from services.gallery_service import upload_to_cloudinary, GalleryService
from services.analytics_service import AnalyticsService

router = APIRouter(prefix="/gallery", tags=["gallery"])


# 1. عرض المعرض 
@router.get("/", response_class=HTMLResponse)
async def get_gallery(
    request: Request, 
    category: str = Query(None), 
    page: int = Query(1, ge=1), # استقبال رقم الصفحة
    success: Optional[str] = Query(None)
):
    cxt = SessionService.get_page_context(request,additional_perms=["view_tree", "add_gallery", "delete_gallery"])
    per_page = 12
    
    # جلب الصور والإجمالي من السيرفس
    images, total_images = GalleryService.get_all_images(category, page, per_page)
    
    # حساب إجمالي الصفحات
    total_pages = (total_images + per_page - 1) // per_page
    
    # جلب التصنيفات
    categories = GalleryService.get_categories()

    messages = {"added": "✅ تم إضافة الصورة بنجاح.", "deleted": "✅ تم حذف الصورة بنجاح."}
    
    # 2. تجهيز السياق الموحد (سيحتوي على user و can_view و unread_count)
    context = {**cxt}
    
    # 3. تحديث السياق بالبيانات الخاصة بالصفحة الرئيسية
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
    if not cxt:
        return RedirectResponse(url="/gallery/?error=unauthorized", status_code=303)

    # التحقق من الصلاحية
    added = cxt.get("perms", {}).get("add_gallery", False)
    if not added:
         return RedirectResponse(url="/gallery/?error=unauthorized", status_code=303)

    response = templates.TemplateResponse("gallery/add.html", cxt) # نمرر cxt مباشرة لأنه يحتوي على csrf_token
    SessionService.set_cache_headers(response)
    return response

   
@router.post("/add")
async def add_new_image(
    request: Request,
    title: str = Form(...),
    image: UploadFile = File(...), # تغيير من str إلى UploadFile
    category: str = Form(None),
    csrf_token: str = Form(...)
):
    cxt = SessionService.get_page_context(request,additional_perms=[ "add_gallery"])
    user = cxt["user"]
    edited = cxt.get("perms", {}).get("add_gallery", False)
    if not edited:
        raise HTTPException(status_code=403, detail="لا تملك صلاحية الإضافة")
    
    form = await request.form()
    SessionService.verify_csrf_token(request, form.get("csrf_token"))

    # 2. تنظيف العنوان والتحقق منه
    title = title.strip()
    if not title or len(title) < 3:
         # 2. تجهيز السياق الموحد (سيحتوي على user و can_view و unread_count)
        context =   {**cxt}
        
        # 3. تحديث السياق بالبيانات الخاصة بالصفحة الرئيسية
        context.update({
          "error": "العنوان قصير جداً", 
        })
        
        response = templates.TemplateResponse("gallery/add.html",  context)
        SessionService.set_cache_headers(response)
        return response
      
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
            # 2. تجهيز السياق الموحد (سيحتوي على user و can_view و unread_count)
            context =   {**cxt}
            
            # 3. تحديث السياق بالبيانات الخاصة بالصفحة الرئيسية
            context.update({
              "error": "فشل الاتصال بـ Cloudinary، يرجى المحاولة مرة أخرى",
            })
            
            response = templates.TemplateResponse("gallery/add.html",  context)
            SessionService.set_cache_headers(response)
            return response
          
        # 4. الحفظ في قاعدة البيانات باستخدام الرابط الناتج
        GalleryService.add_image(
            title=title, 
            image_url=cloudinary_url, # الرابط الذي جاء من Cloudinary
            user_id=user['id'], 
            category=category
        )

        # 5. تسجيل النشاط (البصمة الاحترافية لـ engcof)
        AnalyticsService.log_action(
            user_id=user['id'],
            action="إضافة صورة",
            details=f"تم رفع صورة بعنوان '{title}' بنجاح إلى المعرض"
        )

        return RedirectResponse(url="/gallery?success=added", status_code=303)

    except Exception as e:
        print(f"Server Internal Error: {e}")
        # 2. تجهيز السياق الموحد (سيحتوي على user و can_view و unread_count)
        context =   {**cxt}
        
        # 3. تحديث السياق بالبيانات الخاصة بالصفحة الرئيسية
        context.update({
           "error": "حدث خطأ فني غير متوقع"
        })
        
        response = templates.TemplateResponse("gallery/add.html",  context)
        SessionService.set_cache_headers(response)
        return response
       

@router.post("/delete/{image_id}")
async def delete_photo(
    request: Request, 
    image_id: int, 
    page: int = Query(1), # استقبال رقم الصفحة الحالية
    category: str = Query(None) # استقبال التصنيف الحالي إن وجد
):
    cxt = SessionService.get_page_context(request,additional_perms=[ "delete_gallery"])
    user = cxt["user"]
    perms = cxt.get("perms", {})
    deleted = perms.get("delete_gallery", False)
    # 1. فحص الصلاحية
    if not deleted :
        raise HTTPException(status_code=403, detail="لا تملك الصلاحية لحذف الصورة.")
    
    # 2. التحقق من CSRF
    form = await request.form()
    SessionService.verify_csrf_token(request, form.get("csrf_token"))
    
    try:
        if GalleryService.delete_image(image_id):
            # تسجيل النشاط
            AnalyticsService.log_action(
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