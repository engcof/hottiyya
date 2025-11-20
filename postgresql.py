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

            # 1. إذا كان العمود type موجود → نغيّر اسمه إلى relation
            #     إذا ما كانش موجود → نتجاهل الخطأ ونكمل
            try:
                cur.execute('ALTER TABLE family_name RENAME COLUMN type TO relation;')
                print("تم تغيير اسم العمود: type → relation")
            except psycopg2.errors.UndefinedColumn:
                print("العمود 'type' غير موجود (تم تغييره مسبقًا أو ما وُجد أصلاً) → تم التخطي")
            except Exception as e:
                print(f"تحذير: مشكلة في RENAME (ربما تم التغيير من قبل): {e}")

            # 2. إضافة nick_name إذا ما كانش موجود
            cur.execute('ALTER TABLE family_name ADD COLUMN IF NOT EXISTS nick_name TEXT;')
            print("تم التأكد من وجود عمود nick_name")

            # 3. إضافة status في family_info إذا ما كانش موجود
            cur.execute('''
                ALTER TABLE family_info 
                ADD COLUMN IF NOT EXISTS status TEXT 
                CHECK (status IN ('حي', 'حية', 'متوفي', 'متوفية'))
            ''')
            print("تم التأكد من وجود عمود status مع القيود")

            print("تم تحديث قاعدة البيانات بنجاح!")

        except Exception as e:
            print(f"خطأ غير متوقع أثناء التحديث: {e}")
            raise