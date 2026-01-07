import os
import psycopg2
import psycopg2.extras
from contextlib import contextmanager
from dotenv import load_dotenv

load_dotenv()

@contextmanager
def get_db_context():
    conn = None
    # 💡 التحقق أولاً من وجود DATABASE_URL (الطريقة المُفضلة لـ Render)
    database_url = os.getenv("DATABASE_URL")
    
    try:
        if database_url:
            # استخدام DATABASE_URL مباشرة
            conn = psycopg2.connect(database_url, sslmode="require")
        else:
            # استخدام المتغيرات المنفصلة (للاستخدام المحلي)
            host = os.getenv("DB_HOST")
            dbname = os.getenv("DB_NAME")
            user = os.getenv("DB_USER")
            password = os.getenv("DB_PASSWORD")
            port = os.getenv("DB_PORT", "5432")

            if not all([host, dbname, user, password]):
                raise ValueError("متغيرات قاعدة البيانات مفقودة!")

            conn = psycopg2.connect(
                host=host,
                dbname=dbname,
                user=user,
                password=password,
                port=port,
                # يمكن تعيين sslmode هنا إلى 'prefer' أو 'disable' إذا لم تكن تستخدم SSL محلياً
                sslmode="prefer"
            )
        
        yield conn
    except Exception as e:
        if conn:
            conn.rollback()
        raise
    finally:
        if conn and not conn.closed:
            conn.close()



def init_database():
    with get_db_context() as conn:
        conn.autocommit = True
        cur = conn.cursor()
        try:
            print("🟢 جاري تهيئة مكونات قاعدة البيانات الأساسية...")

            
            # 2. إنشاء جدول المعرض بالهيكلية الجديدة والمكتملة
            cur.execute("""
                CREATE TABLE IF NOT EXISTS gallery (
                    id SERIAL PRIMARY KEY,
                    title VARCHAR(255) NOT NULL,           -- عنوان الصورة
                    image_url TEXT NOT NULL,               -- رابط Cloudinary
                    category VARCHAR(100),                 -- تصنيف الصورة
                    user_id INTEGER REFERENCES users(id) ON DELETE SET NULL, -- ربطها بـ engcof
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
            """)

            # 3. إنشاء فهرس لتسريع جلب الصور حسب التصنيف
            cur.execute("CREATE INDEX IF NOT EXISTS idx_gallery_category ON gallery(category);")
            
            cur.execute(""" 
                    CREATE TABLE IF NOT EXISTS activity_logs (
                    id SERIAL PRIMARY KEY,
                    user_id INTEGER REFERENCES users(id) ON DELETE SET NULL, -- المستخدم الذي قام بالفعل
                    action VARCHAR(100) NOT NULL,                           -- (إضافة خبر، حذف مقال، إلخ)
                    details TEXT,                                           -- تفاصيل العملية
                    timestamp TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP -- توقيت العملية بدقة
                );
            """)
            cur.execute(""" 
                CREATE TABLE IF NOT EXISTS videos (
                    id SERIAL PRIMARY KEY,
                    title VARCHAR(255) NOT NULL,
                    video_url TEXT NOT NULL,
                    thumbnail_url TEXT, -- اختياري: صورة مصغرة للفيديو
                    category VARCHAR(100),
                    user_id INTEGER REFERENCES users(id),
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
            """)           
            #print("✅ تم إنشاء جدول معرض الصور وإنهاء التهيئة بنجاح!")

            cur.execute("""
                CREATE TABLE IF NOT EXISTS library (
                    id SERIAL PRIMARY KEY,
                    title VARCHAR(255) NOT NULL,
                    author VARCHAR(255),
                    category VARCHAR(100) NOT NULL,
                    file_url TEXT NOT NULL,
                    cover_url TEXT,
                    file_size VARCHAR(50),
                    uploader_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
                    views_count INTEGER DEFAULT 0,         -- العمود الجديد لعداد القراءة
                    downloads_count INTEGER DEFAULT 0,     -- العمود الجديد لعداد التحميل
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
            """)

            # 💡 كود إضافي لضمان إضافة الأعمدة إذا كان الجدول موجوداً مسبقاً
            cur.execute("ALTER TABLE library ADD COLUMN IF NOT EXISTS views_count INTEGER DEFAULT 0;")
            cur.execute("ALTER TABLE library ADD COLUMN IF NOT EXISTS downloads_count INTEGER DEFAULT 0;")

            cur.execute("CREATE INDEX IF NOT EXISTS idx_library_category ON library(category);")
            print("✅ تم تحديث هيكلية المكتبة وإضافة العدادات بنجاح!")
           
           
            
            print("✅ تم إنشاء جدول المكتبة وتحديث الهيكلية بنجاح!")
          
        except Exception as e:
            print(f"❌ خطأ أثناء تهيئة قاعدة البيانات: {e}") 
            raise