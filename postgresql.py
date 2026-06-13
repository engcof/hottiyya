import os
import psycopg2
import psycopg2.extras
from contextlib import contextmanager
from dotenv import load_dotenv

load_dotenv()

# 🔒 تحديد ما إذا كانت البيئة هي إنتاج (على Render) أم محلي للتطوير
IS_PROD = os.getenv("RENDER_EXTERNAL_URL") is not None or os.getenv("ENVIRONMENT") == "production"

@contextmanager
def get_db_context():
    conn = None
    database_url = os.getenv("DATABASE_URL")
    
    try:
        if database_url:
            conn = psycopg2.connect(database_url, sslmode="require")
        else:
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
            # =======================================================
            # الجداول العامة المشتركة (تعمل في الإنتاج والمحلي)
            # =======================================================
            
            # 1. جدول معرض الصور
            cur.execute("""
                CREATE TABLE IF NOT EXISTS gallery (
                    id SERIAL PRIMARY KEY,
                    title VARCHAR(255) NOT NULL,
                    image_url TEXT NOT NULL,
                    category VARCHAR(100),
                    user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
            """)
            cur.execute("CREATE INDEX IF NOT EXISTS idx_gallery_category ON gallery(category);")
            
            # 2. جدول سجلات العمليات (الأمن والرقابة)
            cur.execute(""" 
                CREATE TABLE IF NOT EXISTS activity_logs (
                    id SERIAL PRIMARY KEY,
                    user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
                    action VARCHAR(100) NOT NULL,
                    details TEXT,
                    timestamp TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
                );
            """)
            
            # 3. جدول الفيديو
            cur.execute(""" 
                CREATE TABLE IF NOT EXISTS videos (
                    id SERIAL PRIMARY KEY,
                    title VARCHAR(255) NOT NULL,
                    video_url TEXT NOT NULL,
                    thumbnail_url TEXT,
                    category VARCHAR(100),
                    user_id INTEGER REFERENCES users(id),
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
            """)           

            # 4. جدول المكتبة الرقمية
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
                    views_count INTEGER DEFAULT 0,
                    downloads_count INTEGER DEFAULT 0,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
            """)
            cur.execute("ALTER TABLE library ADD COLUMN IF NOT EXISTS views_count INTEGER DEFAULT 0;")
            cur.execute("ALTER TABLE library ADD COLUMN IF NOT EXISTS downloads_count INTEGER DEFAULT 0;")
            cur.execute("ALTER TABLE library ADD COLUMN IF NOT EXISTS allow_download BOOLEAN DEFAULT TRUE;")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_library_category ON library(category);")
            
            # =======================================================
            # 🔒 حماية بيانات العائلة: يتم إنشاؤها في السيرفر المحلي فقط
            # =======================================================
            if not IS_PROD:
                print("🛠️ بيئة محلية: جاري تهيئة جداول ودوال شجرة العائلة...")
                
                # دالة توحيد الألفات
                cur.execute('''
                    CREATE OR REPLACE FUNCTION public.normalize_arabic(text)
                    RETURNS text AS $$
                    SELECT TRANSLATE($1, 'أإآ', 'ااا')
                    $$ LANGUAGE SQL IMMUTABLE RETURNS NULL ON NULL INPUT;
                ''')

                # جدول البحث
                cur.execute('''
                    CREATE TABLE IF NOT EXISTS family_search (
                        code TEXT PRIMARY KEY,
                        full_name TEXT NOT NULL,
                        nick_name TEXT,
                        level INT, 
                        updated_at TIMESTAMPTZ DEFAULT NOW()
                    )
                ''')

                # عمود البحث المحسوب
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

                # فهارس البحث
                cur.execute("CREATE INDEX IF NOT EXISTS idx_family_search_gin ON family_search USING GIN (to_tsvector('arabic', search_text));")
                cur.execute("CREATE INDEX IF NOT EXISTS idx_family_search_name ON family_search(full_name);")

                # دالة الـ Trigger لتحديث البحث
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

                # ربط الـ Trigger بجدول الأسماء
                cur.execute('''
                    DROP TRIGGER IF EXISTS trig_refresh_search ON family_name;
                    CREATE TRIGGER trig_refresh_search
                        AFTER INSERT OR UPDATE OF name, f_code, m_code, h_code, w_code, nick_name, level
                        ON family_name
                        FOR EACH ROW
                        EXECUTE FUNCTION refresh_family_search();
                ''')
                print("✅ تم تهيئة نظام شجرة العائلة المحلي بنجاح.")
            else:
                print("🚀 بيئة إنتاج: تم تخطي تهيئة جداول الشجرة لحماية البيانات الشخصية.")

            print("✅ تم تحديث كافة المكونات العامة بنجاح!")
           
        except Exception as e:
            print(f"❌ خطأ أثناء تهيئة قاعدة البيانات: {e}") 
            raise