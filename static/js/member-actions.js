/**
 * سكربت إدارة أعضاء الشجرة - موقع الحوطية
 */
document.getElementById('memberCode').addEventListener('input', async function(e) {
    let val = e.target.value.trim().toUpperCase();
    e.target.value = val;

    // نقترح الكود الجديد عندما يكتب المستخدم البادئة كاملة (مثال: A0-005)
    // طول البادئة عادة يكون 6 محارف
    if (val.length === 6 && val.includes('-')) {
        try {
            const response = await fetch(`/names/get-next-code?prefix=${val}`);
            const data = await response.json();
            if (data.next_code) {
                e.target.value = data.next_code;
                // إظهار رسالة نجاح بسيطة أو وميض للحقل
                validateCode(data.next_code); 
            }
        } catch (error) {
            console.error("خطأ في جلب الكود:", error);
        }
    }
});
document.addEventListener('DOMContentLoaded', () => {
    const codeInput = document.getElementById('memberCode');
    const statusIcon = document.getElementById('codeStatusIcon');
    const feedback = document.getElementById('codeFeedback');

    if (codeInput) {
        // 1. ميزة الاقتراح التلقائي والاختصار
        codeInput.addEventListener('input', async function(e) {
            let val = e.target.value.trim().toUpperCase();
            e.target.value = val;

            // إذا كتب المستخدم حرفاً واحداً، نقترح كوداً كاملاً
            if (val.length === 1 && /^[A-Z]$/.test(val)) {
                try {
                    const res = await fetch(`/names/get-next-code?letter=${val}`);
                    const data = await res.json();
                    if (data.next_code) {
                        e.target.value = data.next_code;
                        e.target.setSelectionRange(1, data.next_code.length);
                        validateCode(data.next_code);
                    }
                } catch (err) { console.error("Error fetching next code:", err); }
            }
        });

        // 2. التحقق عند الخروج من الحقل
        codeInput.addEventListener('blur', function() {
            validateCode(this.value);
        });
    }

    async function validateCode(code) {
        if (code.length < 3 || !statusIcon) return;

        try {
            const response = await fetch(`/names/check-code-availability?code=${code}`);
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
            console.error("خطأ في التحقق:", err);
        }
    }
});