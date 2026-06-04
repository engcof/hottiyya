/* ========== ✅ سكربت التحكم بمعرض الصور (gallery-actions.js) ========== */

document.addEventListener('DOMContentLoaded', () => {
    const galleryForm = document.getElementById('galleryForm');
    const galleryImage = document.getElementById('galleryImage');
    const galleryTitle = document.getElementById('galleryTitle');
    const uploadContent = document.getElementById('uploadContent');
    const imagePreview = document.getElementById('imagePreview');
    const previewImg = document.getElementById('previewImg');
    const removePreview = document.getElementById('removePreview');
    const fileError = document.getElementById('fileError');
    const titleError = document.getElementById('titleError');

    // الإعدادات الأمنية والقيود
    const ALLOWED_EXTENSIONS = ['jpg', 'jpeg', 'png', 'gif', 'webp'];
    const MAX_FILE_SIZE = 5 * 1024 * 1024; // 5 ميجابايت

    // 1. مراقبة حدث اختيار الصورة ومعاينتها برمجياً
    if (galleryImage) {
        galleryImage.addEventListener('change', function() {
            fileError.style.display = 'none';
            
            if (this.files && this.files[0]) {
                const file = this.files[0];
                const extension = file.name.split('.').pop().toLowerCase();
                
                // أ. فحص الامتداد أمنياً على مستوى المتصفح
                if (!ALLOWED_EXTENSIONS.includes(extension)) {
                    fileError.textContent = '❌ امتداد الملف غير مسموح به! يرجى اختيار صورة صالحة.';
                    fileError.style.display = 'block';
                    this.value = ''; // تصفير الحقل
                    return;
                }

                // ب. فحص حجم الملف من الاستهلاك المفرط للموارد
                if (file.size > MAX_FILE_SIZE) {
                    fileError.textContent = '❌ حجم الصورة ضخم جداً! الحد الأقصى المسموح به هو 5 ميجابايت.';
                    fileError.style.display = 'block';
                    this.value = '';
                    return;
                }

                // ج. إنشاء قارئ الملف لإنشاء المعاينة البصرية النظيفة
                const reader = new FileReader();
                reader.onload = function(e) {
                    previewImg.src = e.target.result;
                    uploadContent.style.display = 'none';
                    imagePreview.style.display = 'flex';
                    // خفض مستوى التغطية الـ z-index لملف المدخلات لتمكين الضغط على تغيير الصورة
                    galleryImage.style.zIndex = '-1';
                };
                reader.readAsDataURL(file);
            }
        });
    }

    // 2. زر إلغاء المعاينة وتغيير الصورة
    if (removePreview) {
        removePreview.addEventListener('click', function(e) {
            e.preventDefault();
            galleryImage.value = ''; // مسح الملف المخزن
            imagePreview.style.display = 'none';
            uploadContent.style.display = 'block';
            fileError.style.display = 'none';
            galleryImage.style.zIndex = '10'; // إعادة الحقل ليكون قابلاً للضغط
        });
    }

    // 3. فحص مدخلات العنوان عند الإرسال لمنع الثغرات النصية والأخطاء اللغوية
    if (galleryForm) {
        galleryForm.addEventListener('submit', function(e) {
            titleError.style.display = 'none';
            const titleValue = galleryTitle.value.trim();

            if (titleValue.length < 3) {
                e.preventDefault();
                titleError.textContent = '⚠️ وصف الصورة قصير جداً، يجب أن يتكون من 3 أحرف على الأقل.';
                titleError.style.display = 'block';
                galleryTitle.focus();
                return;
            }

            // منع العناوين التي تبدأ برموز أو أرقام غير منطقية متوافقاً مع فحص الـ Backend
            const invalidPattern = /^[\d\s\-\_\.\@\#\!\$\%\^\&\*\(\)]/;
            if (invalidPattern.test(titleValue)) {
                e.preventDefault();
                titleError.textContent = '⚠️ يجب أن يبدأ الوصف بنص واضح وصريح (لا تبدأ بالرموز أو الأرقام).';
                titleError.style.display = 'block';
                galleryTitle.focus();
                return;
            }
        });
    }
});