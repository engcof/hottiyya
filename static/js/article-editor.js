/**
 * سكربت محرر المقالات - موقع الحوطية
 */

function formatDoc(cmd, value = null) {
    if (typeof document.execCommand === 'function') {
        document.execCommand(cmd, false, value);
    }
}

document.addEventListener('DOMContentLoaded', () => {
    const form = document.getElementById('articleForm');
    const editor = document.getElementById('editor');
    const hiddenInput = document.getElementById('content_hidden');
    const placeholderText = "اكتب محتوى مقالك هنا...";

    if (form && editor) {
        
        // 1. مسح النص الترحيبي بذكاء عند التركيز (Focus)
        editor.addEventListener('focus', function() {
            if (this.innerText.trim() === placeholderText) {
                this.innerHTML = "";
            }
        });

        // 2. إعادة النص الترحيبي إذا ترك المستخدم المحرر فارغاً (Blur)
        editor.addEventListener('blur', function() {
            if (this.innerText.trim() === "") {
                this.innerHTML = placeholderText;
            }
        });

        // 3. معالجة وتدقيق البيانات قبل إرسال النموذج (Submit)
        form.addEventListener('submit', function(e) {
            const rawContent = editor.innerHTML;
            const textContent = editor.innerText.trim();

            // تنظيف وإزالة وسوم الـ HTML الفارغة المحتملة للفحص الدقيق
            const cleanCheck = rawContent.replace(/<[^>]*>/g, '').trim();

            if (textContent === "" || textContent === placeholderText || cleanCheck === "") {
                alert("عذراً، لا يمكن نشر مقال فارغ!");
                e.preventDefault();
                return;
            }

            // نقل الـ HTML النظيف والنهائي إلى الحقل المخفي ليتم إرساله لقاعدة البيانات
            if (hiddenInput) {
                hiddenInput.value = rawContent;
            }
        });
    }
});