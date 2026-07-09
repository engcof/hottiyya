# security/hash.py
import bcrypt
from typing import Optional

class HashService:

    @staticmethod
    def hash_password(password: Optional[str]) -> str:
        """
        تشفير كلمة المرور بأمان باستخدام خوارزمية bcrypt مع توليد ملح (Salt) تلقائي.
        معالجة دفاعية: إذا كانت كلمة المرور فارغة، يتم إرجاع نص فارغ لمنع انهيار السيرفر.
        """
        if not password:
            return ""
        
        try:
            # تحويل النص إلى Bytes وتشفيره ثم إعادته كـ string
            pwd_bytes = password.encode('utf-8')
            salt = bcrypt.gensalt()
            hashed_bytes = bcrypt.hashpw(pwd_bytes, salt)
            return hashed_bytes.decode('utf-8')
        except Exception as e:
            print(f"❌ Error hashing password: {e}")
            return ""

    @staticmethod
    def check_password(password: Optional[str], hashed: Optional[str]) -> bool:
        """
        التحقق من مطابقة كلمة المرور المدخلة مع الهاش المخزن في قاعدة البيانات.
        حماية أمنية ودفاعية مسبقة ضد القيم الفارغة.
        """
        if not password or not hashed:
            return False
            
        try:
            return bcrypt.checkpw(password.encode('utf-8'), hashed.encode('utf-8'))
        except Exception as e:
            # الحماية من الأخطاء في حال كان الهاش القديم في القاعدة تالفاً أو بصيغة غير مدعومة
            print(f"⚠️ Error checking password compatibility: {e}")
            return False