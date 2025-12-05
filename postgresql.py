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

            print("✅ تم إنهاء التهيئة بنجاح!")

        except Exception as e:
            print(f"❌ خطأ أثناء التهيئة: {e}")
            raise