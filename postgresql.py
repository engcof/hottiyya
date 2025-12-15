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
            # 1. تهيئة صفوف stats_summary الأساسية (لضمان وجود العداد)
            # =======================================================
            # (تم حذف CREATE TABLE IF NOT EXISTS stats_summary)
            cur.execute("""
                INSERT INTO stats_summary (key, value)
                VALUES ('total_visitors_count', 0)
                ON CONFLICT (key) DO NOTHING;
            """)
            
            # =======================================================
            # 2. إنشاء فهرس notifications (لضمان وجوده)
            # =======================================================
            # (تم حذف CREATE TABLE IF NOT EXISTS notifications)
            cur.execute('CREATE INDEX IF NOT EXISTS idx_notifications_recipient_unread ON notifications(recipient_id, is_read);')
           
            # =======================================================
            # 3. ترحيل التواريخ: حذف d_o_b و d_o_d من family_info (ترحيل هيكلي)
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
            # 4. تحديث دالة PostgreSQL لحساب العمر عند الوفاة (يجب أن تبقى)
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
            ''')
            
            # =======================================================
            # 5. إنشاء جدول family_age_search مع العمود المحسوب (يجب أن يبقى)
            # =======================================================
            cur.execute('''
                CREATE TABLE IF NOT EXISTS family_age_search (
                    code TEXT PRIMARY KEY REFERENCES family_name(code) ON DELETE CASCADE,
                    
                    -- التواريخ الآن هنا
                    d_o_b DATE,
                    d_o_d DATE,
                    
                    -- العمر عند الوفاة: عمود يُحسب تلقائياً ويُخزَّن
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
            # 6. تحديث دالة PostgreSQL لجلب الاسم الكامل (يجب أن تبقى)
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

            # ..........................
            # 7. جدول family_search + الـ Trigger (يجب أن تبقى)
            # ..........................

            # 💡 7.1. إعادة تعريف دالة التطبيع (توحيد الألفات فقط)
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

            # 💡 7.2. إنشاء جدول family_search (لضمان وجوده)
            cur.execute('''
                CREATE TABLE IF NOT EXISTS family_search (
                    code TEXT PRIMARY KEY,
                    full_name TEXT NOT NULL,
                    nick_name TEXT,
                    level INT, 
                    updated_at TIMESTAMPTZ DEFAULT NOW()
                )
            ''')


            # 💡 7.3. إدارة عمود search_text المحسوب (إضافة/تحديث آمن)
            cur.execute("""
                DO $$
                BEGIN
                    -- 1. حذف الفهرس GIN أولاً لأنه يعتمد على search_text
                    DROP INDEX IF EXISTS idx_family_search_gin;
                    
                    -- 2. إذا كان العمود search_text موجوداً، قم بحذفه
                    IF EXISTS (SELECT 1 FROM information_schema.columns 
                            WHERE table_name='family_search' AND column_name='search_text') THEN
                        EXECUTE 'ALTER TABLE family_search DROP COLUMN search_text;';
                        RAISE NOTICE '✅ تم حذف العمود search_text القديم.';
                    END IF;
                    
                    -- 3. إضافة العمود المحسوب الجديد بالمنطق الصحيح والدالة المحدثة
                    EXECUTE 'ALTER TABLE family_search 
                            ADD COLUMN search_text TEXT 
                            GENERATED ALWAYS AS (public.normalize_arabic(coalesce(full_name, '''') || '' '' || coalesce(nick_name, ''''))) STORED;';
                    RAISE NOTICE '✅ تم إضافة عمود search_text المحسوب الجديد والمحدّث.';

                END
                $$;
            """)

            # 💡 7.4. إعادة إنشاء الفهارس (بعد ضمان وجود عمود search_text الجديد)
            cur.execute("""
                CREATE INDEX IF NOT EXISTS idx_family_search_gin
                ON family_search
                USING GIN (to_tsvector('arabic', search_text))
            """)
            cur.execute('CREATE INDEX IF NOT EXISTS idx_family_search_name ON family_search(full_name)')
            # ..........................
            
            # 7.5. دالة Trigger (refresh_family_search)
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

            # 7.6. ربط Trigger بجدول family_name
            cur.execute('''
                DROP TRIGGER IF EXISTS trig_refresh_search ON family_name;
                CREATE TRIGGER trig_refresh_search
                    AFTER INSERT OR UPDATE OF name, f_code, m_code, h_code, w_code, nick_name, level
                    ON family_name
                    FOR EACH ROW
                    EXECUTE FUNCTION refresh_family_search();
            ''')
            

            # 9. رسالة نهاية واحدة (نظيفة)
            print("✅ تم إنهاء التهيئة بنجاح!")
          
           
        except Exception as e:
            # ❌ الإبقاء على رسالة الخطأ الحاسم فقط
            print(f"❌ خطأ أثناء تهيئة قاعدة البيانات: {e}") 
            raise