# init_db.py
# init_db.py
import os
import sys
import logging

# إجبار الـ logging على stdout
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger(__name__)

logger.info("بدء تنفيذ init_db.py...")

# جلب المتغيرات
DB_HOST = os.getenv("DB_HOST")
DB_NAME = os.getenv("DB_NAME")
DB_USER = os.getenv("DB_USER")
DB_PASSWORD = os.getenv("DB_PASSWORD")

logger.info(f"DB_HOST: {DB_HOST}")
logger.info(f"DB_NAME: {DB_NAME}")
logger.info(f"DB_USER: {DB_USER}")

if not all([DB_HOST, DB_NAME, DB_USER, DB_PASSWORD]):
    logger.error("متغيرات قاعدة البيانات مفقودة!")
    sys.exit(1)

try:
    import psycopg2
    from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT
    import bcrypt

    logger.info("استيراد المكتبات ناجح")

    conn = psycopg2.connect(
        host=DB_HOST,
        dbname=DB_NAME,
        user=DB_USER,
        password=DB_PASSWORD,
        port="5432",
        sslmode="require"
    )
    conn.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
    cursor = conn.cursor()
    logger.info("تم الاتصال بقاعدة البيانات بنجاح!")

    # تحقق من وجود جدول users
    cursor.execute("SELECT to_regclass('public.users');")
    if cursor.fetchone()[0]:
        logger.info("الجداول موجودة بالفعل. تخطي التهيئة.")
        cursor.close()
        conn.close()
        sys.exit(0)

    logger.info("إنشاء الجداول...")

    # === جدول المستخدمين ===
    cursor.execute("""
        CREATE TABLE users (
            id SERIAL PRIMARY KEY,
            username TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL,
            role TEXT CHECK(role IN ('admin', 'manager', 'user')) DEFAULT 'user'
        );
    """)

    # === جدول شجرة العائلة ===
    cursor.execute("""
        CREATE TABLE family_name (
            code TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            f_code TEXT,
            m_code TEXT,
            w_code TEXT,
            h_code TEXT,
            type TEXT CHECK(type IN (
                'ابن', 'ابنة', 'زوج', 'زوجة',
                'ابن زوج', 'ابنة زوج', 'ابن زوجة', 'ابنة زوجة'
            )),
            level INTEGER DEFAULT 0,
            FOREIGN KEY(f_code) REFERENCES family_name(code) ON DELETE SET NULL,
            FOREIGN KEY(m_code) REFERENCES family_name(code) ON DELETE SET NULL,
            FOREIGN KEY(w_code) REFERENCES family_name(code) ON DELETE SET NULL,
            FOREIGN KEY(h_code) REFERENCES family_name(code) ON DELETE SET NULL      
           
        );
    """)
    cursor.execute("""
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
            FOREIGN KEY(code_info) REFERENCES family_name(code)       
        );
    """) 
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS family_picture (
            id SERIAL PRIMARY KEY,       
            code_pic TEXT,
            pic_path TEXT,
            picture BYTEA,
            FOREIGN KEY(code_pic) REFERENCES family_name(code)       
        );
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS articles (
            id SERIAL PRIMARY KEY,
            title TEXT NOT NULL,
            content TEXT NOT NULL,
            author TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
    ''')
    conn.commit()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS comments (
            id SERIAL PRIMARY KEY,
            article_id INTEGER,
            username TEXT,
            content TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(article_id) REFERENCES articles(id)
        );
    ''')
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS news (
        id SERIAL PRIMARY KEY,
        title TEXT NOT NULL,
        content TEXT NOT NULL,
        image_url TEXT,
        video_url TEXT,
        author TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    ''')
    # === جدول السجلات (logs) ===
    cursor.execute("""
        CREATE TABLE logs (
            id SERIAL PRIMARY KEY,
            user_id INTEGER REFERENCES users(id),
            action TEXT NOT NULL,
            timestamp TIMESTAMP DEFAULT NOW()
        );
    """)

    # === جدول الصلاحيات ===
    cursor.execute("""
        CREATE TABLE permissions (
            id SERIAL PRIMARY KEY,
            name TEXT UNIQUE NOT NULL,
            description TEXT
        );
    """)

    # === جدول ربط المستخدمين بالصلاحيات ===
    cursor.execute("""
        CREATE TABLE user_permissions (
            user_id INTEGER REFERENCES users(id),
            permission_id INTEGER REFERENCES permissions(id),
            PRIMARY KEY (user_id, permission_id)
        );
    """)

    # === إضافة صلاحيات افتراضية ===
    permissions = [
        ("add_member", "إضافة عضو في الشجرة"),
        ("edit_member", "تعديل عضو"),
        ("delete_member", "حذف عضو"),
        ("view_logs", "عرض السجلات"),
        ("manage_users", "إدارة المستخدمين")
    ]
    for name, desc in permissions:
        cursor.execute("""
            INSERT INTO permissions (name, description) 
            VALUES (%s, %s) ON CONFLICT (name) DO NOTHING
        """, (name, desc))

    # === إضافة المستخدم admin ===
    hashed = bcrypt.hashpw("admin123".encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
    cursor.execute("""
        INSERT INTO users (username, password, role) 
        VALUES (%s, %s, %s) ON CONFLICT (username) DO NOTHING
    """, ("admin", hashed, "admin"))

    # === منح admin كل الصلاحيات ===
    cursor.execute("SELECT id FROM users WHERE username = 'admin'")
    admin_id = cursor.fetchone()
    if admin_id:
        cursor.execute("SELECT id FROM permissions")
        perm_ids = cursor.fetchall()
        for (perm_id,) in perm_ids:
            cursor.execute("""
                INSERT INTO user_permissions (user_id, permission_id) 
                VALUES (%s, %s) ON CONFLICT DO NOTHING
            """, (admin_id[0], perm_id))

    logger.info("تم إنشاء جميع الجداول وإعداد admin بنجاح!")
    cursor.close()
    conn.close()

except Exception as e:
    logger.error(f"فشل في init_db.py: {e}")
    import traceback
    logger.error(traceback.format_exc())
    sys.exit(1)