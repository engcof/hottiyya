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

def upload_video_to_cloudinary(file_stream):
    """رفع الفيديو باستخدام تدفق البيانات المباشر لمنع استهلاك بايتات الذاكرة العشوائية"""
    try:
        result = cloudinary.uploader.upload(
            file_stream, 
            folder="hottiyya_videos",
            resource_type="video",
            chunk_size=6000000,
            timeout=120
        )
        return result.get("secure_url")
    except Exception as e:
        print(f"Cloudinary Video Error: {e}")
        return None

class VideoService:
    @staticmethod
    def add_video_to_db(title, video_url, category, user_id, thumbnail_url=None):
        try:
            with get_db_context() as conn:
                with conn.cursor() as cur:
                    query = """
                        INSERT INTO videos (title, video_url, category, user_id, thumbnail_url)
                        VALUES (%s, %s, %s, %s, %s)
                        RETURNING id;
                    """
                    cur.execute(query, (title, video_url, category, user_id, thumbnail_url))
                    video_id = cur.fetchone()[0]
                conn.commit()
                return video_id
        except Exception as e:
            print(f"❌ خطأ في حفظ بيانات الفيديو: {e}")
            return None

    @staticmethod
    def get_video_by_id(video_id):
        """دالة هندسية مضافة لجلب فيديو فردي بكفاءة عالية وبناء معزول"""
        try:
            with get_db_context() as conn:
                with conn.cursor() as cur:
                    cur.execute("SELECT * FROM videos WHERE id = %s;", (int(video_id),))
                    row = cur.fetchone()
                    if row:
                        columns = [desc[0] for desc in cur.description]
                        return dict(zip(columns, row))
            return None
        except Exception as e:
            print(f"❌ خطأ في استعلام جلب الفيديو بالمعرف: {e}")
            return None

    @staticmethod
    def get_all_videos(category=None, page=1, per_page=18):
        try:
            offset = (page - 1) * per_page
            with get_db_context() as conn:
                with conn.cursor() as cur:
                    
                    if category and category != "الكل" and category != "None":
                        query = "SELECT * FROM videos WHERE category = %s ORDER BY created_at DESC LIMIT %s OFFSET %s;"
                        cur.execute(query, (category, per_page, offset))
                    else:
                        query = "SELECT * FROM videos ORDER BY created_at DESC LIMIT %s OFFSET %s;"
                        cur.execute(query, (per_page, offset))
                    
                    columns = [desc[0] for desc in cur.description]
                    videos = [dict(zip(columns, row)) for row in cur.fetchall()]

                    count_query = "SELECT COUNT(*) FROM videos" + (" WHERE category = %s" if category and category != "الكل" and category != "None" else "")
                    cur.execute(count_query, (category,) if category and category != "الكل" and category != "None" else ())
                    total_videos = cur.fetchone()[0]

                    return videos, total_videos
        except Exception as e:
            print(f"❌ خطأ في جلب الفيديوهات: {e}")
            return [], 0
    
    @staticmethod
    def delete_video_from_cloudinary(public_id):
        try:
            clean_public_id = public_id.split('.')[0]
            result = cloudinary.uploader.destroy(clean_public_id, resource_type="video")
            return result.get("result") == "ok"
        except Exception as e:
            print(f"Error deleting from Cloudinary: {e}")
            return False
        
    @staticmethod
    def delete_video_from_db(video_id):
        try:
            with get_db_context() as conn:
                with conn.cursor() as cur:
                    query = "DELETE FROM videos WHERE id = %s RETURNING id;"
                    cur.execute(query, (int(video_id),))
                    deleted_row = cur.fetchone()
                conn.commit()
                return deleted_row is not None
        except Exception as e:
            print(f"❌ خطأ في حذف الفيديو من قاعدة البيانات: {e}")
            return False