import os
import psycopg2
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
            # 🟢 رسالة بداية واحدة
            print("🟢 جاري تهيئة مكونات قاعدة البيانات الأساسية...")

            # =======================================================
            # 1. إنشاء جدول stats_summary
            # =======================================================
            cur.execute('''
                CREATE TABLE IF NOT EXISTS stats_summary (
                    key TEXT PRIMARY KEY,
                    value BIGINT NOT NULL DEFAULT 0
                );
            ''')
            
            # تهيئة الصف الأساسي
            cur.execute("""
                INSERT INTO stats_summary (key, value)
                VALUES ('total_visitors_count', 0)
                ON CONFLICT (key) DO NOTHING;
            """)
            
            # =======================================================
            # 2. ترحيل البيانات (الإبقاء على رسالة الترحيل فقط)
            # =======================================================
            cur.execute("SELECT value FROM stats_summary WHERE key = 'total_visitors_count'")
            current_total = cur.fetchone()[0] if cur.rowcount > 0 else 0

            if current_total == 0:
                cur.execute("SELECT COUNT(DISTINCT session_id) FROM visits")
                initial_total = cur.fetchone()[0] or 0
                
                if initial_total > 0:
                    cur.execute("""
                        UPDATE stats_summary
                        SET value = %s
                        WHERE key = 'total_visitors_count' AND value = 0;
                    """, (initial_total,))
                    print(f"✅ تم ترحيل {initial_total} زائر كإجمالي ابتدائي.") # ⬅️ إبقاء هذه الرسالة
                # else: إزالة رسالة "جدول visits فارغ"
            
            # =======================================================
            # 3. إنشاء جدول الإشعارات (Notifications)
            # =======================================================
            cur.execute('''
                CREATE TABLE IF NOT EXISTS notifications (
                    id SERIAL PRIMARY KEY,
                    sender_id INTEGER REFERENCES users(id) ON DELETE SET NULL, 
                    recipient_id INTEGER REFERENCES users(id) ON DELETE CASCADE NOT NULL,
                    message TEXT NOT NULL,
                    is_read BOOLEAN DEFAULT FALSE,
                    is_admin_message BOOLEAN DEFAULT FALSE,
                    created_at TIMESTAMPTZ DEFAULT NOW()
                );
            ''')
            cur.execute('CREATE INDEX IF NOT EXISTS idx_notifications_recipient_unread ON notifications(recipient_id, is_read);')
           
            
            # ========================================
            # 4. تحديث دالة PostgreSQL لجلب الاسم الكامل (public.get_full_name)
            # ========================================
            cur.execute('''
                CREATE OR REPLACE FUNCTION public.get_full_name(
                    p_code TEXT,
                    p_max_names INT DEFAULT NULL,
                    p_include_nick BOOLEAN DEFAULT FALSE
                ) RETURNS TEXT AS $$
                DECLARE
                    result TEXT := '';
                    rec RECORD;
                    names_parts TEXT[] := '{}';
                    current_name_count INT := 0;
                    nick_name_part TEXT := NULL;
                BEGIN
                    -- حلقة لتجميع الأسماء من الشخص للأجداد
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
                        -- حفظ اللقب للشخص الأول فقط
                        IF current_name_count = 0 AND rec.nick_name IS NOT NULL AND rec.nick_name != '' THEN
                            nick_name_part := rec.nick_name;
                        END IF;

                        -- تجميع الأسماء حتى الحد الأقصى المطلوب
                        IF p_max_names IS NULL OR current_name_count < p_max_names THEN
                            names_parts := names_parts || rec.name;
                            current_name_count := current_name_count + 1;
                        END IF;
                    END LOOP;

                    result := array_to_string(names_parts, ' ');
                    
                    -- إضافة اللقب بين قوسين فقط إذا طُلب صراحةً
                    IF p_include_nick AND nick_name_part IS NOT NULL THEN
                        result := result || ' (' || nick_name_part || ')';
                    END IF;

                    RETURN result;
                END;
                $$ LANGUAGE plpgsql STABLE;
            ''')
            # ❌ إزالة: print("✅ تم تحديث دالة get_full_name.")

            # ---
            # 5. جدول family_search + الـ Trigger
            # ---
            
            cur.execute('''
                CREATE TABLE IF NOT EXISTS family_search (
                    code TEXT PRIMARY KEY,
                    full_name TEXT NOT NULL,
                    nick_name TEXT,
                    level INT, 
                    search_text TEXT GENERATED ALWAYS AS (
                        coalesce(full_name, '') || ' ' || coalesce(nick_name, '')
                    ) STORED,
                    updated_at TIMESTAMPTZ DEFAULT NOW()
                )
            ''')

            # إضافة الفهارس
            cur.execute("""
                CREATE INDEX IF NOT EXISTS idx_family_search_gin
                ON family_search
                USING GIN (to_tsvector('arabic', search_text))
            """)
            cur.execute('CREATE INDEX IF NOT EXISTS idx_family_search_name ON family_search(full_name)')
            
            # 6. دالة Trigger (refresh_family_search)
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

            # 7. ربط Trigger بجدول family_name
            cur.execute('''
                DROP TRIGGER IF EXISTS trig_refresh_search ON family_name;
                CREATE TRIGGER trig_refresh_search
                    AFTER INSERT OR UPDATE OF name, f_code, m_code, h_code, w_code, nick_name, level
                    ON family_name
                    FOR EACH ROW
                    EXECUTE FUNCTION refresh_family_search();
            ''')
            
            # ❌ إزالة: print("✅ تم التحقق من جدول family_search والـ Trigger بنجاح.")

            
            # 8. رسالة نهاية واحدة
            print("✅ تم إنهاء التهيئة بنجاح!")
          
           
        except Exception as e:
            # ❌ الإبقاء على رسالة الخطأ الحاسم فقط
            print(f"❌ خطأ أثناء تهيئة قاعدة البيانات: {e}") 
            raise