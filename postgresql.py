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


# ←←←←←←←←←←←←←←←←←←←←←←←←←←←←←←←←
# دالة التهيئة: تُستدعى مرة واحدة فقط عند تشغيل التطبيق
# من main.py عبر lifespan
def init_database():
    with get_db_context() as conn:
        conn.autocommit = True
        cur = conn.cursor()

        # --- تحديث جدول articles ---
        cur.execute('ALTER TABLE articles ADD COLUMN IF NOT EXISTS author_id INTEGER;')
        cur.execute('ALTER TABLE articles ADD COLUMN IF NOT EXISTS image_url TEXT;')

        # تحقق إذا العمود author موجود قبل الترحيل
        cur.execute("""
            SELECT column_name 
            FROM information_schema.columns 
            WHERE table_name = 'articles' AND column_name = 'author'
        """)
        author_column_exists = cur.fetchone() is not None

        if author_column_exists:
            print("وجد عمود author قديم → جاري نقل البيانات إلى author_id...")
            cur.execute('''
                UPDATE articles a
                SET author_id = u.id
                FROM users u
                WHERE a.author = u.username
                  AND a.author_id IS NULL
                  AND a.author IS NOT NULL;
            ''')

            try:
                cur.execute('ALTER TABLE articles ALTER COLUMN author_id SET NOT NULL;')
            except:
                pass

            try:
                cur.execute('ALTER TABLE articles DROP COLUMN author;')
                print("تم حذف العمود author بنجاح")
            except:
                pass
        else:
            print("العمود author غير موجود (تم الترحيل من قبل) → لا حاجة لنقل البيانات")

              # === ترحيل comments بأمان 100% ===
        cur.execute("SELECT column_name FROM information_schema.columns WHERE table_name = 'comments' AND column_name = 'user_id'")
        user_id_exists = cur.fetchone() is not None

        cur.execute("SELECT column_name FROM information_schema.columns WHERE table_name = 'comments' AND column_name = 'username'")
        username_exists = cur.fetchone() is not None

        if not user_id_exists:
            cur.execute('ALTER TABLE comments ADD COLUMN user_id INTEGER')

        if username_exists and user_id_exists:
            print("جاري نقل البيانات من username → user_id...")
            cur.execute('''
                UPDATE comments c SET user_id = u.id
                FROM users u
                WHERE c.username = u.username AND c.user_id IS NULL
            ''')

            try: cur.execute('ALTER TABLE comments ALTER COLUMN user_id SET NOT NULL')
            except: pass
            try: cur.execute('ALTER TABLE comments DROP COLUMN username')
            except: pass

        print("تم تحديث جدول comments بنجاح (username → user_id)")