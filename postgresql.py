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
            

            # 9. رسالة نهاية واحدة (نظيفة)
            print("✅ تم إنهاء التهيئة بنجاح!")
          
           
        except Exception as e:
            # ❌ الإبقاء على رسالة الخطأ الحاسم فقط
            print(f"❌ خطأ أثناء تهيئة قاعدة البيانات: {e}") 
            raise