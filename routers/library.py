import re
from fastapi import APIRouter, Request, Form, UploadFile, File, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from psycopg2.extras import RealDictCursor
from security.session import set_cache_headers
from security.csrf import generate_csrf_token, verify_csrf_token
from utils.permission import has_permission
from services.analytics import log_action
from services.library_service import LibraryService
import shutil
import os
from core.templates import templates
import html 


router = APIRouter(prefix="/library", tags=["Library"])


# التصنيفات المعتمدة
CATEGORIES = ["كتب دينية", "روايات", "كتب علمية", "كتب طبية", "كتب مدرسية", "كتب ثقافية"]
# التعبير النمطي الجديد يدعم العربية والإنجليزية والأرقام وعلامات الترقيم الشائعة
VALID_TITLE_REGEX = r"[\u0600-\u06FFa-zA-Z\s\d\.\,\!\؟\-\(\)]+"

def can(user: dict | None, perm: str) -> bool:
    if not user:
        return False
    if user.get("role") == "admin":
        return True
    user_id = user.get("id")
    return user_id and has_permission(user_id, perm)

@router.get("/", response_class=HTMLResponse)
async def list_library(request: Request, category: str = "الكل", page: int = 1, q: str = None):
    user = request.session.get("user")
    can_add = can(user, "add_book")
    
    PER_PAGE = 12
    # تمرير نص البحث للسيرفس
    books, total_pages = LibraryService.get_books_paginated(category, page, PER_PAGE, q)
    
    csrf_token = generate_csrf_token()
    request.session["csrf_token"] = csrf_token
    
    response = templates.TemplateResponse("library/index.html", {
        "request": request, 
        "user": user, 
        "can_add": can_add,
        "csrf_token": csrf_token,
        "books": books, 
        "categories": CATEGORIES,
        "selected_category": category,
        "current_page": page,
        "total_pages": total_pages,
        "q": q  
    })
    set_cache_headers(response)
    return response
   

@router.get("/add", response_class=HTMLResponse)
async def add_book_page(request: Request):
    user = request.session.get("user")
    if not can(user, "add_book"): 
        return RedirectResponse("/library")
    
    csrf_token = generate_csrf_token()
    request.session["csrf_token"] = csrf_token
    return templates.TemplateResponse("library/add.html", {
        "request": request, 
        "user": user, 
        "csrf_token": csrf_token,
        "categories": CATEGORIES}
        )

@router.post("/add")
async def add_book(
    request: Request,
    title: str = Form(...),
    author: str = Form(None),
    category: str = Form(...),
    book_file: UploadFile = File(...),
    cover_image: UploadFile = File(None)
):
    user = request.session.get("user")
    if not can(user, "add_book"):
        raise HTTPException(403, "غير مصرح لك بإضافة كتب")
    
    # التحقق من CSRF والنظافة (كما في كودك)
    form = await request.form()
    verify_csrf_token(request, form.get("csrf_token"))
    
    # تطبيق html.escape لمنع XSS قبل الحفظ
    title_stripped = title.strip()
    title_safe = html.escape(title_stripped)
    
    error = None
    
    # 1.التحقق من عدم فراغ العنوان 
    if not title_stripped:
        error = "عنوان  مطلوب."
    # 2. التحقق من نظافة العنوان 
    elif not re.fullmatch(VALID_TITLE_REGEX, title_stripped):
        error = "العنوان يحتوي على رموز غير مسموح بها. يُسمح بالعربية والإنجليزية والأرقام وعلامات الترقيم الشائعة فقط."
    
    # ... بعد التحقق من العنوان والنمط النمطي ...
    if error:
        csrf_token = generate_csrf_token()
        request.session["csrf_token"] = csrf_token
        return templates.TemplateResponse("library/add.html", {
            "request": request, 
            "user": user, 
            "error": error, 
            "categories": CATEGORIES,
            "csrf_token": csrf_token,
            # نعيد البيانات التي أدخلها المستخدم لكي لا يكتبها من جديد
            "title": title,
            "author": author
        })    
    # 1. حساب حجم الملف بصيغة مقروءة
    file_size_bytes = 0
    content = await book_file.read()
    file_size_bytes = len(content)
    await book_file.seek(0) # إعادة المؤشر للبداية للرفع
    
    if file_size_bytes < 1024 * 1024:
        size_str = f"{round(file_size_bytes / 1024, 2)} KB"
    else:
        size_str = f"{round(file_size_bytes / (1024 * 1024), 2)} MB"

    # 2. رفع الملف الأساسي (PDF/Word)
    file_url = await LibraryService.upload_file(book_file)
    if not file_url:
        return templates.TemplateResponse("library/add.html", {
            "request": request, "user": user, "error": "فشل رفع ملف الكتاب", "categories": CATEGORIES
        })

    # 3. رفع الغلاف إن وجد
    cover_url = None
    if cover_image and cover_image.filename:
        cover_url = await LibraryService.upload_cover(cover_image)

    # 4. حفظ في قاعدة البيانات (تنظيف المدخلات أولاً)
    book_id = await LibraryService.add_book(
        title=title_safe,
        author=html.escape(author.strip()) if author else "غير معروف",
        category=category,
        file_url=file_url,
        cover_url=cover_url,
        uploader_id=user["id"],
        file_size=size_str
    )

    # 5. تسجيل النشاط
    log_action(
        user_id=user["id"],
        action="إضافة كتاب",
        details=f"قام {user['username']} برفع كتاب جديد: {title} في قسم {category}"
    )

    return RedirectResponse("/library", status_code=303)

@router.post("/delete/{book_id}")
async def delete_book(request: Request, book_id: int):
    user = request.session.get("user")
    if not can(user, "delete_book"):
        raise HTTPException(403, "غير مصرح لك بالحذف")
    
    form = await request.form()
    verify_csrf_token(request, form.get("csrf_token")) 
    # تنفيذ الحذف واسترجاع بيانات الكتاب للسجل
    deleted_book = LibraryService.delete_book(book_id)
    
    if deleted_book:
        log_action(
            user_id=user["id"],
            action="حذف كتاب",
            details=f"قام {user['username']} بحذف كتاب: {deleted_book['title']} من المكتبة"
        )

    return RedirectResponse("/library", status_code=303)