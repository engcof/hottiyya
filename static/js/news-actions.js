/**
 * سكربت إدارة الأخبار - موقع الحوطية (النسخة المستقرة والمؤمنة)
 */

document.addEventListener('DOMContentLoaded', () => {
    // 1. إدارة ملفات الوسائط (صور وفيديوهات)
    const newsImage = document.getElementById('newsImage');
    const previewContainer = document.getElementById('imagePreview');
    const uploadContent = document.getElementById('uploadContent');
    const statusText = document.getElementById('fileStatusText');
    const removeBtn = document.getElementById('removePreview');

    if (newsImage && previewContainer) {
        newsImage.addEventListener('change', function(e) {
            const file = e.target.files[0];
            if (file) {
                const reader = new FileReader();
                reader.onload = (event) => {
                    // تفريغ أي معاينة سابقة (سواء كانت صورة أو فيديو قديم)
                    // مع الاحتفاظ بزر الإزالة بالأسفل
                    const oldPreview = previewContainer.querySelector('.dynamic-preview');
                    if (oldPreview) oldPreview.remove();

                    let previewElement;

                    // التحقق الذكي من نوع الملف لإنشاء العنصر المناسب في الـ DOM
                    if (file.type.startsWith('video/')) {
                        previewElement = document.createElement('video');
                        previewElement.src = event.target.result;
                        previewElement.controls = true;
                    } else {
                        previewElement = document.createElement('img');
                        previewElement.src = event.target.result;
                    }

                    // إضافة تنسيق موحد للمعاينة ديناميكياً
                    previewElement.className = 'dynamic-preview';
                    previewElement.style.width = '120px';
                    previewElement.style.maxHeight = '120px';
                    previewElement.style.objectFit = 'cover';
                    previewElement.style.borderRadius = '8px';
                    previewElement.style.border = '2px solid var(--accent)';
                    previewElement.style.display = 'inline-block';

                    // إدراج العنصر الجديد في بداية حاوية المعاينة
                    previewContainer.insertBefore(previewElement, previewContainer.firstChild);

                    // تحديث عناصر الواجهة البصرية
                    previewContainer.style.display = 'block';
                    if (uploadContent) uploadContent.style.display = 'none';
                    if (statusText) {
                        statusText.innerText = "📸 تم تجهيز: " + file.name;
                        statusText.style.color = "#2563eb";
                    }
                };
                reader.readAsDataURL(file);
            }
        });
    }

    if (removeBtn) {
        removeBtn.addEventListener('click', () => {
            if (newsImage) newsImage.value = "";
            if (previewContainer) previewContainer.style.display = 'none';
            if (uploadContent) uploadContent.style.display = 'block';
            
            const oldPreview = previewContainer.querySelector('.dynamic-preview');
            if (oldPreview) oldPreview.remove();

            if (statusText) {
                statusText.innerText = "اضغط لتغيير الوسائط (اختياري)";
                statusText.style.color = "";
            }
        });
    }

    // 2. إدارة المحرر والنموذج والتحقق الذكي
    const form = document.getElementById('newsForm');
    const editor = document.getElementById('editor');
    const contentHidden = document.getElementById('content_hidden');
    const placeholderText = "اكتب تفاصيل الخبر هنا...";

    if (form && editor && contentHidden) {
        
        // مسح النص الافتراضي عند التركيز (Focus)
        editor.addEventListener('focus', function() {
            if (this.innerText.trim() === placeholderText) {
                this.innerHTML = "";
            }
        });

        // إعادة وضع النص الافتراضي في حال ترك الحقل فارغاً (Blur)
        editor.addEventListener('blur', function() {
            if (this.innerText.trim() === "") {
                this.innerHTML = placeholderText;
            }
        });

        // التحقق عند الإرسال لمنع الثغرات أو الحقول الفارغة
        form.addEventListener('submit', function(e) {
            const rawContent = editor.innerHTML.trim();
            const textContent = editor.innerText.trim();
            
            // إزالة وسوم الـ HTML للتحقق من الطول الفعلي الصادق للنص
            const cleanCheck = rawContent.replace(/<[^>]*>/g, '').trim();

            if (textContent === "" || textContent === placeholderText || cleanCheck === "") {
                e.preventDefault();
                alert("عذراً، لا يمكن نشر خبر بدون تفاصيل حقيقية!");
                return false;
            }

            if (textContent.length < 15) {
                e.preventDefault();
                alert("تفاصيل الخبر قصيرة جداً، يرجى كتابة 15 حرفاً على الأقل.");
                return false;
            }

            // المزامنة الآمنة النهائية للحقل المخفي
            contentHidden.value = rawContent;
        });
    }
});

// دالة أدوات التنسيق للمحرر الغني
function formatDoc(cmd, value = null) {
    if (typeof document.execCommand === 'function') {
        document.execCommand(cmd, false, value);
    }
}