/**
 * سكربت معالجة رفع الفيديوهات مع شريط التقدم المطور - موقع الحوطية
 */
document.addEventListener('DOMContentLoaded', () => {
    const form = document.getElementById('videoForm');
    const videoInput = document.getElementById('video_file');
    const uploadBtn = document.getElementById('uploadBtn');
    const statusText = document.getElementById('fileStatusText');
    const previewContainer = document.getElementById('videoPreview');
    const previewVideo = document.getElementById('previewVid');
    const uploadContent = document.getElementById('uploadContent');
    
    const progressContainer = document.getElementById('progressContainer');
    const progressBar = document.getElementById('progressBar');
    const percentText = document.getElementById('percentText');
    const uploadStatus = document.getElementById('uploadStatus');

    // دالة مساعدة لحقن التنبيهات الاحترافية ديناميكياً أعلى الاستمارة في حال حدوث خطأ
    function showDynamicAlert(message) {
        // التحقق من عدم وجود تنبيه حالي معروض لمنع التكرار
        const existingAlert = document.getElementById('dynamic-video-alert');
        if (existingAlert) existingAlert.remove();

        const alertDiv = document.createElement('div');
        alertDiv.className = 'alert error';
        alertDiv.id = 'dynamic-video-alert';
        alertDiv.innerHTML = `
            <i class="fas fa-exclamation-circle"></i>
            <span>${message}</span>
            <button type="button" class="alert-close" onclick="this.parentElement.remove()">×</button>
        `;
        
        // إدخال التنبيه قبل حقول الاستمارة مباشرةً
        form.insertBefore(alertDiv, form.firstChild);

        // جعل التنبيه يختفي تلقائياً بعد 6 ثوانٍ
        setTimeout(() => {
            alertDiv.style.transition = 'opacity 0.6s ease';
            alertDiv.style.opacity = '0';
            setTimeout(() => alertDiv.remove(), 600);
        }, 6000);
    }

    // مراقبة تغيير حقل إدخال الفيديو وتحديث المعاينة
    if (videoInput) {
        videoInput.addEventListener('change', function(e) {
            const file = e.target.files[0];
            if (file) {
                statusText.innerText = "تم اختيار: " + file.name;
                const url = URL.createObjectURL(file);
                previewVideo.src = url;
                
                // التحكم بالظهور والاختفاء عبر كتل العرض النظيفة
                if (previewContainer) previewContainer.style.display = 'block';
                if (uploadContent) uploadContent.style.display = 'none';
            }
        });
    }

    // معالجة إرسال الاستمارة عبر AJAX (XMLHttpRequest) لضمان شريط تقدم حي
    if (form) {
        form.onsubmit = function(e) {
            e.preventDefault();

            const formData = new FormData(form);
            console.log("CSRF Token being sent:", formData.get('csrf_token'));

            const xhr = new XMLHttpRequest();
       
            // تهيئة واجهة أزرار الرفع (تعطيل الزر لمنع نقرات متعددة)
            uploadBtn.disabled = true;
            uploadBtn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> جاري الرفع...';
            
            // إظهار حاوية شريط التقدم الموحدة
            if (progressContainer) progressContainer.style.display = 'block';
            if (uploadStatus) uploadStatus.innerText = 'يرجى عدم إغلاق الصفحة حتى اكتمال العملية';

            // مراقبة شريط تقدم الرفع وحساب النسبة المئوية
            xhr.upload.addEventListener('progress', function(event) {
                if (event.lengthComputable) {
                    const percent = Math.round((event.loaded / event.total) * 100);
                    if (progressBar) progressBar.style.width = percent + '%';
                    if (percentText) percentText.innerText = percent + '%';
                    
                    if (percent === 100 && uploadStatus) {
                        uploadStatus.innerText = 'تم الرفع بنجاح! جاري معالجة الفيديو سحابياً وحفظ السجل...';
                    }
                }
            });

            // معالجة استجابة السيرفر بعد انتهاء الرفع بالكامل
            xhr.onreadystatechange = function() {
                if (xhr.readyState === 4) {
                    if (xhr.status === 200 || xhr.status === 303) {
                        // التحقق من وجود رابط إعادة توجيه من السيرفر، وإلا الذهاب للرابط الافتراضي لمعرض الفيديوهات
                        const redirectUrl = xhr.getResponseHeader('Location') || "/video/?success=added";
                        window.location.href = redirectUrl;
                    } else {
                        console.error("Upload Failed. Status:", xhr.status, "Response:", xhr.responseText);
                        
                        // معالجة الأخطاء الشائعة وحقن التنبيه الذكي ديناميكياً
                        if (xhr.status === 413) {
                            showDynamicAlert("فشل الرفع: حجم ملف الفيديو كبير جداً ويتجاوز الحد المسموح به للسيرفر.");
                        } else if (xhr.status === 403) {
                            showDynamicAlert("فشل الرفع: انتهت صلاحية الجلسة أو توكن الأمان (CSRF) غير صالح.");
                        } else {
                            showDynamicAlert(`حدث خطأ غير متوقع أثناء الرفع (كود: ${xhr.status}). يرجى إعادة المحاولة.`);
                        }
                        
                        // إعادة تهيئة زر الإرسال للسماح للمستخدم بالمحاولة مرة أخرى
                        uploadBtn.disabled = false;
                        uploadBtn.innerHTML = '<i class="fas fa-cloud-upload-alt"></i> بدء رفع الفيديو';
                        
                        // إخفاء شريط التقدم وتصفيره في حال حدوث خطأ لإتاحة المحاولة من جديد
                        if (progressContainer) progressContainer.style.display = 'none';
                        if (progressBar) progressBar.style.width = '0%';
                        if (percentText) percentText.innerText = '0%';
                    }
                }
            };

            xhr.open('POST', form.action, true);
            xhr.send(formData);
        };
    }
});