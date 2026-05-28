# utils/time_utils.py
from datetime import date
from typing import Optional, Dict, Any

def calculate_age_details(d_o_b_str: Optional[str], d_o_d_str: Optional[str]) -> Dict[str, Optional[Any]]:
    """
    تحسب العمر الحالي ومدة الوفاة منذ.
    """
    today = date.today()
    dob = None
    dod = None
    
    # ========================================================
    # 💡 التعديل هنا: التأكد من أن القيمة ليست None قبل التحويل
    # ========================================================
    try:
        # يجب أن يكون التحقق صريحًا: هل القيمة موجودة (ليست None)؟
        if d_o_b_str is not None: 
            dob = date.fromisoformat(d_o_b_str)
    except ValueError:
        dob = None # إذا لم تكن بصيغة تاريخ صالحة

    try:
        if d_o_d_str is not None:
            dod = date.fromisoformat(d_o_d_str)
    except ValueError:
        dod = None

    result = {
        "age": None,
        # 💡 تم حذف "age_at_death" من القاموس الذي يتم حسابه في Python
        "time_since_death": None,
        "has_dob": dob is not None,
        "has_dod": dod is not None,
    }

    # 1. العمر (لشخص لا يزال على قيد الحياة)
    # يتم الحساب إذا وُجد تاريخ ميلاد ولم يوجد تاريخ وفاة
    if dob and not dod:
        # حساب العمر: (السنة الحالية - سنة الميلاد) - (هل احتفل بعيد ميلاده هذا العام؟ 0/1)
        age = today.year - dob.year - ((today.month, today.day) < (dob.month, dob.day))
        result["age"] = age

    # 💡 تم حذف الخطوة 2: حساب العمر عند الوفاة (لأنه يتم جلبه من DB)
    
    # 3. الوفاة منذ (في حال وجود تاريخ الوفاة)
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
                # حساب الشهور التقريبي
                months = days // 30 
                time_since = f"منذ {months} شهر"
            else:
                # حساب السنوات التقريبي
                years = days // 365
                time_since = f"منذ {years} سنة"
            
            result["time_since_death"] = time_since
            
    return result