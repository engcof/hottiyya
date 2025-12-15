import re

def normalize_arabic(text):
    if not text:
        return text

    # 1. إزالة التشكيل (هذا الجزء عادةً مطلوب لتحسين البحث)
    # ملاحظة: إذا كنت لا تريد إزالة التشكيل، يمكنك حذف هذا السطر.
    # التشكيل: Fathatan, Dammatan, Kasratan, Fatha, Damma, Kasra, Shadda, Sukun
    text = re.sub(r'[\u0617-\u061A\u064B-\u0652]', '', text)

    # 2. توحيد الألف (أ، إ، آ) إلى ألف عادية (ا) - **هذا هو المطلوب**
    text = re.sub(r'[إأآ]', 'ا', text)
    # ملاحظة: حرف 'ا' موجود بالفعل ولا يحتاج للاستبدال

    # ❌ حذف: توحيد الياء والألف المقصورة
    # text = text.replace("ى", "ي") 

    # ❌ حذف: توحيد الهاء والتاء المربوطة
    # text = text.replace("ة", "ه") 

    return text