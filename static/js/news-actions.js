/**
 * سكربت إدارة الأخبار - موقع الحوطية
 */

document.addEventListener('DOMContentLoaded', () => {
    // 1. إدارة ملفات الوسائط
    const newsImage = document.getElementById('newsImage');
    const previewContainer = document.getElementById('imagePreview');
    const previewImg = document.getElementById('previewImg');
    const uploadContent = document.getElementById('uploadContent');
    const statusText = document.getElementById('fileStatusText');
    const removeBtn = document.getElementById('removePreview');

    if (newsImage) {
        newsImage.addEventListener('change', function(e) {
            const file = e.target.files[0];
            if (file) {
                // ملاحظة: قمت بإزالة شرط (image/) لأنك تدعم الفيديو أيضاً في الـ HTML
                const reader = new FileReader();
                reader.onload = (event) => {
                    previewImg.src = event.target.result;
                    previewContainer.style.display = 'block';
                    uploadContent.style.display = 'none';
                    statusText.innerText = "تم اختيار: " + file.name;
                };
                reader.readAsDataURL(file);
            }
        });
    }

    if (removeBtn) {
        removeBtn.addEventListener('click', () => {
            newsImage.value = "";
            previewContainer.style.display = 'none';
            uploadContent.style.display = 'block';
            statusText.innerText = "اضغط لتغيير الوسائط (اختياري)";
        });
    }

    // 2. إدارة المحرر والنموذج
    const form = document.getElementById('newsForm');
    const editor = document.getElementById('editor');
    const contentHidden = document.getElementById('content_hidden');

    if (form && editor && contentHidden) {
        form.addEventListener('submit', function(e) {
            // نقل الـ HTML الناتج من المحرر إلى الحقل المخفي
            contentHidden.value = editor.innerHTML;
            
            // التحقق من أن المقال ليس فارغاً
            const textContent = editor.innerText.trim();
            if (!textContent) {
                alert("عذراً، لا يمكن نشر خبر فارغ!");
                e.preventDefault(); // منع الإرسال
            }
        });

        // 2. مسح النص الافتراضي عند بدء الكتابة
        editor.addEventListener('focus', function() {
            if (this.innerText.trim() === "اكتب تفاصيل الخبر هنا..." ) {
                this.innerHTML = "";
            }
        }, { once: true });
    }
});

// دالة أدوات التنسيق للمحرر
function formatDoc(cmd, value = null) {
    document.execCommand(cmd, false, value);
}