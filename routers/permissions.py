from fastapi import APIRouter, Request, Depends, HTTPException, Form
from postgresql import get_db_context
from services.permission_service import PermissionService
from security.csrf import generate_csrf_token, verify_csrf_token
from fastapi.responses import HTMLResponse, RedirectResponse
from security.session import set_cache_headers,get_current_user
from psycopg2.extras import RealDictCursor
from core.templates import templates
import html # تم إضافة هذه المكتبة لتنقية المدخلات (Sanitization)

router = APIRouter(prefix="/permissions", tags=["permissions"])
@router.get("/", response_class=HTMLResponse)
async def permissions_page(request: Request, page: int = 1):
    user = get_current_user(request)
    if not user or user.get("role") != "admin":
        return RedirectResponse("/auth/login", status_code=303)

    # جلب كل البيانات من السيرفس بضغطة واحدة
    data = PermissionService.get_permissions_data(page)
    
    csrf_token = generate_csrf_token()
    request.session["csrf_token"] = csrf_token

    response = templates.TemplateResponse("/permissions/permissions.html", {
        "request": request,
        "csrf_token": csrf_token,
        "user": user,
        "current_page": page,
        "error_message": request.session.pop("error_message", None),
        "success_message": request.session.pop("success_message", None),
        **data # فك القاموس لتمرير perms, users, assignments, etc.
    })
    set_cache_headers(response)
    return response


@router.post("/add_permission")
async def add_permission(request: Request, name: str = Form(...), category: str = Form(...), 
                         current_page: int = Form(1), csrf_token: str = Form(...)):
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
    verify_csrf_token(request, csrf_token)

    try:
        success, message = PermissionService.delete_permission(perm_id)
        request.session["success_message" if success else "error_message"] = message
    except Exception as e:
        request.session["error_message"] = f"فشل في حذف الصلاحية: {str(e)}"
    
    # لا تنسى هذا السطر للعودة للصفحة
    return RedirectResponse(url=f"/permissions?page={current_page}", status_code=303)