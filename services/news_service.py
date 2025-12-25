# news_service.py
import cloudinary.uploader
from postgresql import get_db_context
from psycopg2.extras import RealDictCursor


class NewsService:
    @staticmethod
    def upload_news_media(file, news_id):
        """رفع صورة أو فيديو قصير إلى سحابة Cloudinary"""
        try:
            # اكتشاف نوع الملف تلقائياً (صورة أو فيديو)
            result = cloudinary.uploader.upload(
                file,
                folder="hottiyya_news",
                public_id=f"news_{news_id}",
                overwrite=True,
                resource_type="auto"  # auto تسمح برفع الصور والفيديوهات معاً
            )
            return result.get("secure_url")
        except Exception as e:
            print(f"❌ Error uploading news media: {e}")
            return None

    
    @staticmethod
    def get_all_news():
        """جلب كافة الأخبار مرتبة من الأحدث للأقدم"""
        with get_db_context() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("SELECT * FROM news ORDER BY created_at DESC")
                return cur.fetchall()

    @staticmethod
    def get_news_by_id(news_id):
        """جلب خبر محدد بواسطة المعرف"""
        with get_db_context() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("SELECT * FROM news WHERE id = %s", (news_id,))
                return cur.fetchone()
    
    @staticmethod
    def create_news(title, content, author, media_file=None):
        with get_db_context() as conn:
            with conn.cursor() as cur:
                # 1. حفظ الخبر أولاً
                cur.execute("""
                    INSERT INTO news (title, content, author)
                    VALUES (%s, %s, %s) RETURNING id
                """, (title, content, author))
                news_id = cur.fetchone()[0]
                
                # 2. رفع الوسائط (صورة/فيديو) إذا وجدت
                if media_file:
                    media_url = NewsService.upload_news_media(media_file, news_id)
                    if media_url:
                        cur.execute("UPDATE news SET image_url = %s WHERE id = %s", (media_url, news_id))
                
                conn.commit()
                return news_id
            
    @staticmethod
    def update_news(news_id, title, content, author, media_file=None):
        with get_db_context() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("SELECT image_url FROM news WHERE id = %s", (news_id,))
                old_news = cur.fetchone()
                if not old_news:
                    return False

                image_url = old_news['image_url']

                if media_file:
                    # ✅ الإصلاح: تمرير news_id للدالة
                    image_url = NewsService.upload_news_media(media_file, news_id)

                cur.execute("""
                    UPDATE news 
                    SET title=%s, content=%s, author=%s, image_url=%s
                    WHERE id=%s
                """, (title, content, author, image_url, news_id))
                conn.commit()
                return True
    
    @staticmethod
    def delete_news(news_id):
        """حذف الخبر وملفه المرفق من السحابة والقاعدة بشكل نهائي"""
        with get_db_context() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                # 1. جلب رابط الملف قبل حذف السجل
                cur.execute("SELECT image_url FROM news WHERE id = %s", (news_id,))
                item = cur.fetchone()
                
                if not item:
                    return False

                # 2. حذف الملف من Cloudinary
                if item['image_url'] and "cloudinary.com" in item['image_url']:
                    try:
                        # استخراج الـ public_id الصحيح مع اسم المجلد
                        # الرابط عادة يحتوي على /hottiyya_news/filename
                        url_parts = item['image_url'].split('/')
                        filename = url_parts[-1].split('.')[0] # اسم الملف بدون امتداد
                        
                        # التعديل الجوهري: إضافة اسم المجلد للمسار
                        full_public_id = f"hottiyya_news/{filename}"
                        
                        # تحديد نوع الملف تلقائياً (صورة أو فيديو)
                        resource_type = "video" if item['image_url'].lower().endswith(('.mp4', '.mov', '.avi')) else "image"
                        
                        cloudinary.uploader.destroy(full_public_id, resource_type=resource_type)
                        print(f"✅ تم حذف الملف من السحابة: {full_public_id}")
                    except Exception as e:
                        print(f"⚠️ فشل حذف ملف السحابة: {e}")

                # 3. حذف الخبر من قاعدة البيانات
                cur.execute("DELETE FROM news WHERE id = %s", (news_id,))
                conn.commit()
                return True