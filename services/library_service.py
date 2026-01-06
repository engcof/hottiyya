# library_service.py
import os
import shutil
import tempfile
import asyncio
import socket
import httplib2
import json
import fitz  # PyMuPDF
import cloudinary.uploader
import requests
from fastapi import UploadFile
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.http import MediaFileUpload
from googleapiclient.discovery import build
from postgresql import get_db_context
from psycopg2.extras import RealDictCursor

class LibraryService:
    SCOPES = ['https://www.googleapis.com/auth/drive.file']
    TOKEN_FILE = 'token.json'
    GOOGLE_DRIVE_FOLDER_ID = '1nbegMhH8rIQf7mRiNHkv4P5wamwFMbeZ'

    @staticmethod
    def get_drive_service():
        """بناء خدمة مع معالجة متقدمة لقطع الاتصال وDNS"""
        from googleapiclient.discovery import build
        from google.auth.transport.requests import Request
        from google.oauth2.credentials import Credentials
        import google_auth_httplib2
        import httplib2
        import socket

        # 1. حل مشكلة الـ DNS والاتصال على مستوى النظام لهذه العملية
        socket.setdefaulttimeout(600) 
        
        creds = Credentials.from_authorized_user_file(LibraryService.TOKEN_FILE, LibraryService.SCOPES)
        
        if creds.expired and creds.refresh_token:
            creds.refresh(Request())
            with open(LibraryService.TOKEN_FILE, 'w') as token:
                token.write(creds.to_json())
        
        # 2. إعداد محول HTTP مع خاصية إعادة المحاولة عند حدوث Timeout
        # نقوم بضبط disable_ssl_certificate_validation=False لضمان الأمان
        http_transport = httplib2.Http(timeout=600)
        
        # 3. الربط باستخدام مكتبة google_auth_httplib2
        authorized_http = google_auth_httplib2.AuthorizedHttp(creds, http=http_transport)
        
        # 4. بناء الخدمة مع تمكين عدد محاولات إعادة الاتصال (Retries)
        return build('drive', 'v3', http=authorized_http, static_discovery=False)
    @staticmethod
    async def process_and_get_metadata(file: UploadFile):
        """
        المرحلة الأولى (سريعة): 
        تضغط الملف وتستخرج الغلاف وترفع الغلاف فقط.
        تعيد المسار المحلي للملف المضغوط ليتم رفعه في الخلفية.
        """
        temp_input = None
        try:
            with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
                shutil.copyfileobj(file.file, tmp)
                temp_input = tmp.name

            temp_output = temp_input.replace(".pdf", "_compressed.pdf")
            
            # عملية الضغط باستخدام Ghostscript
            gs_command = ["gs", "-sDEVICE=pdfwrite", "-dCompatibilityLevel=1.4", "-dPDFSETTINGS=/ebook", 
                          "-dNOPAUSE", "-dQUIET", "-dBATCH", f"-sOutputFile={temp_output}", temp_input]
            process = await asyncio.create_subprocess_exec(*gs_command)
            await process.wait()

            final_local_path = temp_output if os.path.exists(temp_output) else temp_input
            file_size_mb = os.path.getsize(final_local_path) / (1024 * 1024)
            size_str = f"{file_size_mb:.2f} MB"

            # استخراج الغلاف فوراً
            temp_cover = final_local_path.replace(".pdf", ".jpg")
            doc = fitz.open(final_local_path)
            pix = doc.load_page(0).get_pixmap(matrix=fitz.Matrix(1.5, 1.5))
            pix.save(temp_cover)
            doc.close()
            
            # رفع الغلاف لـ Cloudinary (سريع)
            cover_res = cloudinary.uploader.upload(temp_cover, folder="hottiyya_library/covers")
            
            if os.path.exists(temp_cover): os.remove(temp_cover)
            if temp_input != final_local_path and os.path.exists(temp_input): os.remove(temp_input)

            return final_local_path, cover_res.get("secure_url"), size_str
        except Exception as e:
            if temp_input and os.path.exists(temp_input): os.remove(temp_input)
            raise e

    @staticmethod
    def background_upload(file_path: str, filename: str, book_id: int):
        """
        المرحلة الثانية (خلفية):
        تتعامل مع الرفع المستأنف للملفات الكبيرة وتحديث الحالة عند الفشل.
        """
        try:
            file_size_mb = os.path.getsize(file_path) / (1024 * 1024)
            final_url = None

            if file_size_mb < 10:
                # الرفع لـ Cloudinary للملفات الصغيرة (سريع ومستقر)
                res = cloudinary.uploader.upload(file_path, resource_type="raw", folder="hottiyya_library/books")
                final_url = res['secure_url']
            else:
                # الرفع لـ Google Drive للملفات الكبيرة (نظام الأجزاء)
                service = LibraryService.get_drive_service()
                media = MediaFileUpload(
                    file_path, 
                    mimetype='application/pdf', 
                    resumable=True, # تفعيل استئناف الرفع للملفات الكبيرة
                    chunksize=1024*1024 # رفع الملف كأجزاء (1 ميجا لكل جزء) لتقليل حمل الذاكرة والـ Timeout
                )
                
                # داخل دالة background_upload في LibraryService
                request = service.files().create(
                    body={'name': filename, 'parents': [LibraryService.GOOGLE_DRIVE_FOLDER_ID]},
                    media_body=media, fields='id'
                )
                
                response = None
                retries = 0
                max_retries = 5
                
                while response is None:
                    try:
                        status, response = request.next_chunk()
                        if status:
                            print(f"🔼 كتاب {book_id}: تم رفع {int(status.progress() * 100)}%")
                    except (socket.timeout, httplib2.ServerNotFoundError, ConnectionError) as e:
                        retries += 1
                        if retries > max_retries:
                            raise e
                        print(f"⚠️ انقطع الاتصال... محاولة رقم {retries} لإعادة الاتصال.")
                        asyncio.sleep(5) # انتظر قليلاً قبل إعادة المحاولة

            # تحديث الرابط في قاعدة البيانات عند النجاح
            with get_db_context() as conn:
                with conn.cursor() as cur:
                    cur.execute("UPDATE library SET file_url = %s WHERE id = %s", (final_url, book_id))
                    conn.commit()
            
            print(f"✅ تم اكتمال رفع الكتاب رقم {book_id} بنجاح.")
            
        except Exception as e:
            # في حال الفشل: نقوم بتغيير الحالة في القاعدة لكي لا تظل "pending"
            with get_db_context() as conn:
                with conn.cursor() as cur:
                    cur.execute("UPDATE library SET file_url = %s WHERE id = %s", ('error', book_id))
                    conn.commit()
            print(f"❌ خطأ في الرفع الخلفي للكتاب {book_id}: {e}")
            
        finally:
            # حذف الملف المحلي دائماً لتوفير مساحة السيرفر
            if os.path.exists(file_path): 
                os.remove(file_path)

    @staticmethod
    async def upload_cover(image_file):
        """رفع صورة غلاف يدوية"""
        content = await image_file.read()
        res = cloudinary.uploader.upload(content, folder="hottiyya_library/covers")
        return res.get("secure_url")

    @staticmethod
    async def add_book(title, author, category, file_url, cover_url, uploader_id, file_size):
        """إضافة السجل الأولي لقاعدة البيانات"""
        with get_db_context() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO library (title, author, category, file_url, cover_url, uploader_id, file_size)
                    VALUES (%s, %s, %s, %s, %s, %s, %s) RETURNING id
                """, (title, author, category, file_url, cover_url, uploader_id, file_size))
                book_id = cur.fetchone()[0]
                conn.commit()
                return book_id

    @staticmethod
    def delete_book(book_id):
        """حذف الكتاب نهائياً من القاعدة والسحاب (Cloudinary & Drive)"""
        with get_db_context() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("SELECT title, file_url, cover_url FROM library WHERE id = %s", (book_id,))
                book = cur.fetchone()
                if not book: return None

                # 1. حذف السجل من قاعدة البيانات أولاً
                cur.execute("DELETE FROM library WHERE id = %s", (book_id,))
                conn.commit()

                # 2. حذف ملف الكتاب (PDF)
                if book.get('file_url') and book['file_url'] != 'pending' and book['file_url'] != 'error':
                    try:
                        if "drive.google.com" in book['file_url']:
                            # استخراج الـ ID بدقة من الرابط
                            import urllib.parse as urlparse
                            url_data = urlparse.urlparse(book['file_url'])
                            query = urlparse.parse_qs(url_data.query)
                            file_id = query.get('id', [None])[0]
                            
                            if file_id:
                                service = LibraryService.get_drive_service()
                                service.files().delete(fileId=file_id).execute()
                                print(f"✅ تم حذف الملف من Google Drive: {file_id}")
                        else:
                            # حذف من Cloudinary: يجب إرسال المسار الكامل والمجلد
                            # استخراج اسم الملف بدون الامتداد
                            filename = book['file_url'].split('/')[-1].split('.')[0]
                            public_id = f"hottiyya_library/books/{filename}"
                            cloudinary.uploader.destroy(public_id, resource_type="raw")
                            print(f"✅ تم حذف الملف من Cloudinary: {public_id}")
                    except Exception as e:
                        print(f"⚠️ خطأ أثناء حذف ملف الكتاب: {e}")

                # 3. حذف صورة الغلاف
                if book.get('cover_url'):
                    try:
                        # استخراج اسم ملف الغلاف
                        cover_name = book['cover_url'].split('/')[-1].split('.')[0]
                        cover_public_id = f"hottiyya_library/covers/{cover_name}"
                        cloudinary.uploader.destroy(cover_public_id)
                        print(f"✅ تم حذف الغلاف من Cloudinary: {cover_public_id}")
                    except Exception as e:
                        print(f"⚠️ خطأ أثناء حذف الغلاف: {e}")
                
                return book

    @staticmethod
    def get_books_paginated(category="الكل", page=1, per_page=12, search_query=None):
        offset = (page - 1) * per_page
        with get_db_context() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                base_query = "SELECT * FROM library WHERE 1=1"
                count_query = "SELECT COUNT(*) FROM library WHERE 1=1"
                params = []
                if category and category != "الكل":
                    base_query += " AND category = %s"; count_query += " AND category = %s"
                    params.append(category)
                if search_query:
                    search_pattern = f"%{search_query}%"
                    base_query += " AND (title ILIKE %s OR author ILIKE %s)"
                    count_query += " AND (title ILIKE %s OR author ILIKE %s)"
                    params.extend([search_pattern, search_pattern])
                cur.execute(count_query, params)
                total_count = cur.fetchone()['count']
                cur.execute(base_query + " ORDER BY created_at DESC LIMIT %s OFFSET %s", params + [per_page, offset])
                return cur.fetchall(), (total_count + per_page - 1) // per_page