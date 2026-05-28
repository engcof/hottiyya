from fastapi import APIRouter, Request, Depends, HTTPException, Form
from services.permission_service import PermissionService
from fastapi.responses import HTMLResponse, RedirectResponse
from security.session import SessionService
from core.templates import templates


router = APIRouter(prefix="/about", tags=["about"])

@router.get("/", response_class=HTMLResponse)
async def about_page(request: Request):
    # 1. جلب السياق الموحد (يحتوي على user, unread_count, etc)
    context = SessionService.get_page_context(request)
    
    # لا داعي لـ csrf_token إذا لم تكن هناك نماذج (Forms) في هذه الصفحة
    # إذا كنت ستضيف نموذج "اتصال بنا" مستقبلاً، يمكنك إضافته هنا
    
    response = templates.TemplateResponse("about/about.html", context)
    SessionService.set_cache_headers(response)
    return response