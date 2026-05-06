from fastapi import APIRouter, Request,  HTTPException, Form
from services.permission_service import PermissionService
from security.csrf import  verify_csrf_token
from fastapi.responses import HTMLResponse, RedirectResponse
from security.session import set_cache_headers,get_page_context
from core.templates import templates
import html # تم إضافة هذه المكتبة لتنقية المدخلات (Sanitization)

router = APIRouter(prefix="/permissions", tags=["permissions"])
@router.get("/", response_class=HTMLResponse)
async def permissions_page(request: Request, page: int = 1):
    cxt = get_page_context(request)
    isad = cxt["is_admin"]
    if not isad:
        raise HTTPException(status_code=403, detail="غير مصرح لك بالوصول")

    # جلب كل البيانات من السيرفس بضغطة واحدة
    data = PermissionService.get_permissions_data(page)
    
   
    # 2. تجهيز السياق الموحد (سيحتوي على user و can_view و unread_count)
    context = {**cxt} # فك القاموس لتمرير user, perms, unread_count, etc. بشكل مباشر للسياق
    # 3. تحديث السياق بالبيانات الخاصة بالصفحة الرئيسية
    context.update({
        "current_page": page,
        "error_message": request.session.pop("error_message", None),
        "success_message": request.session.pop("success_message", None),
        **data # فك القاموس لتمرير perms, users, assignments, etc.
    })
    response = templates.TemplateResponse("/permissions/permissions.html",  context)
    set_cache_headers(response)
    return response
   

@router.post("/add_permission")
async def add_permission(request: Request, name: str = Form(...), category: str = Form(...), 
                         current_page: int = Form(1), csrf_token: str = Form(...)):
    cxt = get_page_context(request)
    isad = cxt["is_admin"]
    if not isad:
        raise HTTPException(status_code=403, detail="غير مصرح لك بالوصول")
    
    verify_csrf_token(request, csrf_token)
    
    success, message = PermissionService.add_permission(html.escape(name.strip()), html.escape(category.strip()))
    
    request.session["success_message" if success else "error_message"] = message
    return RedirectResponse(f"/permissions?page={current_page}", status_code=303)


@router.post("/edit_permission")
async def edit_permission(
    request: Request, 
    perm_id: int = Form(...), 
    name: str = Form(...), 
    category: str = Form(...), 
    current_page: int = Form(1),
    csrf_token: str = Form(...)
):
    cxt = get_page_context(request)
    isad = cxt["is_admin"]
    if not isad:
        raise HTTPException(status_code=403, detail="غير مصرح لك بالوصول")
    
    verify_csrf_token(request, csrf_token)
    
    try:
        success, message = PermissionService.update_permission(perm_id, html.escape(name.strip()), html.escape(category.strip()))
        request.session["success_message" if success else "error_message"] = message
        return RedirectResponse(f"/permissions?page={current_page}", status_code=303)

               
    except Exception as e:
        request.session["error_message"] = f"فشل في تعديل الصلاحية: {str(e)}"
        return RedirectResponse(url=f"/permissions?page={current_page}", status_code=303)
    

@router.post("/delete_permission")
async def delete_permission(
    request: Request, 
    perm_id: int = Form(...), 
    current_page: int = Form(1),
    csrf_token: str = Form(...)
):
    cxt = get_page_context(request)
    isad = cxt["is_admin"]
    if not isad:
        raise HTTPException(status_code=403, detail="غير مصرح لك بالوصول")

    verify_csrf_token(request, csrf_token)

    try:
        success, message = PermissionService.delete_permission(perm_id)
        request.session["success_message" if success else "error_message"] = message
    except Exception as e:
        request.session["error_message"] = f"فشل في حذف الصلاحية: {str(e)}"
    
    # لا تنسى هذا السطر للعودة للصفحة
    return RedirectResponse(url=f"/permissions?page={current_page}", status_code=303)