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
    conn = None
    try:
        conn = psycopg2.connect(
            host=os.getenv("DB_HOST"),
            dbname=os.getenv("DB_NAME"),
            user=os.getenv("DB_USER"),
            password=os.getenv("DB_PASSWORD"),
            port="5432",
            sslmode="require"
        )
        conn.autocommit = True
        cur = conn.cursor()

        # إنشاء جدول articles بالشكل الصحيح من الأول
        cur.execute('''
            CREATE TABLE IF NOT EXISTS articles (
                id SERIAL PRIMARY KEY,
                title TEXT NOT NULL,
                content TEXT NOT NULL,
                author_id INTEGER NOT NULL,
                image_url TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (author_id) REFERENCES users(id) ON DELETE SET NULL
            );
        ''')

        # إضافة العمود إذا ما كان موجود (للتوافق مع القديم)
        cur.execute('''
            ALTER TABLE articles 
            ADD COLUMN IF NOT EXISTS author_id INTEGER;
        ''')

        # نقل البيانات من author إلى author_id إذا لسه ما تم النقل
        cur.execute('''
            UPDATE articles a
            SET author_id = u.id
            FROM users u
            WHERE a.author = u.username
              AND a.author_id IS NULL
              AND a.author IS NOT NULL;
        ''')

        # اجعل author_id مطلوب + احذف العمود القديم
        cur.execute('ALTER TABLE articles ALTER COLUMN author_id SET NOT NULL;')
        cur.execute('ALTER TABLE articles DROP COLUMN IF EXISTS author;')

        # جدول التعليقات (تأكد من وجود user_id)
        cur.execute('''
            CREATE TABLE IF NOT EXISTS comments (
                id SERIAL PRIMARY KEY,
                article_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                content TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (article_id) REFERENCES articles(id) ON DELETE CASCADE,
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
            );
        ''')

        print("تم تهيئة قاعدة البيانات بنجاح!")
    except Exception as e:
        print(f"خطأ في init_database: {e}")
    finally:
        if conn:
            conn.close()