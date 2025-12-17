import os
import subprocess
from datetime import datetime
import shutil
from fastapi import APIRouter, Request, Depends, HTTPException, Form, File, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse, FileResponse
from core.templates import templates
from dotenv import load_dotenv
from urllib.parse import quote_plus
from starlette.background import BackgroundTask # **تم إضافة استيراد مهم هنا**

# تحميل متغيرات البيئة من ملف .env
load_dotenv()

# [تعريف كلمة المرور] 
IMPORT_PASSWORD = os.getenv("IMPORT_PASSWORD", "my_secret_key")

router = APIRouter(prefix="/data", tags=["data"])

# ====================== دالة لتنظيف الملف بعد التصدير ======================
def cleanup_file(filepath: str):
    """تحذف الملف المؤقت بعد الانتهاء من إرسال الاستجابة."""
    if os.path.exists(filepath):
        try:
            os.remove(filepath)
            print(f"Cleanup: Removed temporary file {filepath}")
        except Exception as clean_e:
            print(f"Cleanup Failed: Could not remove temporary file {filepath}: {clean_e}")


# ====================== تهيئة سلسلة اتصال قاعدة البيانات ======================
def get_database_url():
    """
    يقوم ببناء سلسلة الاتصال بقاعدة البيانات (DATABASE_URL) 
    إما من المتغير الكامل أو من المتغيرات المنفصلة (DB_HOST, DB_USER, إلخ).
    """
    database_url = os.getenv("DATABASE_URL")
    
    if database_url:
        return database_url
    
    # إذا لم يتم تعريف DATABASE_URL، نقوم ببنائها من المتغيرات المنفصلة
    db_host = os.getenv("DB_HOST")
    db_name = os.getenv("DB_NAME")
    db_user = os.getenv("DB_USER")
    db_password = os.getenv("DB_PASSWORD")
    db_port = os.getenv("DB_PORT", "5432")

    if all([db_host, db_name, db_user, db_password]):
        # ترميز كلمة المرور لمعالجة الأحرف الخاصة مثل @
        encoded_password = quote_plus(db_password)
        
        # بناء السلسلة بالصيغة القياسية لـ PostgreSQL: postgresql://user:password@host:port/dbname
        return f"postgresql://{db_user}:{encoded_password}@{db_host}:{db_port}/{db_name}"
    
    return None

# ====================== استيراد البيانات (GET لعرض النموذج) ======================
@router.get("/import-data", response_class=HTMLResponse)
async def import_page(request: Request):
    user = request.session.get("user")
    if not user or user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="غير مصرح لك بالوصول")
        
    return templates.TemplateResponse("data/import_data.html", {"request": request, "user": user, "message": None})

@router.post("/import-data")
async def import_data(
    request: Request,
    dump_file: UploadFile = File(...),
    password: str = Form(...),
):
    user = request.session.get("user")
    if not user or user.get("role") != "admin" or password != IMPORT_PASSWORD:
        return templates.TemplateResponse("data/import_data.html", {
            "request": request, "user": user,
            "message": "كلمة المرور غير صحيحة أو ليس لديك صلاحية"
        })

    if not dump_file.filename.lower().endswith(('.dump', '.sql')):
        return templates.TemplateResponse("data/import_data.html", {
            "request": request, "user": user,
            "message": "الملف لازم يكون بصيغة .dump أو .sql"
        })

    file_path = f"/tmp/{dump_file.filename}_{datetime.now().timestamp()}" 
    message = None
    
    try:
        # 1. حفظ الملف
        contents = await dump_file.read()
        with open(file_path, "wb") as f:
            f.write(contents)
        
        # 2. بدء الاستيراد
        database_url = get_database_url() 
        if not database_url:
             raise Exception("DATABASE_URL غير معرّف أو متغيرات القاعدة مفقودة.")

        cmd = ["pg_restore", "--verbose", "--clean", "--if-exists", "--no-owner", "--no-acl", 
            "--dbname", database_url, file_path] if file_path.endswith('.dump') \
            else ["psql", database_url, "-f", file_path]

        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=600
        )

        if result.returncode == 0:
            message = "تم استيراد البيانات بنجاح! العائلة كلها موجودة الآن"
        else:
            error_details = result.stderr.replace(chr(10), '<br>')
            message = f"فشل الاستيراد:<br><pre dir='ltr'>{error_details[-1500:]}</pre>"

    except subprocess.TimeoutExpired:
        message = "انتهت المهلة! لكن عادةً بيكون الاستيراد اكتمل جزئيًا. جرب تاني أو قسم الملف."
    except Exception as e:
        message = f"خطأ: {str(e)}"
    finally:
        # **ملاحظة:** تم إبقاء تنظيف ملف الاستيراد في finally لأنه لا يستخدم FileResponse
        if os.path.exists(file_path):
            try:
                os.remove(file_path)
            except Exception as clean_e:
                print(f"Failed to remove temp file {file_path}: {clean_e}")
        
    
    return templates.TemplateResponse("data/import_data.html", {
        "request": request,
        "user": user,
        "message": message
    })

