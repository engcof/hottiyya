# postgresql.py
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
        
        if not all([host, dbname, user, password]):
            raise ValueError("متغيرات قاعدة البيانات مفقودة!")

        conn = psycopg2.connect(
            host=host,
            dbname=dbname,
            user=user,
            password=password,
            port="5432",
            sslmode="require"
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
            print("جاري تحديث قاعدة البيانات...")

            
            # أضف هذا الكود في آخر دالة init_database() قبل الـ print الأخير
            cur.execute('''
                CREATE TABLE IF NOT EXISTS visits (
                    id SERIAL PRIMARY KEY,
                    session_id TEXT NOT NULL,
                    user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
                    username TEXT,
                    ip TEXT,
                    user_agent TEXT,
                    path TEXT,
                    timestamp TIMESTAMPTZ DEFAULT NOW()
                )
            ''')
            print("تم إنشاء جدول visits لتتبع الزوار")

            # إضافة فهرس للأداء الملكي (مهم جدًا)
            cur.execute('CREATE INDEX IF NOT EXISTS idx_visits_session ON visits(session_id)')
            cur.execute('CREATE INDEX IF NOT EXISTS idx_visits_timestamp ON visits(timestamp DESC)')
            print("تم إضافة الفهرس لأداء فائق السرعة")  
        except Exception as e:
            print(f"خطأ غير متوقع أثناء التحديث: {e}")
            raise