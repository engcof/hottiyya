import os
import logging
import psycopg2
import bcrypt
from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT

# إعداد logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

host = os.getenv("DB_HOST")
dbname = os.getenv("DB_NAME")
user = os.getenv("DB_USER")
password = os.getenv("DB_PASSWORD")

if not all([host, dbname, user, password]):
    raise EnvironmentError("متغيرات قاعدة البيانات مفقودة!")

logger.info(f"تهيئة قاعدة البيانات: {user}@{host}/{dbname}")



def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')

def check_password(password: str, hashed: str) -> bool:
    return bcrypt.checkpw(password.encode('utf-8'), hashed.encode('utf-8'))

def init_database():
    try:
        logger.info("جاري الاتصال بقاعدة البيانات...")
        conn = psycopg2.connect(
        host=host,
        dbname=dbname,
        user=user,
        password=password,
        port="5432",
        sslmode="require"
)
        conn.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
        cursor = conn.cursor()

        # التحقق من وجود جدول users (لتشغيل مرة واحدة)
        cursor.execute("SELECT COUNT(*) FROM information_schema.tables WHERE table_name = 'users'")
        if cursor.fetchone()[0] > 0:
            logger.info("الجداول موجودة بالفعل. تخطي التهيئة.")
            cursor.close()
            conn.close()
            return

        # إنشاء الجداول (مع تحسينات)
        tables_sql = """
        CREATE TABLE IF NOT EXISTS family_name (
            code TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            f_code TEXT,
            m_code TEXT,
            w_code TEXT,
            h_code TEXT,
            type TEXT CHECK(type IN ('ابن', 'ابنة', 'زوج', 'زوجة', 'ابن زوج', 'ابنة زوج', 'ابن زوجة', 'ابنة زوجة')),
            level INTEGER,
            FOREIGN KEY(f_code) REFERENCES family_name(code) ON DELETE SET NULL,
            FOREIGN KEY(m_code) REFERENCES family_name(code) ON DELETE SET NULL,
            FOREIGN KEY(w_code) REFERENCES family_name(code) ON DELETE SET NULL,
            FOREIGN KEY(h_code) REFERENCES family_name(code) ON DELETE SET NULL
        );

        CREATE TABLE IF NOT EXISTS family_info (
            id SERIAL PRIMARY KEY,
            code_info TEXT,
            gender TEXT,
            d_o_b TEXT,
            d_o_d TEXT,
            email TEXT,
            phone TEXT,
            address TEXT,
            p_o_b TEXT,
            FOREIGN KEY(code_info) REFERENCES family_name(code) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS family_picture (
            id SERIAL PRIMARY KEY,
            code_pic TEXT,
            pic_path TEXT,
            picture BYTEA,
            FOREIGN KEY(code_pic) REFERENCES family_name(code) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS articles (
            id SERIAL PRIMARY KEY,
            title TEXT NOT NULL,
            content TEXT NOT NULL,
            author TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS comments (
            id SERIAL PRIMARY KEY,
            article_id INTEGER,
            username TEXT,
            content TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(article_id) REFERENCES articles(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS logs (
            id SERIAL PRIMARY KEY,
            username TEXT NOT NULL,
            action TEXT NOT NULL,
            target TEXT,
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS news (
            id SERIAL PRIMARY KEY,
            title TEXT NOT NULL,
            content TEXT NOT NULL,
            image_url TEXT,
            video_url TEXT,
            author TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS users (
            id SERIAL PRIMARY KEY,
            username TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL,
            role TEXT CHECK(role IN ('admin', 'manager', 'user')) DEFAULT 'user',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS permissions (
            id SERIAL PRIMARY KEY,
            name TEXT UNIQUE NOT NULL,
            description TEXT,
            category TEXT DEFAULT 'عام'
        );

        CREATE TABLE IF NOT EXISTS user_permissions (
            user_id INTEGER,
            permission_id INTEGER,
            PRIMARY KEY (user_id, permission_id),
            FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE,
            FOREIGN KEY(permission_id) REFERENCES permissions(id) ON DELETE CASCADE
        );
        """
        cursor.execute(tables_sql)

        # إضافة الصلاحيات
        permissions_list = [
            ("add_member", "إضافة عضو جديد في شجرة العائلة", 'الشجرة'),
            ("edit_member", "تعديل بيانات الأعضاء", 'الشجرة'),
            ("delete_member", "حذف الأعضاء من الشجرة", 'الشجرة'),
            ("add_article", "إضافة مقال جديد", 'المقالات'),
            ("edit_article", "تعديل المقالات", 'المقالات'),
            ("delete_article", "حذف المقالات", 'المقالات'),
            ("add_news", "إضافة خبر جديد", 'الأخبار'),
            ("edit_news", "تعديل الأخبار", 'الأخبار'),
            ("delete_news", "حذف الأخبار", 'الأخبار'),
            ("add_comment", "إضافة تعليق", 'عام'),
            ("delete_comment", "حذف تعليق", 'عام'),
            ("view_logs", "عرض سجل النشاطات", 'عام'),
        ]
        for name, desc, cat in permissions_list:
            cursor.execute("""
                INSERT INTO permissions (name, description, category)
                VALUES (%s, %s, %s) ON CONFLICT (name) DO NOTHING
            """, (name, desc, cat))

        # إضافة مستخدمين (مع كلمات مرور آمنة - غيّرها!)
        users = [
            ("admin", "admin123", "admin"),
            ("manager", "manager123", "manager"),
            ("user", "user123", "user"),
        ]
        for username, password, role in users:
            hashed = hash_password(password)
            cursor.execute("""
                INSERT INTO users (username, password, role)
                VALUES (%s, %s, %s) ON CONFLICT (username) DO NOTHING
            """, (username, hashed, role))

        # منح صلاحيات للـ admin
        cursor.execute("SELECT id FROM users WHERE username = %s", ("admin",))
        admin_id = cursor.fetchone()
        if admin_id:
            cursor.execute("SELECT id FROM permissions")
            for (perm_id,) in cursor.fetchall():
                cursor.execute("""
                    INSERT INTO user_permissions (user_id, permission_id)
                    VALUES (%s, %s) ON CONFLICT DO NOTHING
                """, (admin_id[0], perm_id))

        logger.info("✅ تم تهيئة قاعدة البيانات بنجاح!")
        cursor.close()
        conn.close()

    except Exception as e:
        logger.error(f"⚠️ فشل التهيئة: {e}")
        if 'conn' in locals():
            conn.close()
        raise  # أعد رفع الخطأ للمعالجة العليا

if __name__ == "__main__":
    init_database()