# ====================== تصدير البيانات (POST لمعالجة طلب التصدير) ======================
@router.post("/export-data")
async def export_data_post(request: Request, password: str = Form(...)):
    user = request.session.get("user")
    export_path = None # تعريف مسار التصدير في نطاق الدالة

    # 1. التحقق من الصلاحية
    if not user or user.get("role") != "admin" or password != IMPORT_PASSWORD:
        return templates.TemplateResponse("data/import_data.html", {
            "request": request, "user": user,
            "message": "فشل التصدير: كلمة المرور غير صحيحة أو ليس لديك صلاحية."
        })

    # 2. بناء سلسلة الاتصال
    database_url = get_database_url()
    if not database_url:
        return templates.TemplateResponse("data/import_data.html", {
            "request": request, "user": user,
            "message": "فشل التصدير: DATABASE_URL غير معرّف أو متغيرات القاعدة مفقودة."
        })

    # 3. تحديد مسار الملف
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    filename = f"عائلة_حطية_كاملة_{timestamp}.dump"
    export_path = f"/tmp/{filename}" 
    download_filename = f"كاملة_الداتابيز{timestamp}.dump"

    try:
        # 4. تشغيل pg_dump
        cmd = [
            "pg_dump",
            "--verbose",
            "--no-owner",
            "--no-acl",
            "--format=custom",          
            "--file", export_path,      
            database_url
        ]

        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=600
        )

        # 5. التحقق من فشل العملية (Return Code)
        if result.returncode != 0:
            error_details = result.stderr.replace(chr(10), '<br>')
            # نطبع الخطأ في اللوغ لسهولة التشخيص
            print(f"PG_DUMP FAILED: {result.stderr}") 
            
            # محاولة تنظيف الملف في حالة الفشل الفوري
            cleanup_file(export_path)

            return templates.TemplateResponse("data/import_data.html", {
                "request": request, "user": user,
                "message": f"فشل التصدير (Code {result.returncode}):<br><pre dir='ltr'>{error_details[-1500:]}</pre>"
            })

        # 6. التحقق من وجود الملف فعلاً بعد انتهاء العملية
        if not os.path.exists(export_path) or os.path.getsize(export_path) < 100:
            print(f"PG_DUMP returned 0 but file {export_path} is missing or too small.")
            
            # لا حاجة لـ cleanup_file هنا، الملف غير موجود
            
            return templates.TemplateResponse("data/import_data.html", {
                "request": request, "user": user,
                "message": "فشل التصدير: pg_dump لم يقم بإنشاء ملف النسخة الاحتياطية بشكل صحيح أو الملف صغير جداً."
            })

        # 7. إرجاع الملف وتعيين مهمة حذف في الخلفية (الحل الجذري)
        response = FileResponse(
            path=export_path,
            filename=download_filename,
            media_type="application/octet-stream",
            background=BackgroundTask(cleanup_file, export_path) # **هذا هو الحل**
        )
        return response

    except Exception as e:
        # في حالة حدوث خطأ غير متوقع
        cleanup_file(export_path) # تنظيف الملف في حالة فشل غير متوقع
        return templates.TemplateResponse("data/import_data.html", {
            "request": request, "user": user,
            "message": f"فشل التصدير (خطأ غير متوقع): {str(e)}"
        })
    finally:
        # **ملاحظة هامة**: تم حذف منطق الحذف من هنا
        # عملية الحذف تتم الآن في الخلفية بواسطة BackgroundTask فقط
        pass