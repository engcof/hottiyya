# news_service.py
import cloudinary.uploader
from postgresql import get_db_context
from psycopg2.extras import RealDictCursor

class NewsService:
    @staticmethod
    def upload_news_media(file, news_id):
        """رفع صورة أو فيديو قصير إلى سحابة Cloudinary"""
        try:
            result = cloudinary.uploader.upload(
                file,
                folder="hottiyya_news",
                public_id=f"news_{news_id}",
                overwrite=True,
                resource_type="auto"  # يسمح برفع الصور والفيديوهات معاً تلقائياً
            )
            return result.get("secure_url")
        except Exception as e:
            print(f"❌ Error uploading news media: {e}")
            return None

    @staticmethod
    def get_all_news(page: int = 1, limit: int = 10, q: str = None):
        """جلب الأخبار مع الترقيم والبحث بطريقة آمنة ومطهرة تماماً"""
        offset = (page - 1) * limit
        
        # بناء شرط البحث بأسلوب الحقل الموحد المعزول
        params = []
        if q:
            where_clause = "WHERE title ILIKE %s OR content ILIKE %s"
            search_term = f"%{q}%"
            params = [search_term, search_term]
        else:
            where_clause = ""
            
        with get_db_context() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                # الاستعلام مبني بأمان، ويتم التحكم بالـ where_clause برمجياً ومحلياً فقط
                query = f"""
                    SELECT * FROM news {where_clause} 
                    ORDER BY created_at DESC LIMIT %s OFFSET %s
                """
                cur.execute(query, (*params, limit, offset))
                news = cur.fetchall()
                
                count_query = f"SELECT COUNT(*) as total FROM news {where_clause}"
                cur.execute(count_query, params)
                total = cur.fetchone()['total']
                
        return news, total
    
    @staticmethod
    def get_news_by_id(news_id):
        """جلب خبر محدد بواسطة المعرف"""
        with get_db_context() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("SELECT * FROM news WHERE id = %s", (news_id,))
                return cur.fetchone()
    
    @staticmethod
    def create_news(title, content, author, media_file=None):
        """إنشاء خبر مع حماية السحابة من الملفات اليتيمة في حال فشل قاعدة البيانات"""
        news_id = None
        media_url = None
        
        try:
            with get_db_context() as conn:
                with conn.cursor() as cur:
                    # 1. حفظ الخبر أولاً في قاعدة البيانات لجلب المعرف الفريد
                    cur.execute("""
                        INSERT INTO news (title, content, author)
                        VALUES (%s, %s, %s) RETURNING id
                    """, (title, content, author))
                    news_id = cur.fetchone()[0]
                    
                    # 2. رفع الوسائط إذا وجدت
                    if media_file:
                        media_url = NewsService.upload_news_media(media_file, news_id)
                        if media_url:
                            cur.execute("UPDATE news SET image_url = %s WHERE id = %s", (media_url, news_id))
                    
                    conn.commit()
                    return news_id
                    
        except Exception as db_error:
            # 🛡️ خط الدفاع للحماية من الملفات اليتيمة: إذا تم الرفع للسحابة ثم انهارت المعاملة في الداتابيز، نقوم بمسح الملف فوراً لتوفر المساحة
            if media_url and news_id:
                try:
                    res_type = "video" if "/video/" in media_url.lower() or media_url.lower().endswith(('.mp4', '.mov', '.avi')) else "image"
                    cloudinary.uploader.destroy(f"hottiyya_news/news_{news_id}", resource_type=res_type)
                    print(f"🧹 تم تنظيف السحابة من الملف اليتيم لـ news_{news_id} بسبب فشل حفظ الداتابيز.")
                except Exception as cloud_err:
                    print(f"⚠️ فشل تنظيف السحابة التلقائي: {cloud_err}")
            
            # إعادة إطلاق الاستثناء ليتعامل معه الـ Router بشكل صحيح ويظهر الـ 500 للمستخدم
            raise db_error
            
    @staticmethod
    def update_news(news_id, title, content, author, media_file=None):
        """تحديث الخبر مع التحديد الدقيق والذكي لنوع الملف المرفوع سابقاً"""
        with get_db_context() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                # 1. جلب بيانات الخبر الحالية
                cur.execute("SELECT image_url FROM news WHERE id = %s", (news_id,))
                old_item = cur.fetchone()
                if not old_item:
                    return False

                image_url = old_item['image_url']

                # 2. إذا رفع المستخدم ملفاً جديداً
                if media_file:
                    # حذف الملف القديم من Cloudinary بشكل آمن ودقيق
                    if image_url and "cloudinary.com" in image_url:
                        try:
                            url_parts = image_url.split('/')
                            filename = url_parts[-1].split('.')[0]
                            full_public_id = f"hottiyya_news/{filename}"
                            
                            # الفحص الذكي عبر الامتداد أو محتوى مسار الرابط (أكثر أماناً)
                            is_video = "/video/" in image_url.lower() or image_url.lower().endswith(('.mp4', '.mov', '.avi', '.webm'))
                            res_type = "video" if is_video else "image"
                            
                            cloudinary.uploader.destroy(full_public_id, resource_type=res_type)
                        except Exception as e:
                            print(f"⚠️ تنبيه: تعذر حذف الملف القديم من السحابة: {e}")

                    # رفع الملف الجديد والحصول على الرابط
                    image_url = NewsService.upload_news_media(media_file, news_id)

                # 3. تحديث البيانات في قاعدة البيانات
                cur.execute("""
                    UPDATE news 
                    SET title=%s, content=%s, author=%s, image_url=%s
                    WHERE id=%s
                """, (title, content, author, image_url, news_id))
                conn.commit()
                return True

    @staticmethod
    def delete_news(news_id):
        """حذف الخبر وملفه المرفق نهائياً وتجنب بقاء أي مخلفات سحابية ثقيلة"""
        with get_db_context() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                # 1. جلب رابط الملف قبل حذف السجل لضمان الحصول على البيانات
                cur.execute("SELECT image_url FROM news WHERE id = %s", (news_id,))
                item = cur.fetchone()
                
                if not item:
                    return False

                # 2. حذف الملف من Cloudinary أولاً
                if item['image_url'] and "cloudinary.com" in item['image_url']:
                    try:
                        img_path = item['image_url']
                        url_parts = img_path.split('/')
                        filename = url_parts[-1].split('.')[0]
                        full_public_id = f"hottiyya_news/{filename}"
                        
                        is_video = "/video/" in img_path.lower() or img_path.lower().endswith(('.mp4', '.mov', '.avi', '.webm'))
                        resource_type = "video" if is_video else "image"
                        
                        cloudinary.uploader.destroy(full_public_id, resource_type=resource_type)
                        print(f"✅ تم حذف ملف السحابة بنجاح: {full_public_id}")
                    except Exception as e:
                        print(f"⚠️ فشل حذف ملف السحابة: {e}")

                # 3. حذف الخبر من قاعدة البيانات بعد تصفية السحابة
                cur.execute("DELETE FROM news WHERE id = %s", (news_id,))
                conn.commit()
                return True