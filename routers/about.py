from fastapi import APIRouter, Request, Depends, HTTPException, Form
from services.permission_service import PermissionService
from security.csrf import generate_csrf_token, verify_csrf_token
from fastapi.responses import HTMLResponse, RedirectResponse
from security.session import set_cache_headers
from core.templates import templates, get_global_context


router = APIRouter(prefix="/about", tags=["about"])

@router.get("/", response_class=HTMLResponse)
async def about_page(request: Request):
    # 1. جلب السياق الموحد (يحتوي على user, unread_count, etc)
    context = get_global_context(request)
    
    # لا داعي لـ csrf_token إذا لم تكن هناك نماذج (Forms) في هذه الصفحة
    # إذا كنت ستضيف نموذج "اتصال بنا" مستقبلاً، يمكنك إضافته هنا
    
    response = templates.TemplateResponse("about/about.html", context)
    set_cache_headers(response)
    return response