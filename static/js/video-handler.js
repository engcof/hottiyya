/**
 * سكربت معالجة رفع الفيديوهات مع شريط التقدم - موقع الحوطية
 */
document.addEventListener('DOMContentLoaded', () => {
    const form = document.getElementById('videoForm');
    const videoInput = document.getElementById('video_file');
    const uploadBtn = document.getElementById('uploadBtn');
    const statusText = document.getElementById('fileStatusText');
    const previewContainer = document.getElementById('videoPreview');
    const previewVideo = document.getElementById('previewVid');
    
    const progressContainer = document.getElementById('progressContainer');
    const progressBar = document.getElementById('progressBar');
    const percentText = document.getElementById('percentText');

    if (videoInput) {
        videoInput.addEventListener('change', function(e) {
            const file = e.target.files[0];
            if (file) {
                statusText.innerText = "تم اختيار: " + file.name;
                const url = URL.createObjectURL(file);
                previewVideo.src = url;
                previewContainer.style.display = 'block';
                document.getElementById('uploadContent').style.display = 'none';
            }
        });
    }

    if (form) {
        // داخل فيديو-handler.js عند onsubmit
        form.onsubmit = function(e) {
            e.preventDefault();

            const formData = new FormData(form);
            
            // تأكيد إضافي: طباعة التوكن في الكونسول للتأكد من وجوده (للتطوير فقط)
            console.log("CSRF Token being sent:", formData.get('csrf_token'));

            const xhr = new XMLHttpRequest();
       
            // تهيئة الواجهة
            uploadBtn.disabled = true;
            uploadBtn.style.opacity = '0.8';
            uploadBtn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> جاري الرفع...';
            if (progressContainer) progressContainer.style.display = 'block';

            // مراقبة التقدم
            xhr.upload.addEventListener('progress', function(event) {
                if (event.lengthComputable) {
                    const percent = Math.round((event.loaded / event.total) * 100);
                    if (progressBar) progressBar.style.width = percent + '%';
                    if (percentText) percentText.innerText = percent + '%';
                    
                    if (percent === 100) {
                        document.getElementById('uploadStatus').innerText = 'تم الرفع بنجاح! جاري معالجة الفيديو سحابياً...';
                    }
                }
            });

            // معالجة الاستجابة (دمجنا التحقق من نوع الخطأ هنا)
            xhr.onreadystatechange = function() {
                if (xhr.readyState === 4) {
                    if (xhr.status === 200 || xhr.status === 303) {
                        window.location.href = "/video/?success=added";
                    } else {
                        // تسجيل الخطأ في الكونسول للمطور
                        console.error("Upload Failed. Status:", xhr.status, "Response:", xhr.responseText);
                        
                        // تنبيه المستخدم بناءً على نوع الخطأ
                        if (xhr.status === 413) {
                            alert("فشل الرفع: حجم الملف كبير جداً بالنسبة للسيرفر.");
                        } else if (xhr.status === 403) {
                            alert("فشل الرفع: خطأ في توكن الأمان أو انتهت جلستك.");
                        } else {
                            alert("حدث خطأ أثناء الرفع (كود: " + xhr.status + "). يرجى التحقق من الكونسول.");
                        }
                        
                        uploadBtn.disabled = false;
                        uploadBtn.style.opacity = '1';
                        uploadBtn.innerHTML = '<i class="fas fa-cloud-upload-alt"></i> بدء رفع الفيديو';
                    }
                }
            };

            xhr.open('POST', form.action, true);
            xhr.send(formData);
            // تم حذف التكرار الذي كان هنا
        };
    }
});