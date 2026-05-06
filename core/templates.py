# core/templates.py
from fastapi.templating import Jinja2Templates
import markupsafe
from services.notification import get_unread_notification_count
from utils.has_permissions import can

templates = Jinja2Templates(directory="templates")

# فلتر تحويل \n إلى <br>
def newline_to_br(text):
    if text is None:
        return ""
    escaped = markupsafe.escape(text)
    return markupsafe.Markup(escaped.replace('\n', '<br>'))

templates.env.filters['newline_to_br'] = newline_to_br