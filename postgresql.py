import os
import psycopg2
from contextlib import contextmanager
from dotenv import load_dotenv

load_dotenv()

@contextmanager
def get_db_context():
    conn = None
    try:
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
            sslmode="require" if os.getenv("DATABASE_URL") else "prefer"
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
            print("🟢 سيتم تحديث الدوال والجداول الآن لتطبيق التعديلات المطلوبة...")

            # ========================================
            # 1. إنشاء/تحديث دالة get_full_name
            # ========================================
            print("إنشاء دالة get_full_name في PostgreSQL...")
            cur.execute('''
                CREATE OR REPLACE FUNCTION public.get_full_name(
                    p_code TEXT,
                    p_max_length INT DEFAULT NULL,
                    p_include_nick BOOLEAN DEFAULT FALSE
                ) RETURNS TEXT AS $$
                DECLARE
                    result TEXT := '';
                    rec RECORD;
                    max_len INT := COALESCE(p_max_length, 999);
                    parts TEXT[] := '{}';
                    name_part_processed TEXT; -- **جديد: لتبديل الفراغات**
                BEGIN
                    FOR rec IN
                        WITH RECURSIVE tree AS (
                            SELECT code, name, f_code, nick_name, 1 as depth
                            FROM family_name WHERE code = p_code
                            UNION ALL
                            SELECT fn.code, fn.name, fn.f_code, fn.nick_name, t.depth + 1
                            FROM family_name fn
                            JOIN tree t ON fn.code = t.f_code
                            WHERE t.depth < 20
                        )
                        SELECT name, nick_name FROM tree ORDER BY depth ASC
                    LOOP
                        -- **التعديل الجديد:** إزالة الفراغات من الاسم المفرد قبل إضافته.
                        -- هذا يضمن أن 'ابرا هيم' يصبح 'ابراهيم' و 'عبد الرحمن' يصبح 'عبدالرحمن'.
                        name_part_processed := regexp_replace(rec.name, '\s+', '', 'g');

                        IF p_include_nick AND rec.nick_name IS NOT NULL AND rec.nick_name != '' THEN
                            parts := parts || rec.nick_name;
                        ELSE
                            parts := parts || name_part_processed; -- استخدام الاسم المعالج
                        END IF;
                    END LOOP;

                    result := array_to_string(parts, ' ');
                    IF char_length(result) > max_len THEN
                        result := left(result, max_len) || '...';
                    END IF;

                    RETURN result;
                END;
                $$ LANGUAGE plpgsql STABLE;
            ''')

            # normalize_arabic
            cur.execute('''
                CREATE OR REPLACE FUNCTION normalize_arabic(text)
                RETURNS text AS $$
                SELECT translate(
                    regexp_replace(lower($1), '[ًٌٍَُِّْـ]', '', 'g'),
                    'أإآىؤئ',
                    'اايايي'
                );
                $$ LANGUAGE sql IMMUTABLE;
            ''')

            # ========================================
            # حذف Trigger والدالة المرتبطة (إذا موجودة)
            # ========================================
            cur.execute('DROP TRIGGER IF EXISTS trig_refresh_search ON family_name;')
            cur.execute('DROP FUNCTION IF EXISTS refresh_family_search();')

            # ========================================
            # إنشاء جدول family_search الجديد (يتم حذفه وإعادة إنشائه لتطبيق التغيير)
            # ========================================
            cur.execute('DROP TABLE IF EXISTS family_search;')
            cur.execute('''
                CREATE TABLE family_search (
                    code TEXT PRIMARY KEY,
                    full_name TEXT NOT NULL,
                    nick_name TEXT,
                    search_text TEXT GENERATED ALWAYS AS (
                        coalesce(full_name, '') || ' ' || coalesce(nick_name, '')
                    ) STORED,
                    updated_at TIMESTAMPTZ DEFAULT NOW()
                )
            ''')

            cur.execute("""
                CREATE INDEX idx_family_search_gin
                ON family_search USING GIN (to_tsvector('arabic', search_text))
            """)

            cur.execute('CREATE INDEX idx_family_search_name ON family_search(full_name)')

            cur.execute('''
                ALTER TABLE family_search
                ADD COLUMN full_name_normalized TEXT GENERATED ALWAYS AS (
                    regexp_replace(full_name, '\s+', ' ', 'g')
                ) STORED;
            ''')

            cur.execute('''
                ALTER TABLE family_search
                ADD COLUMN normalized_full_name TEXT;
            ''')

            cur.execute('''
                UPDATE family_search
                SET normalized_full_name = normalize_arabic(full_name);
            ''')

            cur.execute('''
                CREATE OR REPLACE FUNCTION update_normalized_full_name()
                RETURNS trigger AS $$
                BEGIN
                    NEW.normalized_full_name := normalize_arabic(NEW.full_name);
                    RETURN NEW;
                END;
                $$ LANGUAGE plpgsql;
            ''')

            cur.execute('''
                CREATE TRIGGER trg_normalized_fullname
                BEFORE INSERT OR UPDATE ON family_search
                FOR EACH ROW
                EXECUTE FUNCTION update_normalized_full_name();
            ''')

            # ========================================
            # دالة و trigger للتحديث التلقائي عند تعديل family_name
            # ========================================
            cur.execute('''
                CREATE OR REPLACE FUNCTION refresh_family_search() RETURNS trigger AS $$
                BEGIN
                    INSERT INTO family_search (code, full_name, nick_name)
                    VALUES (
                        NEW.code,
                        public.get_full_name(NEW.code, NULL, FALSE),
                        NEW.nick_name
                    )
                    ON CONFLICT (code) DO UPDATE SET
                        full_name = EXCLUDED.full_name,
                        nick_name = EXCLUDED.nick_name,
                        updated_at = NOW();
                    RETURN NEW;
                END;
                $$ LANGUAGE plpgsql;
            ''')

            cur.execute('''
                CREATE TRIGGER trig_refresh_search
                AFTER INSERT OR UPDATE OF name, f_code, m_code, h_code, w_code, nick_name
                ON family_name
                FOR EACH ROW
                EXECUTE FUNCTION refresh_family_search();
            ''')

            # ========================================
            # تعبئة الجدول لأول مرة
            # ========================================
            cur.execute('''
                INSERT INTO family_search (code, full_name, nick_name)
                SELECT 
                    code,
                    public.get_full_name(code, NULL, FALSE),
                    nick_name
                FROM family_name
                WHERE level >= 0
                ON CONFLICT (code) DO NOTHING
            ''')

            print("✅ تم إنشاء قاعدة البيانات بنجاح!")

        except Exception as e:
            print(f"❌ خطأ أثناء التهيئة: {e}")
            raise