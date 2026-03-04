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
            cur.execute("ALTER TABLE library ADD COLUMN IF NOT EXISTS allow_download BOOLEAN DEFAULT TRUE;")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_library_category ON library(category);")
            
           
            # =======================================================
            # 5. إنشاء جداول ودوال البحث (ضروري لعمل البحث التلقائي)
            # =======================================================
            
            # 💡 5.1. دالة توحيد الألفات (Normalize)
            cur.execute('''
                CREATE OR REPLACE FUNCTION public.normalize_arabic(text)
                RETURNS text AS $$
                SELECT TRANSLATE($1, 'أإآ', 'ااا')
                $$ LANGUAGE SQL IMMUTABLE RETURNS NULL ON NULL INPUT;
            ''')

            # 💡 5.2. إنشاء جدول البحث
            cur.execute('''
                CREATE TABLE IF NOT EXISTS family_search (
                    code TEXT PRIMARY KEY,
                    full_name TEXT NOT NULL,
                    nick_name TEXT,
                    level INT, 
                    updated_at TIMESTAMPTZ DEFAULT NOW()
                )
            ''')

            # 💡 5.3. إضافة عمود البحث المحسوب (Generated Column)
            cur.execute("""
                DO $$
                BEGIN
                    IF NOT EXISTS (SELECT 1 FROM information_schema.columns 
                                   WHERE table_name='family_search' AND column_name='search_text') THEN
                        ALTER TABLE family_search 
                        ADD COLUMN search_text TEXT 
                        GENERATED ALWAYS AS (public.normalize_arabic(coalesce(full_name, '') || ' ' || coalesce(nick_name, ''))) STORED;
                    END IF;
                END $$;
            """)

            # 💡 5.4. إنشاء الفهارس لتسريع البحث
            cur.execute("CREATE INDEX IF NOT EXISTS idx_family_search_gin ON family_search USING GIN (to_tsvector('arabic', search_text));")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_family_search_name ON family_search(full_name);")

            # 💡 5.5. دالة الـ Trigger لتحديث البحث تلقائياً
            cur.execute('''
                CREATE OR REPLACE FUNCTION refresh_family_search() RETURNS trigger AS $$
                BEGIN
                    INSERT INTO family_search (code, full_name, nick_name, level)
                    VALUES (
                        NEW.code,
                        public.get_full_name(NEW.code, NULL, FALSE),
                        NEW.nick_name,
                        NEW.level
                    )
                    ON CONFLICT (code) DO UPDATE SET
                        full_name = EXCLUDED.full_name,
                        nick_name = EXCLUDED.nick_name,
                        level = EXCLUDED.level,
                        updated_at = NOW();
                    RETURN NEW;
                END;
                $$ LANGUAGE plpgsql;
            ''')

            # 💡 5.6. ربط الـ Trigger بجدول الأسماء
            cur.execute('''
                DROP TRIGGER IF EXISTS trig_refresh_search ON family_name;
                CREATE TRIGGER trig_refresh_search
                    AFTER INSERT OR UPDATE OF name, f_code, m_code, h_code, w_code, nick_name, level
                    ON family_name
                    FOR EACH ROW
                    EXECUTE FUNCTION refresh_family_search();
            ''')
            # ز. 💡 تحديث البيانات الموجودة حالياً لضمان ظهورها في البحث فوراً
          
            cur.execute('''
                INSERT INTO family_search (code, full_name, nick_name, level)
                SELECT code, public.get_full_name(code, NULL, FALSE), nick_name, level 
                FROM family_name
                ON CONFLICT (code) DO UPDATE SET
                    full_name = EXCLUDED.full_name,
                    nick_name = EXCLUDED.nick_name,
                    level = EXCLUDED.level,
                    updated_at = NOW();
            ''')

            print("✅ تم تحديث كافة المكونات ونظام البحث يعمل الآن تلقائياً!")
           
          
        except Exception as e:
            print(f"❌ خطأ أثناء تهيئة قاعدة البيانات: {e}") 
            raise