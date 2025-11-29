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
            print("جاري تحديث قاعدة البيانات...")

            # جدول الزيارات - مع الفهرس الفريد من البداية
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

            # حذف التكرارات القديمة (آمن تمامًا)
            cur.execute('''
                DELETE FROM visits a USING (
                    SELECT MIN(id) as keep_id, session_id
                    FROM visits
                    GROUP BY session_id
                    HAVING COUNT(*) > 1
                ) b
                WHERE a.session_id = b.session_id AND a.id != b.keep_id;
            ''')

            # الفهرس الفريد الملكي - الحل النهائي
            cur.execute('CREATE UNIQUE INDEX IF NOT EXISTS uniq_session_id ON visits(session_id)')
            cur.execute('CREATE INDEX IF NOT EXISTS idx_visits_timestamp ON visits(timestamp DESC)')

            print("تم إنشاء/تحديث جدول visits + الفهرس الفريد بنجاح - لا تحذيرات بعد اليوم!")

        except Exception as e:
            print(f"خطأ أثناء تهيئة قاعدة البيانات: {e}")
            raise