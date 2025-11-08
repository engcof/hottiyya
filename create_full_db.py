import os
import sqlite3
import bcrypt

# --------------------------------------
# 1️⃣ تجهيز قاعدة البيانات
# --------------------------------------
os.makedirs("database", exist_ok=True)
db_path = "database/family_tree.db"

if os.path.exists(db_path):
    print("⚠️ قاعدة البيانات موجودة مسبقًا، لم يتم التعديل.")
    exit()


conn = sqlite3.connect(db_path)
cursor = conn.cursor()
cursor.execute("PRAGMA foreign_keys = ON;")


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
# 3️⃣ إنشاء الجداول
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
    # إنشاء الجداول
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS family_info (
            id INTEGER PRIMARY KEY AUTOINCREMENT,       
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
    # إنشاء الجداول
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS family_picture (
            id INTEGER PRIMARY KEY AUTOINCREMENT,       
            code_pic TEXT,
            pic_path TEXT,
            picture BLOB,
            FOREIGN KEY(code_pic) REFERENCES family_name(code)       
        );
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS articles (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            content TEXT NOT NULL,
            author TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        );
    ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS comments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            article_id INTEGER,
            username TEXT,
            content TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(article_id) REFERENCES articles(id)
        );
    ''')

    cursor.execute('''
    CREATE TABLE IF NOT EXISTS logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT NOT NULL,
        action TEXT NOT NULL,
        target TEXT,
        timestamp TEXT DEFAULT (datetime('now','localtime'))
    );
    ''')

    cursor.execute('''
    CREATE TABLE IF NOT EXISTS news (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        title TEXT NOT NULL,
        content TEXT NOT NULL,
        image_url TEXT,
        video_url TEXT,
        author TEXT,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP
    );
    ''')

    # جدول المستخدمين
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE NOT NULL,
        password TEXT NOT NULL,
        role TEXT CHECK(role IN ('admin', 'manager', 'user')) DEFAULT 'user'
    );
    """)

    # جدول الصلاحيات
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS permissions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT UNIQUE NOT NULL,
        description TEXT
    );
    """)

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
        ("add_member", "إضافة عضو جديد في شجرة العائلة"),
        ("edit_member", "تعديل بيانات الأعضاء"),
        ("delete_member", "حذف الأعضاء من الشجرة"),

        # المقالات
        ("add_article", "إضافة مقال جديد"),
        ("edit_article", "تعديل المقالات"),
        ("delete_article", "حذف المقالات"),

        # الأخبار
        ("add_news", "إضافة خبر جديد"),
        ("edit_news", "تعديل الأخبار"),
        ("delete_news", "حذف الأخبار"),

        # التعليقات
        ("add_comment", "إضافة تعليق"),
        ("delete_comment", "حذف تعليق"),

        # السجل
        ("view_logs", "عرض سجل النشاطات"),
    ]

    for name, desc in permissions_list:
        cursor.execute("INSERT OR IGNORE INTO permissions (name, description) VALUES (?, ?)", (name, desc))


    # --------------------------------------
    # 5️⃣ إضافة المستخدمين الافتراضيين
    # --------------------------------------
    def add_user(username, password, role):
        cursor.execute("SELECT id FROM users WHERE username = ?", (username,))
        if not cursor.fetchone():
            cursor.execute(
                "INSERT INTO users (username, password, role) VALUES (?, ?, ?)",
                (username, hash_password(password), role)
            )
            conn.commit()

    add_user("admin", "123", "admin")
    add_user("manager", "123", "manager")
    add_user("user", "123", "user")

    # مثال التحقق من كلمة مرور مستخدم:
    cursor.execute("SELECT password FROM users WHERE username = 'admin'")
    hashed_pw = cursor.fetchone()[0]
    if check_password("admin123", hashed_pw):
        print("✅ كلمة مرور الأدمن صحيحة")
    else:
        print("❌ كلمة مرور الأدمن خاطئة")

    # --------------------------------------
    # 6️⃣ ربط المستخدمين بالصلاحيات
    # --------------------------------------

    def give_all_permissions(username):
        """إعطاء جميع الصلاحيات للمستخدم (مثل الأدمن)"""
        cursor.execute("SELECT id FROM users WHERE username = ?", (username,))
        user = cursor.fetchone()
        if not user:
            return
        user_id = user[0]
        cursor.execute("SELECT id FROM permissions")
        for (perm_id,) in cursor.fetchall():
            cursor.execute("INSERT OR IGNORE INTO user_permissions (user_id, permission_id) VALUES (?, ?)", (user_id, perm_id))
        conn.commit()


    def give_manager_permissions(username):
        """إعطاء المدير صلاحيات محددة (تحرير بدون حذف)"""
        cursor.execute("SELECT id FROM users WHERE username = ?", (username,))
        user = cursor.fetchone()
        if not user:
            return
        user_id = user[0]
        cursor.execute("SELECT id FROM permissions WHERE name LIKE 'add_%' OR name LIKE 'edit_%'")
        for (perm_id,) in cursor.fetchall():
            cursor.execute("INSERT OR IGNORE INTO user_permissions (user_id, permission_id) VALUES (?, ?)", (user_id, perm_id))
        conn.commit()


    def give_user_permissions(username):
        """صلاحيات عرض محدودة"""
        cursor.execute("SELECT id FROM users WHERE username = ?", (username,))
        user = cursor.fetchone()
        if not user:
            return
        user_id = user[0]
        cursor.execute("SELECT id FROM permissions WHERE name IN ('add_comment')")
        for (perm_id,) in cursor.fetchall():
            cursor.execute("INSERT OR IGNORE INTO user_permissions (user_id, permission_id) VALUES (?, ?)", (user_id, perm_id))
        conn.commit()


    # تطبيق الصلاحيات على المستخدمين
    give_all_permissions("admin")
    give_manager_permissions("manager")
    give_user_permissions("user")

   


    conn.commit()
   
   

except Exception as e:
    print(f"⚠️ حدث خطأ أثناء إعداد القاعدة: {e}")    

# --------------------------------------
# 7️⃣ اختبار: طباعة بيانات
# --------------------------------------
print("\n✅ تم إنشاء قاعدة البيانات والصلاحيات بنجاح.\n")

print("🧑‍💻 المستخدمون:")
for row in cursor.execute("SELECT id, username, role FROM users"):
    print(row)

print("\n🔐 الصلاحيات:")
for row in cursor.execute("SELECT id, name FROM permissions"):
    print(row)

print("\n🔗 ربط المستخدمين بالصلاحيات:")
for row in cursor.execute("""
SELECT u.username, p.name
FROM user_permissions up
JOIN users u ON up.user_id = u.id
JOIN permissions p ON up.permission_id = p.id
ORDER BY u.username
"""):
    print(row)

conn.commit()
conn.close()
