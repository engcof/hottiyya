# core/templates.py
from fastapi.templating import Jinja2Templates
import markupsafe

# 1. تهيئة كائن القوالب وتحديد المجلد الرئيسي
templates = Jinja2Templates(directory="templates")

# ========================================================
# 2. تعريف فلاتر Jinja2 المخصصة (Custom Filters)
# ========================================================

def newline_to_br_filter(text: str) -> markupsafe.Markup:
    """
    فلتر مخصص لتحويل السطور الجديدة (\n) إلى وسم <br> 
    مع الحفاظ على أمان النص ومنع هجمات XSS باستخدام escape.
    """
    if text is None:
        return markupsafe.Markup("")
    
    escaped = markupsafe.escape(text)
    return markupsafe.Markup(escaped.replace('\n', '<br>'))


# ========================================================
# 3. تسجيل الفلاتر داخل بيئة Jinja2
# ========================================================
templates.env.filters['newline_to_br'] = newline_to_br_filter

# (مستقبلاً) إذا أضفت أي فلتر آخر، قم بتسجيله هنا كالتالي:
# templates.env.filters['format_date'] = format_date_filter