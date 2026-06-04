# gallery_service.py
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

def upload_to_cloudinary(file_stream):
    """دالة لرفع الصورة باستخدام تدفق البيانات مباشرة وبشكل آمن"""
    try:
        file_stream.seek(0)
        file_content = file_stream.read()
        
        result = cloudinary.uploader.upload(
            file_content, 
            folder="hottiyya_gallery",
            resource_type="image" # إجبار السحابة على معاملتها كصورة لحمايتها
        )
        return result.get("secure_url")
    except Exception as e:
        print(f"Cloudinary Error: {e}")
        return None

def extract_public_id(image_url):
    """استخراج المعرف العام للصورة من رابط Cloudinary بأمان عالي"""
    try:
        if not image_url:
            return None
        parts = image_url.split('/')
        filename_with_ext = parts[-1]
        # تلافي الأخطاء في روابط المجلدات
        if len(parts) >= 2:
            folder = parts[-2]
            return f"{folder}/{filename_with_ext.split('.')[0]}"
        return filename_with_ext.split('.')[0]
    except Exception:
        return None  

class GalleryService:
    @staticmethod
    def add_image(title, image_url, user_id, category=None):
        """إضافة صورة جديدة إلى المعرض وضمان تسجيل الـ Transaction"""
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
    def get_all_images(category=None, page=1, per_page=12):
        """جلب الصور مع ترقيم الصفحات وبناء معزول للاستعلامات لحماية محرك الـ SQL"""
        offset = (page - 1) * per_page
        
        # تحضير الهياكل الأساسية المعزولة
        base_count = "SELECT COUNT(*) FROM gallery"
        base_select = """
            SELECT g.*, u.username 
            FROM gallery g
            LEFT JOIN users u ON g.user_id = u.id
        """
        
        where_clause = ""
        count_params = []
        select_params = []
        
        if category and category != "الكل" and category != "None":
            where_clause = " WHERE g.category = %s " if "g." in base_select else " WHERE category = %s "
            # تعديل متوافق مع جملة الـ Count
            count_where = " WHERE category = %s "
            count_params.append(category)
            select_params.append(category)
        else:
            count_where = ""

        with get_db_context() as conn:
            with conn.cursor() as cur:
                # 1. جلب إجمالي العدد
                cur.execute(f"{base_count}{count_where}", tuple(count_params))
                total_images = cur.fetchone()[0]

                # 2. جلب البيانات بترتيب منظم وآمن
                full_query = f"{base_select}{where_clause.replace('category', 'g.category') if where_clause else ''} ORDER BY g.created_at DESC LIMIT %s OFFSET %s;"
                select_params.extend([per_page, offset])
                
                cur.execute(full_query, tuple(select_params))
                
                columns = [desc[0] for desc in cur.description]
                images = [dict(zip(columns, row)) for row in cur.fetchall()]
                
                return images, total_images
            
    @staticmethod
    def get_categories():
        """جلب قائمة التصنيفات الفريدة التي تحتوي على صور"""
        with get_db_context() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT DISTINCT category 
                    FROM gallery 
                    WHERE category IS NOT NULL AND category != '' AND category != 'None'
                    ORDER BY category ASC;
                """)
                return [row[0] for row in cur.fetchall()]

    @staticmethod
    def delete_image(image_id):
        """حذف صورة من المعرض ومن السحابة معاً بشكل متزامن وآمن"""
        with get_db_context() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT image_url FROM gallery WHERE id = %s;", (image_id,))
                row = cur.fetchone()
                
                if row:
                    image_url = row[0]
                    
                    # الحذف من Cloudinary أولاً
                    public_id = extract_public_id(image_url)
                    if public_id:
                        try:
                            cloudinary.uploader.destroy(public_id)
                        except Exception as e:
                            print(f"Cloudinary Delete Error: {e}")

                    # الحذف النهائي من قاعدة البيانات
                    cur.execute("DELETE FROM gallery WHERE id = %s;", (image_id,))
                    conn.commit()
                    return True
        return False