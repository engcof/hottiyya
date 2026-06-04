/**
 * سكربت المقالات الموحد (محرر المقال + عداد حروف التعليقات) - موقع الحوطية
 */

// دالة تنسيق النصوص الأساسية للمحرر
function formatDoc(cmd, value = null) {
    if (typeof document.execCommand === 'function') {
        document.execCommand(cmd, false, value);
    }
}

document.addEventListener('DOMContentLoaded', () => {
    // === عناصر محرر المقالات (إضافة / تعديل) ===
    const form = document.getElementById('articleForm');
    const editor = document.getElementById('editor');
    const hiddenInput = document.getElementById('content_hidden');
    const fileInput = document.getElementById('image-upload');
    const fileLabel = document.getElementById('file-chosen-text');
    const placeholderText = "اكتب محتوى مقالك هنا...";

    // === عناصر قسم التعليقات (تفاصيل المقال المفرد) ===
    const commentTextarea = document.querySelector('textarea[name="content"]');
    const charCounter = document.querySelector('.char-counter');

    // ==========================================
    // 1️⃣ إدارة محرر المقالات (إذا كانت عناصرها موجودة بالصفحة)
    // ==========================================
    if (editor) {
        if (editor.innerHTML.trim() === "") {
            editor.innerHTML = placeholderText;
        }

        editor.addEventListener('focus', function() {
            if (this.innerText.trim() === placeholderText) {
                this.innerHTML = "";
            }
        });

        editor.addEventListener('blur', function() {
            if (this.innerText.trim() === "") {
                this.innerHTML = placeholderText;
            }
        });
    }

    if (fileInput && fileLabel) {
        fileInput.addEventListener('change', function() {
            if (this.files.length > 0) {
                fileLabel.textContent = "📸 تم تجهيز: " + this.files[0].name;
                fileLabel.style.color = "#2563eb";
            }
        });
    }

    if (form && editor && hiddenInput) {
        form.addEventListener('submit', function(e) {
            const rawContent = editor.innerHTML.trim();
            const textContent = editor.innerText.trim();
            const cleanCheck = rawContent.replace(/<[^>]*>/g, '').trim();

            if (textContent === "" || textContent === placeholderText || cleanCheck === "") {
                e.preventDefault();
                alert("عذراً، لا يمكن نشر مقال فارغ!");
                return false;
            }

            if (textContent.length < 10) {
                e.preventDefault();
                alert("محتوى المقال قصير جداً! يرجى كتابة 10 أحرف على الأقل تشرح فكرتك.");
                return false;
            }

            hiddenInput.value = rawContent;
        });
    }

    // ==========================================
    // 2️⃣ إدارة عداد حروف التعليقات (إذا كانت عناصرها موجودة بالصفحة)
    // ==========================================
    if (commentTextarea && charCounter) {
        commentTextarea.addEventListener('input', () => {
            const currentLength = commentTextarea.value.length;
            charCounter.textContent = `${currentLength}/1000`;
            
            // تحسين بصري: تحويل لون العداد للأحمر إذا اقترب من الحد الأقصى
            if (currentLength >= 900) {
                charCounter.style.color = "#ef4444";
            } else {
                charCounter.style.color = "#64748b";
            }
        });
    }
});