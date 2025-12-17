# gallery_service.py
import cloudinary
import cloudinary.uploader
from postgresql import get_db_context # لاستخدامه في حفظ الروابط لاحقاً
import os
from dotenv import load_dotenv

load_dotenv()

cloudinary.config( 
    cloud_name = os.getenv("CLOUDINARY_NAME"), 
    api_key = os.getenv("CLOUDINARY_KEY"), 
    api_secret = os.getenv("CLOUDINARY_SECRET"),
    secure = True
)
def upload_to_cloudinary(file_path):
    """دالة لرفع الصورة وإرجاع الرابط المباشر"""
    try:
        result = cloudinary.uploader.upload(file_path, folder="hottiyya_gallery")
        return result.get("secure_url")
    except Exception as e:
        print(f"Cloudinary Error: {e}")
        return None

class GalleryService:
    @staticmethod
    def add_image(title, image_url, user_id, category=None): # أضفنا user_id هنا
        """إضافة صورة جديدة إلى المعرض مع ربطها بالمستخدم"""
        with get_db_context() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO gallery (title, image_url, user_id, category)
                    VALUES (%s, %s, %s, %s)
                    RETURNING id;
                """, (title, image_url, user_id, category))
                image_id = cur.fetchone()[0]
            conn.commit()
            return image_id

    @staticmethod
    def get_all_images(category=None):
        """جلب جميع الصور مع اسم المستخدم الذي قام برفعها"""
        with get_db_context() as conn:
            with conn.cursor() as cur:
                # نستخدم JOIN لجلب اسم المستخدم (username) من جدول users
                query = """
                    SELECT g.*, u.username 
                    FROM gallery g
                    LEFT JOIN users u ON g.user_id = u.id
                """
                if category and category != "الكل":
                    query += " WHERE g.category = %s"
                    query += " ORDER BY g.created_at DESC;"
                    cur.execute(query, (category,))
                else:
                    query += " ORDER BY g.created_at DESC;"
                    cur.execute(query)
                
                columns = [desc[0] for desc in cur.description]
                return [dict(zip(columns, row)) for row in cur.fetchall()]
    @staticmethod
    def delete_image(image_id):
        """حذف صورة من المعرض ومن السحابة معاً"""
        with get_db_context() as conn:
            cur = conn.cursor()
            
            # 1. جلب رابط الصورة قبل حذفها من DB لمعرفة ماذا سنحذف من السحابة
            cur.execute("SELECT image_url FROM gallery WHERE id = %s;", (image_id,))
            row = cur.fetchone()
            
            if row:
                image_url = row[0]
                
                # 2. الحذف من Cloudinary
                public_id = extract_public_id(image_url)
                if public_id:
                    try:
                        import cloudinary.uploader
                        cloudinary.uploader.destroy(public_id)
                    except Exception as e:
                        print(f"Cloudinary Delete Error: {e}")

                # 3. الحذف من قاعدة البيانات
                cur.execute("DELETE FROM gallery WHERE id = %s;", (image_id,))
                conn.commit()
                return True
        return False
        

def extract_public_id(image_url):
    """استخراج المعرف العام للصورة من رابط Cloudinary"""
    try:
        # الرابط يكون بتنسيق: .../upload/v12345/folder/image_name.jpg
        # نحتاج لاستخراج 'folder/image_name'
        parts = image_url.split('/')
        filename_with_ext = parts[-1] # image_name.jpg
        folder = parts[-2] # hottiyya_gallery (اسم المجلد الذي اخترناه)
        public_id = f"{folder}/{filename_with_ext.split('.')[0]}"
        return public_id
    except:
        return None        