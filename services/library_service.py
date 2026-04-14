# library_service.py
import os
import re
import time
import json
import fitz  # PyMuPDF
import shutil
import tempfile
import asyncio
import socket
import httplib2
import traceback
import cloudinary.uploader
import google_auth_httplib2
from fastapi import UploadFile
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.http import MediaFileUpload
from googleapiclient.discovery import build
from psycopg2.extras import RealDictCursor
from postgresql import get_db_context

# إجبار النظام على استخدام IPv4 فقط لاتصالات Google API لضمان الاستقرار في Render
orig_getaddrinfo = socket.getaddrinfo
def getaddrinfo_ipv4(host, port, family=0, type=0, proto=0, flags=0):
    return orig_getaddrinfo(host, port, socket.AF_INET, type, proto, flags)
socket.getaddrinfo = getaddrinfo_ipv4

class LibraryService:
    SCOPES = ['https://www.googleapis.com/auth/drive.file']
    TOKEN_FILE = 'token.json'
    GOOGLE_DRIVE_FOLDER_ID = '1nbegMhH8rIQf7mRiNHkv4P5wamwFMbeZ'

    @staticmethod
    def get_drive_service():
        """بناء خدمة مع تعطيل إعادة التوجيه التلقائي واستخدام الملفات السرية في الإنتاج"""
        # Render يضع ملفات الـ Secrets في المسار الجذري للمشروع افتراضياً
        creds = Credentials.from_authorized_user_file(LibraryService.TOKEN_FILE, LibraryService.SCOPES)
        
        if creds.expired and creds.refresh_token:
            creds.refresh(Request())
            with open(LibraryService.TOKEN_FILE, 'w') as token:
                token.write(creds.to_json())
        
        # تحسين إعدادات الاتصال لتجنب أخطاء الشبكة في السحاب
        http_transport = httplib2.Http(timeout=120)
        http_transport.follow_redirects = False 
        
        authorized_http = google_auth_httplib2.AuthorizedHttp(creds, http=http_transport)
        DRIVE_DISCOVERY_URL = 'https://www.googleapis.com/discovery/v1/apis/drive/v3/rest'
        
        return build(
            'drive', 
            'v3', 
            http=authorized_http, 
            discoveryServiceUrl=DRIVE_DISCOVERY_URL,
            static_discovery=False
        )
    
    @staticmethod
    async def process_and_get_metadata(file: UploadFile):
        temp_input = None
        ext = os.path.splitext(file.filename)[1].lower()
        
        try:
            with tempfile.NamedTemporaryFile(delete=False, suffix=ext) as tmp:
                shutil.copyfileobj(file.file, tmp)
                temp_input = tmp.name

            final_local_path = temp_input
            cover_url = None
            
            # إذا كان الملف PDF: نقوم بالضغط واستخراج الغلاف
            if ext == ".pdf":
                temp_output = temp_input.replace(".pdf", "_compressed.pdf")
                gs_command = ["gs", "-sDEVICE=pdfwrite", "-dCompatibilityLevel=1.4", "-dPDFSETTINGS=/ebook", 
                            "-dNOPAUSE", "-dQUIET", "-dBATCH", f"-sOutputFile={temp_output}", temp_input]
                process = await asyncio.create_subprocess_exec(*gs_command)
                await process.wait()

                if os.path.exists(temp_output):
                    final_local_path = temp_output
                    if os.path.exists(temp_input): os.remove(temp_input)

                # استخراج الغلاف
                temp_cover = final_local_path.replace(".pdf", ".jpg")
                doc = fitz.open(final_local_path)
                pix = doc.load_page(0).get_pixmap(matrix=fitz.Matrix(1.5, 1.5))
                pix.save(temp_cover)
                doc.close()
                cover_res = cloudinary.uploader.upload(temp_cover, folder="hottiyya_library/covers")
                cover_url = cover_res.get("secure_url")
                if os.path.exists(temp_cover): os.remove(temp_cover)
            
            else:
                # للملفات الأخرى (Word/PPT): نضع رابط صورة افتراضية حسب النوع
                icons = {
                    '.doc': 'https://example.com/word_icon.png',
                    '.docx': 'https://example.com/word_icon.png',
                    '.ppt': 'https://example.com/ppt_icon.png',
                    '.pptx': 'https://example.com/ppt_icon.png'
                }
                cover_url = icons.get(ext, 'https://example.com/default_book_icon.png')

            file_size_mb = os.path.getsize(final_local_path) / (1024 * 1024)
            return final_local_path, cover_url, f"{file_size_mb:.2f} MB"

        except Exception as e:
            if temp_input and os.path.exists(temp_input): os.remove(temp_input)
            raise e

    @staticmethod
    def background_upload(file_path: str, filename: str, book_id: int):
        """
        المرحلة الثانية (خلفية): دعم PDF, Word, PowerPoint
        تتعامل مع الرفع المستأنف وتحديث الحالة.
        """
        os.environ['no_proxy'] = '*'
        try:
            # 1. تجهيز البيانات الأساسية
            ext = os.path.splitext(filename)[1].lower()
            file_size_mb = os.path.getsize(file_path) / (1024 * 1024)
            final_url = None
            
            # خريطة أنواع الملفات (Mimetypes)
            mimetypes = {
                '.pdf': 'application/pdf',
                '.doc': 'application/msword',
                '.docx': 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
                '.ppt': 'application/vnd.ms-powerpoint',
                '.pptx': 'application/vnd.openxmlformats-officedocument.presentationml.presentation'
            }
            current_mime = mimetypes.get(ext, 'application/octet-stream')
            
            # تنظيف اسم الملف لاستخدامه في الرابط
            clean_filename = re.sub(r'[^\w\s-]', '', filename.split('.')[0]).strip().replace(' ', '_')

            # 2. منطق الرفع بناءً على الحجم
            if file_size_mb < 10:
                # --- الرفع لـ Cloudinary (للملفات الصغيرة) ---
                res = cloudinary.uploader.upload(
                    file_path, 
                    resource_type="raw", 
                    # أضفنا {ext} لضمان احتفاظ الملف بصيغته الأصلية عند التحميل
                    public_id=f"hottiyya_library/books/{clean_filename}{ext}", 
                    folder="hottiyya_library/books",
                    access_control=[{"access_type": "anonymous"}]
                )
                final_url = res['secure_url']
            
            else:
                # --- الرفع لـ Google Drive (للملفات الكبيرة > 10MB) ---
                service = LibraryService.get_drive_service()
                chunk_size = 2 * 1024 * 1024  # 2MB لكل جزء
                
                media = MediaFileUpload(
                    file_path, 
                    mimetype=current_mime, 
                    resumable=True, 
                    chunksize=chunk_size
                )
                
                request = service.files().create(
                    body={'name': filename, 'parents': [LibraryService.GOOGLE_DRIVE_FOLDER_ID]},
                    media_body=media, 
                    fields='id'
                )
                
                response = None
                retries = 0
                max_retries = 15
                
                while response is None:
                    try:
                        status, response = request.next_chunk()
                        if status:
                            print(f"🔼 جاري رفع كتاب {book_id}: {int(status.progress() * 100)}%")
                    except (socket.timeout, httplib2.ServerNotFoundError, Exception) as e:
                        retries += 1
                        if retries > max_retries: raise e
                        time.sleep(min(retries * 5, 30))
                        if retries % 3 == 0: service = LibraryService.get_drive_service()
                
                if response and 'id' in response:
                    file_id = response.get('id')
                    # جعل الملف متاحاً للتحميل العام
                    service.permissions().create(
                        fileId=file_id,
                        body={'type': 'anyone', 'role': 'reader'}
                    ).execute()
                    final_url = f"https://drive.google.com/uc?export=download&id={file_id}"

            # 3. تحديث قاعدة البيانات عند النجاح
            if final_url:
                with get_db_context() as conn:
                    with conn.cursor() as cur:
                        cur.execute("UPDATE library SET file_url = %s WHERE id = %s", (final_url, book_id))
                        conn.commit()
                print(f"✅ تم اكتمال رفع الكتاب رقم {book_id} بنجاح.")
                
        except Exception as e:
            traceback.print_exc()
            with get_db_context() as conn:
                with conn.cursor() as cur:
                    cur.execute("UPDATE library SET file_url = %s WHERE id = %s", ('error', book_id))
                    conn.commit()
            print(f"❌ خطأ في الرفع الخلفي للكتاب {book_id}: {e}")
            
        finally:
            if os.path.exists(file_path): 
                os.remove(file_path)

    @staticmethod
    async def upload_cover(image_file):
        """رفع صورة غلاف يدوية"""
        content = await image_file.read()
        res = cloudinary.uploader.upload(content, folder="hottiyya_library/covers")
        return res.get("secure_url")
    
    @staticmethod
    def get_book_by_id(book_id: int):
        """جلب بيانات كتاب واحد بواسطة معرفه"""
        with get_db_context() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("SELECT * FROM library WHERE id = %s", (book_id,))
                return cur.fetchone()

    @staticmethod
    async def add_book(title, author, category, file_url, cover_url, uploader_id, file_size, allow_download=True):
        """إضافة السجل الأولي لقاعدة البيانات مع تصفير العدادات وحالة التحميل"""
        with get_db_context() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO library (
                        title, author, category, file_url, cover_url, 
                        uploader_id, file_size, views_count, downloads_count, allow_download
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, 0, 0, %s) RETURNING id
                """, (title, author, category, file_url, cover_url, uploader_id, file_size, allow_download))
                book_id = cur.fetchone()[0]
                conn.commit()
                return book_id
            
    @staticmethod
    def update_book(book_id: int, title: str, author: str, category: str, allow_download: bool):
        """تحديث بيانات الكتاب بما في ذلك صلاحية التحميل"""
        try:
            with get_db_context() as conn:
                with conn.cursor() as cur:
                    cur.execute("""
                        UPDATE library 
                        SET title = %s, author = %s, category = %s, allow_download = %s
                        WHERE id = %s
                    """, (title, author, category, allow_download, book_id))
                    conn.commit()
            return True
        except Exception as e:
            print(f"❌ خطأ أثناء تحديث بيانات الكتاب {book_id}: {e}")
            return False
        
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
                            # حذف من Cloudinary للملفات الخام (PDF)
                            # الحل الصحيح: استخراج اسم الملف مع الامتداد للملفات الخام
                            url_parts = book['file_url'].split('/')
                            filename_with_ext = url_parts[-1] # سيأخذ ke3xbbnhjt98uctmzihx.pdf
                            public_id = f"hottiyya_library/books/{filename_with_ext}"
                            
                            # ملاحظة: للملفات الخام يجب تمرير الـ public_id كاملاً مع الامتداد
                            res = cloudinary.uploader.destroy(public_id, resource_type="raw")
                            print(f"✅ نتيجة حذف Cloudinary: {res}")
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
                    base_query += " AND category = %s"
                    count_query += " AND category = %s"
                    params.append(category)
                    
                if search_query:
                    search_pattern = f"%{search_query}%"
                    base_query += " AND (title ILIKE %s OR author ILIKE %s)"
                    count_query += " AND (title ILIKE %s OR author ILIKE %s)"
                    params.extend([search_pattern, search_pattern])
                
                cur.execute(count_query, params)
                total_count = cur.fetchone()['count']
                total_pages = (total_count + per_page - 1) // per_page
                
                cur.execute(base_query + " ORDER BY created_at DESC LIMIT %s OFFSET %s", params + [per_page, offset])
                books = cur.fetchall()

                # --- منطق توليد أرقام الصفحات الذكي ---
                PAGES_TO_SHOW = 7
                page_numbers = set()
                page_numbers.add(1)
                if total_pages > 1:
                    page_numbers.add(total_pages)
                    
                start = max(2, page - PAGES_TO_SHOW // 2)
                end = min(total_pages - 1, page + PAGES_TO_SHOW // 2)
                
                if start <= 2:
                    end = min(total_pages - 1, PAGES_TO_SHOW + 1)
                if end >= total_pages - 1:
                    start = max(2, total_pages - PAGES_TO_SHOW)
                    
                for p in range(start, end + 1):
                    if p > 1 and p < total_pages:
                        page_numbers.add(p)
                
                sorted_pages = sorted(list(page_numbers))
                # ------------------------------------

                return books, total_pages, sorted_pages
    
    @staticmethod
    def cleanup_orphaned_cloudinary_files():
        """دالة فحص وحذف الملفات التي ليس لها سجل في قاعدة البيانات"""
        import cloudinary.api
        import cloudinary.uploader
        
        cleaned_count = 0
        db_files = set()
        db_covers = set()

        # 1. جلب البيانات من القاعدة
        with get_db_context() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("SELECT file_url, cover_url FROM library")
                rows = cur.fetchall()
                for row in rows:
                    if row['file_url']: db_files.add(row['file_url'].strip())
                    if row['cover_url']: db_covers.add(row['cover_url'].strip())

        # 2. تنظيف الكتب (PDF - النوع raw)
        try:
            resources = cloudinary.api.resources(type="upload", resource_type="raw", prefix="hottiyya_library/books")
            for res in resources.get('resources', []):
                if res['secure_url'] not in db_files:
                    cloudinary.uploader.destroy(res['public_id'], resource_type="raw")
                    cleaned_count += 1
                    print(f"🗑️ تم حذف كتاب يتيم: {res['public_id']}")
        except Exception as e:
            print(f"⚠️ خطأ في تنظيف الكتب: {e}")

        # 3. تنظيف الأغلفة (Images - النوع image)
        try:
            covers = cloudinary.api.resources(type="upload", resource_type="image", prefix="hottiyya_library/covers")
            for res in covers.get('resources', []):
                if res['secure_url'] not in db_covers:
                    cloudinary.uploader.destroy(res['public_id'])
                    cleaned_count += 1
                    print(f"🗑️ تم حذف غلاف يتيم: {res['public_id']}")
        except Exception as e:
            print(f"⚠️ خطأ في تنظيف الأغلفة: {e}")
            
        return cleaned_count  

    @staticmethod
    def increment_view(book_id):
        """زيادة عداد القراءة وإعادة بيانات الكتاب (الرابط والعنوان)"""
        with get_db_context() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                # نعدل الاستعلام ليعيد الرابط والعنوان معاً
                cur.execute("""
                    UPDATE library 
                    SET views_count = views_count + 1 
                    WHERE id = %s 
                    RETURNING file_url, title
                """, (book_id,))
                result = cur.fetchone()
                conn.commit()
                return result  # سيعيد dict يحتوي على file_url و title

    @staticmethod
    def increment_download(book_id):
        """زيادة عداد التحميل وإعادة بيانات الملف"""
        with get_db_context() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("UPDATE library SET downloads_count = downloads_count + 1 WHERE id = %s RETURNING file_url, title", (book_id,))
                result = cur.fetchone()
                conn.commit()
                return result if result else None  
            
    @staticmethod
    def cleanup_error_records():
        """حذف السجلات التي تحمل حالة 'error' من قاعدة البيانات لتنظيف الواجهة"""
        try:
            with get_db_context() as conn:
                with conn.cursor() as cur:
                    cur.execute("DELETE FROM library WHERE file_url = 'error'")
                    conn.commit()
            return True
        except Exception as e:
            print(f"❌ فشل تنظيف سجلات الخطأ: {e}")
            return False        
        
    @staticmethod
    def cleanup_stuck_uploads():
        """تنظيف شامل للسجلات العالقة وحذف ملفاتها من السحاب"""
        try:
            with get_db_context() as conn:
                with conn.cursor(cursor_factory=RealDictCursor) as cur:
                    # جلب معرفات الكتب التي علقت في حالة pending لأكثر من ساعتين
                    # أو التي تحمل حالة error (اختياري حسب رغبتك)
                    cur.execute("""
                        SELECT id FROM library 
                        WHERE (file_url = 'pending' AND created_at < NOW() - INTERVAL '2 hours')
                           OR (file_url = 'error')
                    """)
                    stuck_books = cur.fetchall()
            
            if not stuck_books:
                return 0

            cleaned_count = 0
            for book in stuck_books:
                # نستخدم دالة delete_book الحالية لأنها مجهزة تماماً 
                # لحذف الغلاف من Cloudinary وحذف السجل من القاعدة
                LibraryService.delete_book(book['id'])
                cleaned_count += 1
            
            print(f"🧹 تم إجراء تنظيف شامل لـ {cleaned_count} سجلات وملفات يتيمة.")
            return cleaned_count
            
        except Exception as e:
            print(f"❌ خطأ أثناء التنظيف التلقائي: {e}")
            return 0