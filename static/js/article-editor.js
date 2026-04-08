/**
 * سكربت محرر المقالات - موقع الحوطية
 */

function formatDoc(cmd, value = null) {
    document.execCommand(cmd, false, value);
}

document.addEventListener('DOMContentLoaded', () => {
    const form = document.getElementById('articleForm');
    const editor = document.getElementById('editor');
    const hiddenInput = document.getElementById('content_hidden');

    if (form && editor) {
        // 1. معالجة البيانات قبل إرسال النموذج
        form.addEventListener('submit', function(e) {
            // نقل الـ HTML الناتج من المحرر إلى الحقل المخفي
            hiddenInput.value = editor.innerHTML;
            
            // التحقق من أن المقال ليس فارغاً
            const textContent = editor.innerText.trim();
            if (textContent === "" || textContent === "اكتب محتوى مقالك هنا...") {
                alert("عذراً، لا يمكن نشر مقال فارغ!");
                e.preventDefault();
            }
        });

        // 2. مسح النص الافتراضي عند بدء الكتابة
        editor.addEventListener('focus', function() {
            if (this.innerText.trim() === "اكتب محتوى مقالك هنا...") {
                this.innerHTML = "";
            }
        }, { once: true });
    }
});