# utils/time_utils.py
from datetime import date
from typing import Optional, Dict, Any

class TimeUtils:

    @staticmethod
    def calculate_age_details(d_o_b_str: Optional[str], d_o_d_str: Optional[str]) -> Dict[str, Optional[Any]]:
        """
        تحسب العمر الحالي ومدة الوفاة منذ، وتتحقق من صحة التواريخ المدخلة.
        """
        today = date.today()
        dob = None
        dod = None
        
        # 1. التحقق من تاريخ الميلاد وتحويله بأمان
        try:
            if d_o_b_str is not None: 
                dob = date.fromisoformat(d_o_b_str)
        except ValueError:
            dob = None  # إذا لم تكن بصيغة تاريخ صالحة

        # 2. التحقق من تاريخ الوفاة وتحويله بأمان
        try:
            if d_o_d_str is not None:
                dod = date.fromisoformat(d_o_d_str)
        except ValueError:
            dod = None

        # تجهيز القاموس المبدئي للنتيجة
        result = {
            "age": None,
            "time_since_death": None,
            "has_dob": dob is not None,
            "has_dod": dod is not None,
        }

        # 3. حساب العمر (لشخص لا يزال على قيد الحياة)
        if dob and not dod:
            # حساب العمر: (السنة الحالية - سنة الميلاد) - (هل احتفل بعيد ميلاده هذا العام؟)
            age = today.year - dob.year - ((today.month, today.day) < (dob.month, dob.day))
            result["age"] = age
        
        # 4. حساب مدة الوفاة منذ (في حال وجود تاريخ الوفاة)
        if dod:
            if dod > today:
                 # إذا كان تاريخ الوفاة مستقبليًا (خطأ بيانات)، لا تحسب المدة
                 result["time_since_death"] = "تاريخ الوفاة مستقبلي"
            else:
                diff = today - dod
                days = diff.days
                
                if days < 30:
                    time_since = f"منذ {days} يوم"
                elif days < 365:
                    months = days // 30 
                    time_since = f"منذ {months} شهر"
                else:
                    years = days // 365
                    time_since = f"منذ {years} سنة"
                
                result["time_since_death"] = time_since
                
        return result