# analytics_service.py
import uuid
import re
from datetime import datetime, timedelta
from typing import List, Dict, Tuple, Optional
from fastapi import Request
from postgresql import get_db_context

class AnalyticsService:

    # =======================================================
    # 1. إدارة الزيارات والجلسات الحية (Core Analytics)
    # =======================================================

    @staticmethod
    def log_visit(request: Request, user: Optional[Dict] = None) -> None:
        """تسجيل الزيارة بطريقة آمنة وسريعة مع ON CONFLICT وتحديث الإجمالي للزوار الجدد."""
        session_id = request.session.get("session_id")
        if not session_id:
            session_id = str(uuid.uuid4())
            request.session["session_id"] = session_id

        user_id = user.get("id") if user and user.get("id") else None
        username = user.get("username") if user and user.get("username") else None

        ip = request.client.host
        path = request.url.path
        user_agent = request.headers.get("user-agent", "unknown")

        try:
            with get_db_context() as conn:
                with conn.cursor() as cur:
                    # 1. محاولة إدراج/تحديث الجلسة الحالية
                    cur.execute("""
                        INSERT INTO visits (
                            session_id, user_id, username, ip, user_agent, path
                        ) VALUES (%s, %s, %s, %s, %s, %s)
                        ON CONFLICT (session_id) DO UPDATE SET
                            timestamp = NOW(),
                            user_id = EXCLUDED.user_id,
                            username = EXCLUDED.username,
                            ip = EXCLUDED.ip,
                            path = EXCLUDED.path
                        RETURNING xmax = 0;
                    """, (session_id, user_id, username, ip, user_agent, path))
                    
                    is_new_session = cur.fetchone()[0]

                    # 2. تحديث العداد الإجمالي فقط إذا كانت الجلسة تنشأ لأول مرة
                    if is_new_session:
                        cur.execute("""
                            UPDATE stats_summary
                            SET value = value + 1
                            WHERE key = 'total_visitors_count';
                        """)

                conn.commit()
        except Exception as e:
            if "uniq_session_id" in str(e) or "ON CONFLICT" in str(e):
                print(f"⚠️ تحذير مؤقت (أول مرة فقط): {e}")
            else:
                print(f"❌ خطأ غير متوقع في AnalyticsService.log_visit: {e}")

    @staticmethod
    def get_total_visitors() -> int:
        """جلب العدد الإجمالي الحقيقي من جدول إحصائيات النظام الخفيف."""
        try:
            with get_db_context() as conn:
                with conn.cursor() as cur:
                    cur.execute("SELECT value FROM stats_summary WHERE key = 'total_visitors_count'")
                    result = cur.fetchone()
                    return result[0] if result else 0
        except Exception:
            return 0

    @staticmethod
    def get_today_visitors() -> int:
        """حساب عدد الزوار الفريدين لليوم الحالي."""
        today = datetime.now().date()
        try:
            with get_db_context() as conn:
                with conn.cursor() as cur:
                    cur.execute("SELECT COUNT(DISTINCT session_id) FROM visits WHERE DATE(timestamp) = %s", (today,))
                    return cur.fetchone()[0] or 0
        except Exception:
            return 0

    @staticmethod
    def get_online_users() -> List[Dict]:
        """جلب المستخدمين المتواجدين حالياً (خلال آخر 10 دقائق)."""
        threshold = datetime.now() - timedelta(minutes=10)
        try:
            with get_db_context() as conn:
                with conn.cursor() as cur:
                    cur.execute("""
                        SELECT DISTINCT ON (session_id) username, timestamp
                        FROM visits
                        WHERE timestamp > %s
                        ORDER BY session_id, timestamp DESC
                    """, (threshold,))
                    rows = cur.fetchall()
                    return [
                        {
                            "username": row[0] or "زائر مجهول",
                            "last_seen": row[1].strftime("%H:%M")
                        }
                        for row in rows
                    ]
        except Exception:
            return []

    @staticmethod
    def get_online_count() -> int:
        """الحصول على عدد المتواجدين أونلاين لحظياً."""
        return len(AnalyticsService.get_online_users())


    # =======================================================
    # 2. دوال تتبع عمليات الأمان للمستخدمين (Security Logs)
    # =======================================================

    @staticmethod
    def get_user_security_log(user_id: int, limit: int = 5) -> List[Dict]:
        """جلب سجل النشاط الأمني الأخير لمستخدم معين (أجهزة، مسارات، أيزو وآي بي)."""
        try:
            with get_db_context() as conn:
                with conn.cursor() as cur:
                    cur.execute("""
                        SELECT ip, user_agent, timestamp, path
                        FROM visits
                        WHERE user_id = %s
                        ORDER BY timestamp DESC
                        LIMIT %s
                    """, (user_id, limit))
                    rows = cur.fetchall()
                    
                    logs = []
                    for row in rows:
                        ua = row[1].lower()
                        
                        # تمييز أنظمة التشغيل بدقة
                        if "windows" in ua: os_name = "Windows"
                        elif "macintosh" in ua or "mac os" in ua: os_name = "Mac"
                        elif "android" in ua: os_name = "Android"
                        elif "iphone" in ua or "ipad" in ua: os_name = "iOS"
                        else: os_name = "جهاز غير معروف"

                        # تمييز المتصفحات
                        if "chrome" in ua: browser = "Chrome"
                        elif "firefox" in ua: browser = "Firefox"
                        elif "safari" in ua and "chrome" not in ua: browser = "Safari"
                        elif "edge" in ua: browser = "Edge"
                        else: browser = "متصفح الويب"

                        # داخل دالة get_user_security_log في ملف services/analytics.py
                        # ... كود استخراج المتصفح والنظام المعتاد ...

                        # استقراء الحدث الأمني المباشر بناءً على المسار المحقون ذكياً
                        action_text = "تسجيل دخول / تصفح"
                        if "/admin-changed-your-password" in row[3]:
                            action_text = "⚠️ تم تحديث كلمة المرور بواسطة الإدارة بناءً على طلبك"
                        elif "/change-password" in row[3]:
                            action_text = "🔑 تم تغيير كلمة المرور الشخصية (بواسطتك)"
                        elif "/send-message" in row[3]:
                            action_text = "📩 إرسال رسالة"
                        
                        logs.append({
                            "ip": row[0],
                            "device": f"{browser} ({os_name})",
                            "timestamp": row[2],
                            "action": action_text
                        })
                    return logs
        except Exception as e:
            print(f"❌ Error in AnalyticsService.get_user_security_log: {e}")
            return []


    # =======================================================
    # 3. وظائف الإدارة والتحكم والمراقبة (Admin Controls)
    # =======================================================

    @staticmethod
    def log_action(user_id: int, action: str, details: str) -> None:
        """سجل إدارة العمليات الحيوية وتعديل الشجرة داخل لوحة التحكم."""
        try:
            with get_db_context() as conn:
                with conn.cursor() as cur:
                    cur.execute("""
                        INSERT INTO activity_logs (user_id, action, details)
                        VALUES (%s, %s, %s)
                    """, (user_id, action, details))
                conn.commit()
        except Exception as e:
            print(f"❌ Error in AnalyticsService.log_action: {e}")

    @staticmethod
    def get_logged_in_users_history(limit: int = 50) -> List[Dict]:
        """جلب تاريخ الدخول الموحد للمشرف بدون تكرار الحسابات المتقاربة."""
        try:
            with get_db_context() as conn:
                with conn.cursor() as cur:
                    cur.execute("""
                        SELECT DISTINCT ON (user_id) 
                               username, timestamp, user_id
                        FROM visits
                        WHERE user_id IS NOT NULL AND user_id > 0
                        ORDER BY user_id, timestamp DESC
                        LIMIT %s
                    """, (limit,))
                    rows = cur.fetchall()
                    return [
                        {
                            "username": row[0],
                            "timestamp": row[1],
                            "user_id": row[2]
                        }
                        for row in rows
                    ]
        except Exception:
            return []

    @staticmethod
    def get_activity_logs_paginated(page: int = 1, per_page: int = 30) -> Tuple[List[Dict], int]:
        """جلب لوحة سجل نشاطات النظام العامة مع الترقيم التلقائي للصفحات."""
        offset = (page - 1) * per_page
        try:
            with get_db_context() as conn:
                with conn.cursor() as cur:
                    cur.execute("SELECT COUNT(*) FROM activity_logs")
                    total_logs = cur.fetchone()[0]
                    total_pages = (total_logs + per_page - 1) // per_page

                    cur.execute("""
                        SELECT al.id, u.username, al.action, al.details, al.timestamp
                        FROM activity_logs al
                        LEFT JOIN users u ON al.user_id = u.id
                        ORDER BY al.timestamp DESC
                        LIMIT %s OFFSET %s
                    """, (per_page, offset))
                    
                    logs = [
                        {
                            "id": row[0],
                            "username": row[1] or "نظام/محذوف",
                            "action": row[2],
                            "details": row[3],
                            "timestamp": row[4]
                        } for row in cur.fetchall()
                    ]
                    return logs, total_pages
        except Exception:
            return [], 1

    @staticmethod
    def get_login_logs_paginated(page: int = 1, per_page: int = 20) -> Tuple[List[Dict], int]:
        """جلب آخر سجل دخول آمن وغير مكرر لكل مستخدم مع الترقيم."""
        offset = (page - 1) * per_page
        try:
            with get_db_context() as conn:
                with conn.cursor() as cur:
                    cur.execute("SELECT COUNT(DISTINCT user_id) FROM visits WHERE user_id IS NOT NULL AND user_id > 0")
                    total_logs = cur.fetchone()[0]
                    total_pages = (total_logs + per_page - 1) // per_page

                    cur.execute("""
                        SELECT username, timestamp, user_id
                        FROM (
                            SELECT DISTINCT ON (user_id) username, timestamp, user_id
                            FROM visits
                            WHERE user_id IS NOT NULL AND user_id > 0
                            ORDER BY user_id, timestamp DESC
                        ) AS unique_logins
                        ORDER BY timestamp DESC
                        LIMIT %s OFFSET %s
                    """, (per_page, offset))
                    
                    logs = [
                        {
                            "username": row[0],
                            "timestamp": row[1],
                            "user_id": row[2]
                        } for row in cur.fetchall()
                    ]
                    return logs, total_pages
        except Exception:
            return [], 1

    @staticmethod
    def clean_visits_history(days: int = 7) -> None:
        """تنظيف البيانات الدورية المنتهية لتخفيف حجم قاعدة البيانات وصيانتها أوتوماتيكياً."""
        threshold_date = datetime.now() - timedelta(days=days)
        try:
            with get_db_context() as conn:
                with conn.cursor() as cur:
                    cur.execute("DELETE FROM visits WHERE timestamp < %s", (threshold_date,))
                conn.commit()
                print(f"🧹 [تفريغ أمني]: تم مسح الزيارات القديمة الزائدة عن {days} أيام.")
        except Exception as e:
            print(f"❌ خطأ أثناء صيانة السجلات القديمة: {e}")