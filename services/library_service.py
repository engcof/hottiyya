# library_service.py
import io
import os
import subprocess
import cloudinary
from pypdf import PdfReader, PdfWriter
import cloudinary.uploader
from postgresql import get_db_context
from psycopg2.extras import RealDictCursor

class LibraryService:  
    @staticmethod
    async def upload_file(file, folder="hottiyya_library"):
        try:
            await file.seek(0)
            file_content = await file.read()
            file_size = len(file_content)
            # هذا المتغير سنحتاجه لإرجاع الحجم النهائي لقاعدة البيانات
            final_size_formatted = f"{round(file_size / (1024 * 1024), 2)} MB"
            
            MAX_SIZE = 10 * 1024 * 1024 

            if file_size > MAX_SIZE and file.filename.lower().endswith('.pdf'):
                print(f"⚠️ الملف كبير ({final_size_formatted}). جاري الضغط...")
                
                temp_input = f"temp_in_{file.filename}" # أضفنا اسم الملف لضمان عدم التداخل
                temp_output = f"temp_out_{file.filename}"
                
                with open(temp_input, "wb") as f:
                    f.write(file_content)

                gs_command = [
                    "gs", "-sDEVICE=pdfwrite", "-dCompatibilityLevel=1.4",
                    "-dPDFSETTINGS=/ebook", "-dNOPAUSE", "-dQUIET", "-dBATCH",
                    f"-sOutputFile={temp_output}", temp_input
                ]
                
                subprocess.run(gs_command, check=True)

                if os.path.exists(temp_output):
                    with open(temp_output, "rb") as f:
                        file_content = f.read()
                    
                    # تحديث الحجم المسجل بعد الضغط
                    final_size_formatted = f"{round(len(file_content) / (1024 * 1024), 2)} MB"
                    print(f"✅ تم الضغط بنجاح. الحجم الجديد: {final_size_formatted}")

                    # تنظيف الملفات المؤقتة فوراً بعد القراءة
                    os.remove(temp_input)
                    os.remove(temp_output)

            # الرفع إلى Cloudinary
            final_stream = io.BytesIO(file_content)
            upload_result = cloudinary.uploader.upload_large(
                final_stream,
                folder=folder,
                resource_type="raw",
                use_filename=True,
                unique_filename=True,
                chunk_size=5242880
            )
            
            secure_url = upload_result.get("secure_url")
            # نرجح إرجاع الـ URL والحجم معاً لضمان تسجيل الحجم الصحيح في القاعدة
            return secure_url, final_size_formatted

        except Exception as e:
            print(f"❌ خطأ في نظام الرفع/الضغط: {e}")
            # تنظيف في حالة الفشل لتجنب امتلاء قرص السيرفر
            for f in [temp_input, temp_output]:
                if 'f' in locals() and os.path.exists(f): os.remove(f)
            return None, None

    @staticmethod
    async def upload_cover(image_file):
        """رفع صورة غلاف الكتاب"""
        try:
            content = await image_file.read()
            upload_result = cloudinary.uploader.upload(
                content,
                folder="hottiyya_library/covers",
                resource_type="image"
            )
            return upload_result.get("secure_url")
        except Exception as e:
            print(f"❌ خطأ في رفع الغلاف: {e}")
            return None

    @staticmethod
    async def add_book(title, author, category, file_url, cover_url, uploader_id, file_size):
        """إضافة بيانات الكتاب إلى قاعدة البيانات"""
        with get_db_context() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO library (title, author, category, file_url, cover_url, uploader_id, file_size)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                    RETURNING id
                """, (title, author, category, file_url, cover_url, uploader_id, file_size))
                book_id = cur.fetchone()[0]
                conn.commit()
                return book_id
    
    @staticmethod
    def get_books_paginated(category="الكل", page=1, per_page=12, search_query=None):
        """جلب الكتب مع دعم البحث، الترقيم، والتصنيفات"""
        offset = (page - 1) * per_page
        
        with get_db_context() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                # بناء جملة الاستعلام الأساسية
                base_query = "SELECT * FROM library WHERE 1=1"
                count_query = "SELECT COUNT(*) FROM library WHERE 1=1"
                params = []

                # إضافة فلتر التصنيف
                if category and category != "الكل":
                    base_query += " AND category = %s"
                    count_query += " AND category = %s"
                    params.append(category)

                # إضافة فلتر البحث (البحث في العنوان أو المؤلف)
                if search_query:
                    search_pattern = f"%{search_query}%"
                    base_query += " AND (title ILIKE %s OR author ILIKE %s)"
                    count_query += " AND (title ILIKE %s OR author ILIKE %s)"
                    params.extend([search_pattern, search_pattern])

                # جلب العدد الإجمالي
                cur.execute(count_query, params)
                total_count = cur.fetchone()['count']
                
                # جلب البيانات مع الترتيب والترقيم
                final_query = base_query + " ORDER BY created_at DESC LIMIT %s OFFSET %s"
                final_params = params + [per_page, offset]
                
                cur.execute(final_query, final_params)
                books = cur.fetchall()
                
                total_pages = (total_count + per_page - 1) // per_page
                return books, total_pages

    @staticmethod
    def delete_book(book_id):
        """حذف الكتاب نهائياً من القاعدة والسحابة"""
        with get_db_context() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                # جلب الروابط قبل الحذف لمسحها من Cloudinary
                cur.execute("SELECT title, file_url, cover_url FROM library WHERE id = %s", (book_id,))
                book = cur.fetchone()
                
                if not book:
                    return None

                # حذف الملف الأساسي (Raw)
                if book['file_url']:
                    try:
                        # استخراج الـ public_id للملفات الخام (يحتاج معالجة خاصة أحياناً)
                        file_public_id = "hottiyya_library/" + book['file_url'].split('/')[-1]
                        cloudinary.uploader.destroy(file_public_id, resource_type="raw")
                    except: pass

                # حذف الغلاف (Image)
                if book['cover_url']:
                    try:
                        cover_id = "hottiyya_library/covers/" + book['cover_url'].split('/')[-1].split('.')[0]
                        cloudinary.uploader.destroy(cover_id)
                    except: pass

                # الحذف من القاعدة
                cur.execute("DELETE FROM library WHERE id = %s", (book_id,))
                conn.commit()
                return book # نعيد بيانات الكتاب لاستخدامها في سجل النشاطات