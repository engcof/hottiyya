import os
import subprocess
from datetime import datetime
from fastapi import APIRouter, Request, HTTPException, Form, File, UploadFile
from fastapi.responses import HTMLResponse, FileResponse
from core.templates import templates
from dotenv import load_dotenv
from urllib.parse import quote_plus
from starlette.background import BackgroundTask 
from security.session import SessionService

# استيراد خدمات العائلة من سيرفس الإنتاج الخفيف
from services.family_service import FamilyService

# تحميل متغيرات البيئة من ملف .env
load_dotenv()

# [تعريف كلمة المرور] 
IMPORT_PASSWORD = os.getenv("IMPORT_PASSWORD", "my_secret_key")

router = APIRouter(prefix="/data", tags=["data"])

# =====================================================================
# 🧰 الدالات المساعدة (Helpers)
# =====================================================================

def cleanup_file(filepath: str):
    """تحذف الملف المؤقت بعد الانتهاء من إرسال الاستجابة."""
    if os.path.exists(filepath):
        try:
            os.remove(filepath)
            print(f"Cleanup: Removed temporary file {filepath}")
        except Exception as clean_e:
            print(f"Cleanup Failed: Could not remove temporary file {filepath}: {clean_e}")


def get_database_url():
    database_url = os.getenv("DATABASE_URL")
    if database_url:
        if database_url.startswith("postgres://"):
            database_url = database_url.replace("postgres://", "postgresql://", 1)
        return database_url
    
    db_host = os.getenv("DB_HOST")
    db_name = os.getenv("DB_NAME")
    db_user = os.getenv("DB_USER")
    db_password = os.getenv("DB_PASSWORD")
    db_port = os.getenv("DB_PORT", "5432")

    if all([db_host, db_name, db_user, db_password]):
        encoded_password = quote_plus(db_password)
        return f"postgresql://{db_user}:{encoded_password}@{db_host}:{db_port}/{db_name}"
    
    return None

# =====================================================================
# 💾 استيراد وتصدير قاعدة البيانات كاملة (pg_dump / pg_restore)
# =====================================================================

@router.get("/import-data", response_class=HTMLResponse)
async def import_page(request: Request):
    cxt = SessionService.get_page_context(request)
    if not cxt["is_admin"]:
        raise HTTPException(status_code=403, detail="غير مصرح لك بالوصول")
        
    context = {**cxt, "message": None}
    
    response = templates.TemplateResponse("data/import_data.html", context)
    SessionService.set_cache_headers(response)
    return response
   

@router.post("/import-data")
async def import_data(
    request: Request,
    dump_file: UploadFile = File(...),
    password: str = Form(...),
):
    cxt = SessionService.get_page_context(request)
    if not cxt["is_admin"] or password != IMPORT_PASSWORD:
        context = {**cxt, "message": "كلمة المرور غير صحيحة أو ليس لديك صلاحية"}
        response = templates.TemplateResponse("data/import_data.html", context)
        SessionService.set_cache_headers(response)
        return response
      
    if not dump_file.filename.lower().endswith(('.dump', '.sql')):
        context = {**cxt, "message": "الملف لازم يكون بصيغة .dump أو .sql"}
        response = templates.TemplateResponse("data/import_data.html", context)
        SessionService.set_cache_headers(response)
        return response
       
    file_path = f"/tmp/{dump_file.filename}_{datetime.now().timestamp()}" 
    message = None
    
    try:
        contents = await dump_file.read()
        with open(file_path, "wb") as f:
            f.write(contents)
        
        database_url = get_database_url() 
        if not database_url:
             raise Exception("DATABASE_URL غير معرّف أو متغيرات القاعدة مفقودة.")

        cmd = ["pg_restore", "--verbose", "--clean", "--if-exists", "--no-owner", "--no-acl", 
            "--dbname", database_url, file_path] if file_path.endswith('.dump') \
            else ["psql", database_url, "-f", file_path]

        result = subprocess.run(cmd, capture_output=True, text=True, timeout=600)

        if result.returncode == 0:
            message = "تم استيراد البيانات بنجاح! العائلة كلها موجودة الآن"
        else:
            error_details = result.stderr.replace(chr(10), '<br>')
            message = f"فشل الاستيراد:<br><pre dir='ltr'>{error_details[-1500:]}</pre>"

    except subprocess.TimeoutExpired:
        message = "انتهت المهلة! جرب تقسيم الملف أو المحاولة مرة أخرى."
    except Exception as e:
        message = f"خطأ: {str(e)}"
    finally:
        if os.path.exists(file_path):
            try:
                os.remove(file_path)
            except Exception as clean_e:
                print(f"Failed to remove temp file {file_path}: {clean_e}")
        
    context = {**cxt, "message": message}
    response = templates.TemplateResponse("data/import_data.html", context)
    SessionService.set_cache_headers(response)
    return response
   

@router.post("/export-data")
async def export_data_post(request: Request, password: str = Form(...)):
    export_path = None 
    cxt = SessionService.get_page_context(request)
    
    if not cxt["is_admin"] or password != IMPORT_PASSWORD:
        context = {**cxt, "message": "فشل التصدير: كلمة المرور غير صحيحة أو ليس لديك صلاحية."}
        response = templates.TemplateResponse("data/import_data.html", context)
        SessionService.set_cache_headers(response)
        return response
 
    database_url = get_database_url()
    if not database_url:
        context = {**cxt, "message": "فشل التصدير: DATABASE_URL غير معرّف أو متغيرات القاعدة مفقودة."}
        response = templates.TemplateResponse("data/import_data.html", context)
        SessionService.set_cache_headers(response)
        return response
       
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    filename = f"عائلة_حطية_كاملة_{timestamp}.dump"
    export_path = f"/tmp/{filename}" 
    download_filename = f"full_data_{timestamp}.dump"

    try:
        cmd = [
            "pg_dump", "--verbose", "--no-owner", "--no-acl", "--no-privileges",  
            "--format=custom", "--file", export_path, database_url       
        ]

        result = subprocess.run(cmd, capture_output=True, text=True, timeout=600)

        if result.returncode != 0:
            error_details = result.stderr.replace(chr(10), '<br>')
            print(f"PG_DUMP FAILED: {result.stderr}") 
            cleanup_file(export_path)
            
            context = {**cxt, "message": f"فشل التصدير (Code {result.returncode}):<br><pre dir='ltr'>{error_details[-1500:]}</pre>"}
            response = templates.TemplateResponse("data/import_data.html", context)
            SessionService.set_cache_headers(response)
            return response
         
        if not os.path.exists(export_path) or os.path.getsize(export_path) < 100:
            context = {**cxt, "message": "فشل التصدير: ملف النسخة الاحتياطية فارغ أو مفقود."}
            response = templates.TemplateResponse("data/import_data.html", context)
            SessionService.set_cache_headers(response)
            return response
          
        return FileResponse(
            path=export_path,
            filename=download_filename,
            media_type="application/octet-stream",
            background=BackgroundTask(cleanup_file, export_path)
        )

    except Exception as e:
        cleanup_file(export_path)
        context = {**cxt, "message": f"فشل التصدير (خطأ غير متوقع): {str(e)}"}
        response = templates.TemplateResponse("data/import_data.html", context)
        SessionService.set_cache_headers(response)
        return response

# =====================================================================
# 🩺 التشخيصات وحالة القاعدة
# =====================================================================
@router.get("/api/diagnostics/db-status")
def check_database_health():
    return FamilyService.get_db_status_diagnostics()