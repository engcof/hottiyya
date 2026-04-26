# core/templates.py
from fastapi.templating import Jinja2Templates
import markupsafe
from services.notification import get_unread_notification_count
from utils.has_permissions import can

templates = Jinja2Templates(directory="templates")

# دالة مساعدة لتجهيز سياق البيانات (Context)
def get_global_context(request):
    user = request.session.get("user")
    return {
        "request": request,
        "user": user,
        "can_view": can(user, "view_tree") if user else False,
        "unread_count": get_unread_notification_count(user["id"]) if user else 0
    }

# فلتر تحويل \n إلى <br>
def newline_to_br(text):
    if text is None:
        return ""
    escaped = markupsafe.escape(text)
    return markupsafe.Markup(escaped.replace('\n', '<br>'))

templates.env.filters['newline_to_br'] = newline_to_br