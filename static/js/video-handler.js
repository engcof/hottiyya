/**
 * سكربت معالجة رفع الفيديوهات - موقع الحوطية
 */
document.addEventListener('DOMContentLoaded', () => {
    const form = document.getElementById('videoForm');
    const videoInput = document.getElementById('video_file');
    const uploadBtn = document.getElementById('uploadBtn');
    const statusText = document.getElementById('fileStatusText');
    const previewContainer = document.getElementById('videoPreview');
    const previewVideo = document.getElementById('previewVid');

    if (videoInput) {
        videoInput.addEventListener('change', function(e) {
            const file = e.target.files[0];
            if (file) {
                // تحديث النص
                statusText.innerText = "تم اختيار: " + file.name;
                
                // معاينة الفيديو المصغرة
                const url = URL.createObjectURL(file);
                previewVideo.src = url;
                previewContainer.style.display = 'block';
                document.getElementById('uploadContent').style.display = 'none';
            }
        });
    }

    if (form) {
        form.onsubmit = function() {
            uploadBtn.disabled = true;
            uploadBtn.style.opacity = '0.8';
            uploadBtn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> جاري رفع الفيديو... يرجى عدم إغلاق الصفحة';
        };
    }
});