import os
import psycopg2
import bcrypt

# --------------------------------------
# 1️⃣ إعداد الاتصال بقاعدة بيانات PostgreSQL
# --------------------------------------
DB_NAME = "family_tree"  # اسم قاعدة البيانات
DB_USER = "engcof"    # اسم المستخدم
DB_PASSWORD = "cof4p@ssw0rd" # كلمة المرور
DB_HOST = "localhost"       # المضيف (عادة localhost)
DB_PORT = "5432"            # المنفذ الافتراضي لـ PostgreSQL

try:
    # الاتصال بقاعدة البيانات
    conn = psycopg2.connect(
        dbname=DB_NAME,
        user=DB_USER,
        password=DB_PASSWORD,
        host=DB_HOST,
        port=DB_PORT
    )
    cursor = conn.cursor()
    cursor.execute("SELECT version();")
    print(cursor.fetchone())
    print("✅ تم الاتصال بقاعدة بيانات PostgreSQL بنجاح.")

except Exception as e:
    print(f"⚠️ فشل الاتصال بقاعدة البيانات: {e}")
    exit()

# --------------------------------------
# 2️⃣ دالة لتشفير كلمات المرور باستخدام bcrypt
# --------------------------------------
def hash_password(password):
    """تشفير كلمة المرور باستخدام bcrypt"""
    hashed = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt())
    return hashed.decode('utf-8')  # نخزنها كنص في قاعدة البيانات

def check_password(password, hashed):
    """التحقق من كلمة المرور"""
    return bcrypt.checkpw(password.encode('utf-8'), hashed.encode('utf-8'))



# --------------------------------------
# 3️⃣ إنشاء الجداول في PostgreSQL
# --------------------------------------
try:
    # إنشاء الجداول
    cursor.execute('''
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
    ''')
    conn.commit()
    cursor.execute('''
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
    ''')
    conn.commit()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS family_picture (
            id SERIAL PRIMARY KEY,       
            code_pic TEXT,
            pic_path TEXT,
            picture BYTEA,
            FOREIGN KEY(code_pic) REFERENCES family_name(code)       
        );
    ''')
    conn.commit()
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
    conn.commit()
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS logs (
        id SERIAL PRIMARY KEY,
        username TEXT NOT NULL,
        action TEXT NOT NULL,
        target TEXT,
        timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    ''')
    conn.commit()
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
    conn.commit()
    # جدول المستخدمين
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS users (
        id SERIAL PRIMARY KEY,
        username TEXT UNIQUE NOT NULL,
        password TEXT NOT NULL,
        role TEXT CHECK(role IN ('admin', 'manager', 'user')) DEFAULT 'user'
    );
    """)
    conn.commit() 
    # جدول الصلاحيات
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS permissions (
        id SERIAL PRIMARY KEY,
        name TEXT UNIQUE NOT NULL,
        description TEXT,
        category TEXT DEFAULT 'عام'          
    );
    """)
    conn.commit()
    # جدول ربط المستخدمين بالصلاحيات (many-to-many)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS user_permissions (
        user_id INTEGER,
        permission_id INTEGER,
        FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE,
        FOREIGN KEY(permission_id) REFERENCES permissions(id) ON DELETE CASCADE,
        PRIMARY KEY (user_id, permission_id)
    );
    """)

    # --------------------------------------
    # 4️⃣ إضافة الصلاحيات الأساسية
    # --------------------------------------
    permissions_list = [
        # شجرة العائلة
        ("add_member", "إضافة عضو جديد في شجرة العائلة", 'الشجرة'),
        ("edit_member", "تعديل بيانات الأعضاء", 'الشجرة'),
        ("delete_member", "حذف الأعضاء من الشجرة", 'الشجرة'),

        # المقالات
        ("add_article", "إضافة مقال جديد", 'المقالات'),
        ("edit_article", "تعديل المقالات", 'المقالات'),
        ("delete_article", "حذف المقالات", 'المقالات'),

        # الأخبار
        ("add_news", "إضافة خبر جديد", 'الأخبار'),
        ("edit_news", "تعديل الأخبار", 'الأخبار'),
        ("delete_news", "حذف الأخبار", 'الأخبار'),

        # التعليقات
        ("add_comment", "إضافة تعليق", 'عام'),
        ("delete_comment", "حذف تعليق", 'عام'),

        # السجل
        ("view_logs", "عرض سجل النشاطات", 'عام'),
    ]

    # إدخال الصلاحيات مع تجاهل التكرار
    for name, desc, categ in permissions_list:
        cursor.execute("""
            INSERT INTO permissions (name, description, category)
            VALUES (%s, %s, %s)
            ON CONFLICT (name) DO NOTHING
        """, (name, desc, categ))


    conn.commit()
    print("✅ تم إنشاء الجداول بنجاح.")

except Exception as e:
    conn.rollback()  # التراجع عن المعاملة إذا حدث خطأ
    print(f"⚠️ حدث خطأ أثناء إنشاء الجداول: {e}")


# إضافة مستخدم
def add_user(username, password, role):
    try:
        cursor.execute("SELECT id FROM users WHERE username = %s", (username,))
        if not cursor.fetchone():
            cursor.execute("""
                INSERT INTO users (username, password, role)
                VALUES (%s, %s, %s)
                ON CONFLICT (username) DO NOTHING
            """, (username, hash_password(password), role))
            conn.commit()
    except Exception as e:
        print(f"⚠️ حدث خطأ أثناء إضافة المستخدم {username}: {e}")

# اختبار إضافة مستخدمين
add_user("admin", "admin123", "admin")
add_user("manager", "manager123", "manager")
add_user("user", "user123", "user")


# --------------------------------------
# 6️⃣ ربط المستخدمين بالصلاحيات
# --------------------------------------

def give_all_permissions(username):
    try:
        cursor.execute("SELECT id FROM users WHERE username = %s", (username,))
        user = cursor.fetchone()
        if not user:
            return
        user_id = user[0]
        cursor.execute("SELECT id FROM permissions")
        for (perm_id,) in cursor.fetchall():
            cursor.execute("""
                INSERT INTO user_permissions (user_id, permission_id)
                VALUES (%s, %s)
                ON CONFLICT (user_id, permission_id) DO NOTHING
            """, (user_id, perm_id))
        conn.commit()
    except Exception as e:
        conn.rollback()  # التراجع في حالة حدوث خطأ
        print(f"⚠️ حدث خطأ أثناء إعطاء جميع الصلاحيات للمستخدم {username}: {e}")






# تطبيق الصلاحيات على المستخدمين
give_all_permissions("admin")


# اختبار إضافة مستخدم وصلاحيات
try:
    cursor.execute("SELECT id, username, role FROM users")
    for row in cursor.fetchall():
        print(row)

    cursor.execute("SELECT id, name FROM permissions")
    for row in cursor.fetchall():
        print(row)

    cursor.execute("""
        SELECT u.username, p.name
        FROM user_permissions up
        JOIN users u ON up.user_id = u.id
        JOIN permissions p ON up.permission_id = p.id
        ORDER BY u.username
    """)
    for row in cursor.fetchall():
        print(row)
except Exception as e:
    print(f"⚠️ حدث خطأ أثناء استعراض البيانات: {e}")

finally:
    cursor.close()
    conn.close()

