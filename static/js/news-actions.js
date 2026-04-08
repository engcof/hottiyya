/**
 * سكربت إدارة الأخبار - موقع الحوطية
 * يتولى وظيفة معاينة الصورة المرفوعة وإزالتها
 */

document.addEventListener('DOMContentLoaded', () => {
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
                // التحقق من نوع الملف (اختياري لزيادة الأمان)
                if (!file.type.startsWith('image/')) {
                    alert("يرجى اختيار ملف صورة فقط");
                    this.value = "";
                    return;
                }

                const reader = new FileReader();
                reader.onload = function(event) {
                    previewImg.src = event.target.result;
                    previewContainer.style.display = 'block';
                    uploadContent.style.display = 'none';
                    statusText.innerText = "تم اختيار: " + file.name;
                }
                reader.readAsDataURL(file);
            }
        });
    }

    if (removeBtn) {
        removeBtn.addEventListener('click', function() {
            newsImage.value = "";
            previewContainer.style.display = 'none';
            uploadContent.style.display = 'block';
            statusText.innerText = "اضغط هنا أو اسحب الصورة لرفعها";
        });
    }
});