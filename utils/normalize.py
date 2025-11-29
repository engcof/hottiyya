import re

def normalize_arabic(text):
    if not text:
        return text

    # إزالة التشكيل
    text = re.sub(r'[\u0617-\u061A\u064B-\u0652]', '', text)

    # توحيد الألف
    text = re.sub(r'[إأآا]', 'ا', text)

    # توحيد الياء والألف المقصورة
    text = text.replace("ى", "ي")

    # توحيد الهاء والتاء المربوطة
    text = text.replace("ة", "ه")

    return text
