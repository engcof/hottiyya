
/**
 * سكربت إدارة أعضاء الشجرة - موقع الحوطية - النسخة المؤمنة والمحسنة
 */
document.addEventListener('DOMContentLoaded', () => {
    const codeInput = document.getElementById('memberCode');
    const statusIcon = document.getElementById('codeStatusIcon');
    const feedback = document.getElementById('codeFeedback');
    
    // 🔒 وحدة التحكم في الإلغاء لمنع سباق طلبات الشبكة العشوائية (Race Conditions)
    let abortController = null;

    if (codeInput) {
        codeInput.addEventListener('input', async function(e) {
            let val = e.target.value.trim().toUpperCase();
            e.target.value = val;

            // إلغاء الطلب المعلق السابق إن وجد فوراً بسبب إدخال حرف جديد
            if (abortController) abortController.abort();
            abortController = new AbortController();
            const { signal } = abortController;

            // الحالة أ: إذا كتب المستخدم حرفاً واحداً كبادئة أولية (مثل: A)
            if (val.length === 1 && /^[A-Z]$/.test(val)) {
                try {
                    const res = await fetch(`/family/get-next-code?prefix=${val}`, { signal });
                    const data = await res.json();
                    if (data.next_code) {
                        e.target.value = data.next_code;
                        e.target.setSelectionRange(1, data.next_code.length);
                        validateCode(data.next_code);
                    }
                } catch (err) { 
                    if (err.name !== 'AbortError') console.error("Error fetching next code by letter:", err); 
                }
            }
            // الحالة ب: إذا كتب المستخدم بادئة كاملة أو مخصصة طولها 6 محارف وتحتوي على شرطة
            else if (val.length === 6 && val.includes('-')) {
                try {
                    const response = await fetch(`/family/get-next-code?prefix=${val}`, { signal });
                    const data = await response.json();
                    if (data.next_code) {
                        e.target.value = data.next_code;
                        validateCode(data.next_code); 
                    }
                } catch (error) {
                    if (error.name !== 'AbortError') console.error("خطأ في جلب الكود بالبادئة:", error);
                }
            }
        });

        codeInput.addEventListener('blur', function() {
            validateCode(this.value);
        });
    }

    async function validateCode(code) {
        if (code.length < 3 || !statusIcon || !feedback || !codeInput) return;

        try {
            const response = await fetch(`/family/check-code-availability?code=${encodeURIComponent(code)}`);
            const data = await response.json();

            if (data.available) {
                statusIcon.innerHTML = '✅';
                feedback.innerText = 'هذا الكود متاح للاستخدام';
                feedback.style.color = '#10b981';
                codeInput.style.borderColor = '#10b981';
            } else {
                statusIcon.innerHTML = '❌';
                feedback.innerText = 'عذراً، هذا الكود محجوز مسبقاً!';
                feedback.style.color = '#ef4444';
                codeInput.style.borderColor = '#ef4444';
            }
        } catch (err) {
            console.error("خطأ في التحقق من إتاحة الكود:", err);
        }
    }
});