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
           
            # =======================================================
            # 4. ترحيل التواريخ: حذف d_o_b و d_o_d من family_info
            # =======================================================
            cur.execute("""
                DO $$
                BEGIN
                    -- حذف العمودين من family_info ونقل مسؤوليتهما إلى family_age_search
                    IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='family_info' AND column_name='d_o_b') THEN
                        ALTER TABLE family_info DROP COLUMN d_o_b;
                        RAISE NOTICE '✅ تم حذف العمود d_o_b من family_info.';
                    END IF;
                    
                    IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='family_info' AND column_name='d_o_d') THEN
                        ALTER TABLE family_info DROP COLUMN d_o_d;
                        RAISE NOTICE '✅ تم حذف العمود d_o_d من family_info.';
                    END IF;
                END
                $$;
            """)

            # حذف الـ Trigger غير المستخدم (إن وجد)
            cur.execute('''
                DROP TRIGGER IF EXISTS trig_refresh_age_search ON family_info;
            ''')

            # ========================================
            # 5. تحديث دالة PostgreSQL لحساب العمر عند الوفاة
            # (مطلوبة لاستخدامها في العمود المحسوب)
            # ========================================
            cur.execute('''
                CREATE OR REPLACE FUNCTION public.calculate_age_at_death_db(
                    p_dob DATE,
                    p_dod DATE
                ) RETURNS INTEGER AS $$
                DECLARE
                    age INTEGER := NULL;
                BEGIN
                    -- منطق حساب العمر عند الوفاة
                    IF p_dob IS NOT NULL AND p_dod IS NOT NULL THEN
                        IF p_dod >= p_dob THEN
                            age := EXTRACT(YEAR FROM p_dod) - EXTRACT(YEAR FROM p_dob);
                            
                            IF (EXTRACT(MONTH FROM p_dod), EXTRACT(DAY FROM p_dod)) < 
                            (EXTRACT(MONTH FROM p_dob), EXTRACT(DAY FROM p_dob)) THEN
                                age := age - 1;
                            END IF;
                        END IF;
                    END IF;
                    
                    RETURN age;
                END;
                $$ LANGUAGE plpgsql IMMUTABLE;
                -- 💡 ملاحظة: يجب أن تكون الدالة IMMUTABLE لكي تستخدم في الأعمدة المحسوبة
            ''')
            
            # =======================================================
            # 6. إنشاء جدول family_age_search مع العمود المحسوب
            # =======================================================
            cur.execute('''
                CREATE TABLE IF NOT EXISTS family_age_search (
                    code TEXT PRIMARY KEY REFERENCES family_name(code) ON DELETE CASCADE,
                    
                    -- التواريخ الآن هنا
                    d_o_b DATE,
                    d_o_d DATE,
                    
                    -- العمر عند الوفاة: عمود يُحسب تلقائياً ويُخزَّن
                    age_at_death INTEGER 
                    GENERATED ALWAYS AS (public.calculate_age_at_death_db(d_o_b, d_o_d)) STORED,
                    
                    -- حقل بحث إضافي
                    search_text TEXT GENERATED ALWAYS AS (
                        CASE 
                            WHEN d_o_d IS NOT NULL THEN 'متوفي' 
                            WHEN d_o_b IS NOT NULL THEN 'حي' 
                            ELSE '' 
                        END
                    ) STORED,
                    
                    updated_at TIMESTAMPTZ DEFAULT NOW()
                );
            ''')

            # إضافة فهارس للتواريخ
            cur.execute('CREATE INDEX IF NOT EXISTS idx_age_search_dob ON family_age_search(d_o_b);')
            cur.execute('CREATE INDEX IF NOT EXISTS idx_age_search_dod ON family_age_search(d_o_d);')
            
            # ========================================
            # 7. تحديث دالة PostgreSQL لجلب الاسم الكامل (public.get_full_name)
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

            # ..........................
            # 5. جدول family_search + الـ Trigger
            # ..........................

            # ❌ 1. حذف دالة normalize_arabic القديمة (لإعادة إنشائها بالشكل الجديد)
            cur.execute('''
                DROP FUNCTION IF EXISTS public.normalize_arabic(text) CASCADE;
            ''')

            # 💡 2. إعادة تعريف الدالة لتوحيد (أ، إ، آ) إلى 'ا'، مع الإبقاء على 'ء'، 'ي'، 'ة'، 'ؤ'، 'ئ' كما هي
            cur.execute('''
                CREATE OR REPLACE FUNCTION public.normalize_arabic(text)
                RETURNS text AS $$
                -- هذه الدالة تركز فقط على توحيد الهمزات على الألف والألف الممدودة
                SELECT 
                    TRANSLATE(
                        $1, 
                        'أإآ', -- الأحرف التي سيتم استبدالها (ألفات مهموزة)
                        'ااا'  -- البدائل: (أ, إ, آ) -> ا
                    )
            $$ LANGUAGE SQL IMMUTABLE RETURNS NULL ON NULL INPUT;
            ''')

            # 💡 3. حذف جدول البحث (لتطبيق الدالة الجديدة على search_text)
            cur.execute('''
                DROP TABLE IF EXISTS family_search CASCADE;
            ''')

            # 💡 4. إعادة إنشاء جدول family_search
            cur.execute('''
                CREATE TABLE IF NOT EXISTS family_search (
                    code TEXT PRIMARY KEY,
                    full_name TEXT NOT NULL,
                    nick_name TEXT,
                    level INT, 
                    -- الآن search_text يستخدم دالة normalize_arabic الجديدة
                    search_text TEXT GENERATED ALWAYS AS (
                        public.normalize_arabic(coalesce(full_name, '') || ' ' || coalesce(nick_name, ''))
                    ) STORED,
                    updated_at TIMESTAMPTZ DEFAULT NOW()
                )
            ''')

            # 💡 5. إعادة إنشاء الفهرس GIN
            cur.execute("""
                CREATE INDEX IF NOT EXISTS idx_family_search_gin
                ON family_search
                USING GIN (to_tsvector('arabic', search_text))
            """)
            cur.execute('CREATE INDEX IF NOT EXISTS idx_family_search_name ON family_search(full_name)')
            # ..........................

          
            
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

            # 💡 8. إضافة خطوة التحديث الإجباري لجميع الصفوف القديمة (لإعادة بناء family_search)
            print("⚙️ جاري إعادة بناء جدول البحث لجميع الأعضاء القدامى...")
            cur.execute("""
                UPDATE family_name
                SET level = level; -- تحديث الحقل بقيمته الحالية لتشغيل الـ Trigger
            """)
            print(f"✅ تم تحديث {cur.rowcount} عضو بنجاح وإعادة بناء جدول البحث.")

            # 9. رسالة نهاية واحدة (كانت رقم 8 سابقاً)
            print("✅ تم إنهاء التهيئة بنجاح!")

            # ..........................
            # 8. رسالة نهاية واحدة
            print("✅ تم إنهاء التهيئة بنجاح!")
          
           
        except Exception as e:
            # ❌ الإبقاء على رسالة الخطأ الحاسم فقط
            print(f"❌ خطأ أثناء تهيئة قاعدة البيانات: {e}") 
            raise