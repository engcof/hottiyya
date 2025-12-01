from datetime import datetime, timedelta
from fastapi import Request, HTTPException, status
from typing import Dict, Any

# تخزين مؤقت لمحاولات الفاشلة (Key -> بيانات المحاولة).
# Key يمكن أن يكون IP لتسجيل الدخول أو User ID لتغيير كلمة السر.
attempt_tracker: Dict[str, Any] = {}

# إعدادات تقييد المعدل
MAX_ATTEMPTS = 5
LOCKOUT_DURATION = timedelta(minutes=5)

def initialize_rate_limiter():
    """تهيئة مبدئية (لا تفعل شيئًا في هذا المثال البسيط)"""
    print("تم تهيئة نظام تقييد المعدل البسيط.")
    global attempt_tracker
    attempt_tracker = {}

def get_client_ip(request: Request) -> str:
    """الحصول على عنوان IP للعميل، مع مراعاة Proxy (مثل Render)"""
    return request.headers.get("x-forwarded-for") or request.client.host

def rate_limit_attempt(key: str):
    """
    يطبق تقييد المعدل على أساس مفتاح (IP أو User ID).
    """
    now = datetime.now()

    if key in attempt_tracker:
        attempt_data = attempt_tracker[key]
        last_attempt_time = attempt_data['last_attempt']
        attempts_count = attempt_data['count']

        # 1. تحقق من انتهاء فترة القفل
        if attempts_count >= MAX_ATTEMPTS and (now - last_attempt_time) < LOCKOUT_DURATION:
            time_left = LOCKOUT_DURATION - (now - last_attempt_time)
            # 💡 يتم إرجاع رأس Retry-After في HTTP 429
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"تم تجاوز الحد الأقصى للمحاولات. يرجى الانتظار {time_left.seconds} ثانية قبل المحاولة مرة أخرى.",
                headers={"Retry-After": str(time_left.seconds)}
            )
        
        # 2. إذا انتهت فترة القفل، إعادة تعيين العداد
        elif (now - last_attempt_time) >= LOCKOUT_DURATION:
            attempt_tracker[key] = {'count': 1, 'last_attempt': now}
        
        # 3. زيادة العداد إذا لم يكن مقفولاً
        else:
            attempt_tracker[key]['count'] += 1
            attempt_tracker[key]['last_attempt'] = now

    else:
        # أول محاولة
        attempt_tracker[key] = {'count': 1, 'last_attempt': now}

def reset_attempts(key: str):
    """إعادة تعيين عداد المحاولات الفاشلة بعد عملية ناجحة (تسجيل دخول، تغيير كلمة سر)."""
    if key in attempt_tracker:
        del attempt_tracker[key]        