from fastapi import APIRouter, Request, HTTPException, Form
from services.permission_service import PermissionService
from fastapi.responses import HTMLResponse, RedirectResponse
from security.session import SessionService
from core.templates import templates
import html

router = APIRouter(prefix="/permissions", tags=["permissions"])

@router.get("/", response_class=HTMLResponse)
async def permissions_page(request: Request, page: int = 1):
    cxt = SessionService.get_page_context(request)
    if not cxt or not cxt.get("is_admin"):
        raise HTTPException(status_code=403, detail="غير مصرح لك بالوصول")

    # جلب البيانات من السيرفس
    data = PermissionService.get_permissions_data(page)
    
    # تجهيز السياق الموحد
    context = {**cxt}
    context.update({
        "current_page": page,
        "error_message": request.session.pop("error_message", None),
        "success_message": request.session.pop("success_message", None),
        **data
    })
    
    response = templates.TemplateResponse("/permissions/permissions.html", context)
    SessionService.set_cache_headers(response)
    return response


@router.post("/add_permission")
async def add_permission(
    request: Request, 
    name: str = Form(...), 
    category: str = Form(...), 
    current_page: int = Form(1), 
    csrf_token: str = Form(...)
):
    cxt = SessionService.get_page_context(request)
    if not cxt or not cxt.get("is_admin"):
        raise HTTPException(status_code=403, detail="غير مصرح لك بالوصول")
    
    # سد الثغرة: التحقق من توكن الـ CSRF عبر الكلاس الموحد
    SessionService.verify_csrf_token(request, csrf_token)
    
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
    cxt = SessionService.get_page_context(request)
    if not cxt or not cxt.get("is_admin"):
        raise HTTPException(status_code=403, detail="غير مصرح لك بالوصول")
    
    # ✅ تم إصلاح الثغرة القاتلة: الاستدعاء الآن يمر عبر كلاس السيشن الموحد
    SessionService.verify_csrf_token(request, csrf_token)
    
    try:
        success, message = PermissionService.update_permission(perm_id, html.escape(name.strip()), html.escape(category.strip()))
        request.session["success_message" if success else "error_message"] = message
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
    cxt = SessionService.get_page_context(request)
    if not cxt or not cxt.get("is_admin"):
        raise HTTPException(status_code=403, detail="غير مصرح لك بالوصول")

    SessionService.verify_csrf_token(request, csrf_token)

    try:
        success, message = PermissionService.delete_permission(perm_id)
        request.session["success_message" if success else "error_message"] = message
    except Exception as e:
        request.session["error_message"] = f"فشل في حذف الصلاحية: {str(e)}"
    
    return RedirectResponse(url=f"/permissions?page={current_page}", status_code=303)