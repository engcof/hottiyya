# core/templates.py
from fastapi.templating import Jinja2Templates
import markupsafe

templates = Jinja2Templates(directory="templates")

# فلتر تحويل \n إلى <br> بأمان ضد XSS
def newline_to_br(text):
    if text is None:
        return ""
    escaped = markupsafe.escape(text)
    return markupsafe.Markup(escaped.replace('\n', '<br>'))

# تسجيل الفلتر
templates.env.filters['newline_to_br'] = newline_to_br