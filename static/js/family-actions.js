/**
 * سكربت إدارة أعضاء الشجرة - موقع الحوطية
 */

document.addEventListener('DOMContentLoaded', () => {
    const codeInput = document.getElementById('memberCode');
    const statusIcon = document.getElementById('codeStatusIcon');
    const feedback = document.getElementById('codeFeedback');

    if (codeInput) {
        
        // 1. ميزة الاقتراح التلقائي والاختصار المدمجة والمحمية من التكرار
        codeInput.addEventListener('input', async function(e) {
            let val = e.target.value.trim().toUpperCase();
            e.target.value = val;

            // الحالة أ: إذا كتب المستخدم حرفاً واحداً كبادئة أولية (مثل: A)
            if (val.length === 1 && /^[A-Z]$/.test(val)) {
                try {
                    const res = await fetch(`/family/get-next-code?letter=${val}`);
                    const data = await res.json();
                    if (data.next_code) {
                        e.target.value = data.next_code;
                        // تحديد النص المتبقي المكتوب تلقائياً لتسهيل المسح أو التعديل
                        e.target.setSelectionRange(1, data.next_code.length);
                        validateCode(data.next_code);
                    }
                } catch (err) { 
                    console.error("Error fetching next code by letter:", err); 
                }
            }
            // الحالة ب: إذا كتب المستخدم بادئة كاملة أو مخصصة (مثل: A0-005) طولها 6 محارف وتحتوي على شرطة
            else if (val.length === 6 && val.includes('-')) {
                try {
                    const response = await fetch(`/family/get-next-code?prefix=${val}`);
                    const data = await response.json();
                    if (data.next_code) {
                        e.target.value = data.next_code;
                        validateCode(data.next_code); 
                    }
                } catch (error) {
                    console.error("خطأ في جلب الكود بالبادئة:", error);
                }
            }
        });

        // 2. التحقق الفوري عند خروج مؤشر الكتابة من الحقل (Blur)
        codeInput.addEventListener('blur', function() {
            validateCode(this.value);
        });
    }

    /**
     * دالة التحقق من توفر الكود عبر السيرفر وتحديث الواجهة بصرياً
     */
    async function validateCode(code) {
        if (code.length < 3 || !statusIcon || !feedback || !codeInput) return;

        try {
            const response = await fetch(`/family/check-code-availability?code=${code}`);
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