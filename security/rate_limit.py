from datetime import datetime, timedelta
from typing import Dict, Any, Optional
from fastapi import Request, HTTPException, status

class RateLimitService:
    # =======================================================
    # إعدادات تقييد المعدل الافتراضية
    # =======================================================
    MAX_ATTEMPTS = 5
    LOCKOUT_DURATION = timedelta(minutes=5)
    
    # الذاكرة المؤقتة لتتبع المحاولات (Key -> بيانات المحاولة)
    _attempt_tracker: Dict[str, Dict[str, Any]] = {}

    @classmethod
    def initialize_rate_limiter(cls) -> None:
        """إعادة تهيئة وتفريغ ذاكرة تتبع المحاولات."""
        cls._attempt_tracker = {}
        print("🚀 تم تهيئة وتنظيف نظام تقييد المعدل الذكي بنجاح.")

    @staticmethod
    def get_client_ip(request: Request) -> str:
        """الحصول على عنوان IP الحقيقي للعميل، مع مراعاة خوادم الـ Proxy (مثل Cloudflare أو Render)."""
        forwarded = request.headers.get("x-forwarded-for")
        if forwarded:
            # في حال وجود سلسلة من الـ IPs عبر الـ Proxy، نأخذ الأول دائماً وهو العميل الحقيقي
            return forwarded.split(",")[0].strip()
        return request.client.host if request.client else "127.0.0.1"

    @classmethod
    def rate_limit_attempt(cls, key: str) -> None:
        """
        تطبيق تقييد المعدل على أساس مفتاح مخصص (مثل IP للعميل، أو معرف المستخدم User ID).
        يرفع HTTPException برمز 429 في حال تخطي الحد المسموح.
        """
        now = datetime.now()

        if key in cls._attempt_tracker:
            attempt_data = cls._attempt_tracker[key]
            last_attempt_time = attempt_data['last_attempt']
            attempts_count = attempt_data['count']

            # 1. تحقق مما إذا كان المستخدم داخل فترة الحظر (Lockout) حالياً
            if attempts_count >= cls.MAX_ATTEMPTS and (now - last_attempt_time) < cls.LOCKOUT_DURATION:
                time_left = cls.LOCKOUT_DURATION - (now - last_attempt_time)
                seconds_left = max(int(time_left.total_seconds()), 1)
                
                # رفع الخطأ الأمني القياسي مع إرجاع رأس Retry-After لإعلام المتصفح بفترة الانتظار
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail=f"تم تجاوز الحد الأقصى للمحاولات المسموحة. يرجى الانتظار {seconds_left} ثانية قبل إعادة المحاولة.",
                    headers={"Retry-After": str(seconds_left)}
                )
            
            # 2. إذا انتهت فترة الحظر تماماً، نقوم بإعادة تعيين العداد للبدء من جديد
            elif (now - last_attempt_time) >= cls.LOCKOUT_DURATION:
                cls._attempt_tracker[key] = {'count': 1, 'last_attempt': now}
            
            # 3. إذا لم يصل للحد الأقصى وما زال يحاول في فترة قريبة، نزيد العداد ونحدث وقت آخر محاولة
            else:
                cls._attempt_tracker[key]['count'] += 1
                cls._attempt_tracker[key]['last_attempt'] = now

        else:
            # تسجيل المحاولة الأولى للمفتاح
            cls._attempt_tracker[key] = {'count': 1, 'last_attempt': now}

    @classmethod
    def reset_attempts(cls, key: str) -> None:
        """إعادة تعيين العداد وحذف السجل فوراً بعد عملية نجاح (مثل: تسجيل دخول صحيح، أو تغيير ناجح لكلمة السر)."""
        if key in cls._attempt_tracker:
            del cls._attempt_tracker[key]