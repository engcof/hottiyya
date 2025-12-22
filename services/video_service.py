# video_service.py
import cloudinary
import cloudinary.uploader
from postgresql import get_db_context
import os
from dotenv import load_dotenv

load_dotenv()

cloudinary.config( 
    cloud_name = os.getenv("CLOUDINARY_NAME"), 
    api_key = os.getenv("CLOUDINARY_KEY"), 
    api_secret = os.getenv("CLOUDINARY_SECRET"),
    secure = True
)
def upload_video_to_cloudinary(file):
    try:
        # لاحظ استخدام resource_type="video" وهو ضروري جداً هنا
        result = cloudinary.uploader.upload(
            file, 
            folder="hottiyya_videos",
            resource_type="video",
            chunk_size=6000000  # يدعم رفع الملفات الكبيرة تدريجياً
        )
        return result.get("secure_url")
    except Exception as e:
        print(f"Cloudinary Video Error: {e}")
        return None

class VideoService:
    @staticmethod
    def add_video_to_db(title, video_url, category, user_id, thumbnail_url=None):
        """
        تخزين بيانات الفيديو في قاعدة البيانات بعد رفعه بنجاح
        """
        try:
            with get_db_context() as conn:
                cur = conn.cursor()
                query = """
                    INSERT INTO videos (title, video_url, category, user_id, thumbnail_url)
                    VALUES (%s, %s, %s, %s, %s)
                    RETURNING id;
                """
                cur.execute(query, (title, video_url, category, user_id, thumbnail_url))
                video_id = cur.fetchone()[0]
                conn.commit()
                print(f"✅ تم حفظ الفيديو في قاعدة البيانات بنجاح: ID {video_id}")
                return video_id
        except Exception as e:
            print(f"❌ خطأ في حفظ بيانات الفيديو: {e}")
            return None
    @staticmethod
    def get_all_videos(category=None, page=1, per_page=18):
        try:
            offset = (page - 1) * per_page
            with get_db_context() as conn:
                cur = conn.cursor()
                
                # استعلام لجلب الفيديوهات مع الترقيم
                if category and category != "الكل":
                    query = "SELECT * FROM videos WHERE category = %s ORDER BY created_at DESC LIMIT %s OFFSET %s;"
                    cur.execute(query, (category, per_page, offset))
                else:
                    query = "SELECT * FROM videos ORDER BY created_at DESC LIMIT %s OFFSET %s;"
                    cur.execute(query, (per_page, offset))
                
                columns = [desc[0] for desc in cur.description]
                videos = [dict(zip(columns, row)) for row in cur.fetchall()]

                # جلب العدد الإجمالي للفيديوهات لحساب عدد الصفحات
                count_query = "SELECT COUNT(*) FROM videos" + (" WHERE category = %s" if category and category != "الكل" else "")
                cur.execute(count_query, (category,) if category and category != "الكل" else ())
                total_videos = cur.fetchone()[0]

                return videos, total_videos
        except Exception as e:
            print(f"❌ خطأ في جلب الفيديوهات مع الترقيم: {e}")
            return [], 0
    
    @staticmethod
    def delete_video_from_cloudinary(public_id):
        try:
            # التحقق من أن الـ public_id لا يحتوي على امتداد الملف (مثل .mp4)
            clean_public_id = public_id.split('.')[0]
            result = cloudinary.uploader.destroy(clean_public_id, resource_type="video")
            print(f"Cloudinary Delete Result: {result}") # للتأكد في الكونسول
            return result.get("result") == "ok"
        except Exception as e:
            print(f"Error deleting from Cloudinary: {e}")
            return False
        
    @staticmethod
    def delete_video_from_db(video_id):
        try:
            with get_db_context() as conn:
                cur = conn.cursor()
                # التأكد من تحويل video_id إلى int صريح قبل الإرسال للاستعلام
                query = "DELETE FROM videos WHERE id = %s RETURNING id;"
                cur.execute(query, (int(video_id),))
                
                # التحقق مما إذا كان هناك صف تم حذفه فعلاً
                deleted_row = cur.fetchone()
                conn.commit()
                
                if deleted_row:
                    print(f"✅ تم حذف الفيديو من قاعدة البيانات بنجاح: {video_id}")
                    return True
                else:
                    print(f"⚠️ لم يتم العثور على سجل للفيديو رقم {video_id} في القاعدة")
                    return False
        except Exception as e:
            print(f"❌ خطأ في حذف الفيديو من قاعدة البيانات: {e}")
            return False