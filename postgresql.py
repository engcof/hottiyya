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
            print("🟢 جاري التحقق من تهيئة قاعدة البيانات...")

            # =======================================================
            # 1. إنشاء جدول stats_summary لتخزين الإجمالي الحقيقي (يُنفذ مرة واحدة)
            # =======================================================
            cur.execute('''
                CREATE TABLE IF NOT EXISTS stats_summary (
                    key TEXT PRIMARY KEY,
                    value BIGINT NOT NULL DEFAULT 0
                );
            ''')
            print("✅ تم التحقق من جدول stats_summary")
            
            # تهيئة الصف الأساسي (لتخزين Total Visitors)
            cur.execute("""
                INSERT INTO stats_summary (key, value)
                VALUES ('total_visitors_count', 0)
                ON CONFLICT (key) DO NOTHING;
            """)
            
            # =======================================================
            # 2. ترحيل البيانات: نسخ الإجمالي القديم إلى الجدول الجديد (مرة واحدة فقط)
            # =======================================================
            cur.execute("SELECT value FROM stats_summary WHERE key = 'total_visitors_count'")
            current_total = cur.fetchone()[0] if cur.rowcount > 0 else 0

            # نتحقق إذا كانت القيمة الحالية صفر (لم يتم الترحيل بعد)
            if current_total == 0:
                # *تنبيه: يجب التأكد أن جدول visits موجود بالفعل في القاعدة قبل هذا السطر*
                print("⚠️ جاري ترحيل الإجمالي الحالي للزوار من جدول visits...")
                
                cur.execute("SELECT COUNT(DISTINCT session_id) FROM visits")
                initial_total = cur.fetchone()[0] or 0
                
                if initial_total > 0:
                    cur.execute("""
                        UPDATE stats_summary
                        SET value = %s
                        WHERE key = 'total_visitors_count' AND value = 0;
                    """, (initial_total,))
                    print(f"✅ تم ترحيل {initial_total} زائر كإجمالي ابتدائي.")
                else:
                    print("◀️ جدول visits فارغ، الإجمالي الابتدائي هو صفر.")

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
            # إضافة فهارس لتحسين الأداء
            cur.execute('CREATE INDEX IF NOT EXISTS idx_notifications_recipient_unread ON notifications(recipient_id, is_read);')
            print("✅ تم التحقق من جدول notifications")
            cur.execute('SELECT * FROM  users;')
            rows = cur.fetchall()
            print(rows)
            
            # ========================================
            # 4. دالة PostgreSQL لجلب الاسم الكامل (public.get_full_name)
            # ========================================
            print("⚙️ جاري تحديث دالة public.get_full_name في PostgreSQL...")
            
            # 🛑 التصحيح: حذف الدالة القديمة أولاً إذا كانت موجودة بتوقيعها القديم
            cur.execute("DROP FUNCTION IF EXISTS public.get_full_name(TEXT, INTEGER, BOOLEAN);")
            
            # 💡 التعديل: لاحظ أننا نستخدم الآن p_max_names
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
            print("✅ تم تحديث دالة get_full_name.")

            # ---
            # 5. جدول family_search + الـ Trigger
            # ---
            print("⚙️ جاري التحقق من جدول family_search والـ Trigger...")
            
            # 🛑 1. حذف الجدول القديم (إذا كان موجوداً) لضمان تطبيق الهيكل الجديد بالكامل
            # هذا ضروري إذا كنت تريد إعادة بناء الجدول بـ 'level' وعمود الـ GENERATED
            cur.execute("DROP TABLE IF EXISTS family_search CASCADE;")
            
            cur.execute('''
                CREATE TABLE family_search (
                    code TEXT PRIMARY KEY,
                    full_name TEXT NOT NULL,
                    nick_name TEXT,
                    level INT, -- 💡 عمود المستوى الجديد
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
                    INSERT INTO family_search (code, full_name, nick_name, level) -- 💡 إضافة level
                    VALUES (
                        NEW.code,
                        public.get_full_name(NEW.code, NULL, FALSE),
                        NEW.nick_name,
                        NEW.level -- 💡 جلب level
                    )
                    ON CONFLICT (code) DO UPDATE SET
                        full_name = EXCLUDED.full_name,
                        nick_name = EXCLUDED.nick_name,
                        level = EXCLUDED.level, -- 💡 تحديث level
                        updated_at = NOW();
                    
                    RETURN NEW;
                END;
                $$ LANGUAGE plpgsql;
            ''')

            # 7. ربط Trigger بجدول family_name
            cur.execute('''
                DROP TRIGGER IF EXISTS trig_refresh_search ON family_name;
                CREATE TRIGGER trig_refresh_search
                    AFTER INSERT OR UPDATE OF name, f_code, m_code, h_code, w_code, nick_name, level -- 💡 إضافة level للتحديث
                    ON family_name
                    FOR EACH ROW
                    EXECUTE FUNCTION refresh_family_search();
            ''')
            
            
            print("✅ تم التحقق من جدول family_search والـ Trigger بنجاح.")

            # ... (بقية الدالة: cur.execute('SELECT * FROM users;'), إلخ) ...
            
            print("✅ تم إنهاء التهيئة بنجاح!")
            try:
                cur.execute('''
                    TRUNCATE family_search RESTART IDENTITY; 
                    
                    INSERT INTO family_search (code, full_name, nick_name, level)
                    SELECT 
                        code, 
                        public.get_full_name(code, NULL, TRUE), -- جلب الاسم الكامل مع اللقب
                        nick_name, 
                        level
                    FROM family_name;
                ''')
                conn.commit()
                return {"message": "نجاح إعادة بناء جدول family_search وتحديث جميع الأسماء."}
            except Exception as e:
                    conn.rollback()
                    return {"error": f"فشل في إعادة البناء: {e}"}
            
           
        except Exception as e:
            print(f"❌ خطأ أثناء التهيئة: {e}")
            raise