/* ========== ✅ سكربت معالجة رفع الفيديوهات مع شريط التقدم - موقع الحوطية ========== */
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

    // القيود البرمجية المتوافقة مع السيرفر
    const MAX_VIDEO_SIZE = 40 * 1024 * 1024; // الحد الأقصى 40 ميجابايت مثلاً
    const ALLOWED_EXTENSIONS = ['mp4', 'm4v', 'mov', 'avi', 'webm'];

    function showDynamicAlert(message) {
        const existingAlert = document.getElementById('dynamic-video-alert');
        if (existingAlert) existingAlert.remove();

        const alertDiv = document.createElement('div');
        alertDiv.className = 'alert error';
        alertDiv.id = 'dynamic-video-alert';
        alertDiv.style.cssText = "background-color: #fef2f2; border: 1px solid #fca5a5; color: #991b1b; padding: 12px; border-radius: 8px; margin-bottom: 20px; position: relative;";
        alertDiv.innerHTML = `
            <div style="display: flex; align-items: center; gap: 10px;">
                <i class="fas fa-exclamation-circle"></i>
                <span>${message}</span>
                <button type="button" style="margin-right: auto; background: none; border: none; font-size: 1.2rem; cursor: pointer; color: #991b1b;" onclick="this.parentElement.parentElement.remove()">×</button>
            </div>
        `;
        
        form.insertBefore(alertDiv, form.firstChild);

        setTimeout(() => {
            alertDiv.style.transition = 'opacity 0.6s ease';
            alertDiv.style.opacity = '0';
            setTimeout(() => alertDiv.remove(), 600);
        }, 6000);
    }

    // مراقبة تغيير حقل إدخال الفيديو وتحديث المعاينة الذكية
    if (videoInput) {
        videoInput.addEventListener('change', function(e) {
            const file = e.target.files[0];
            if (file) {
                const extension = file.name.split('.').pop().toLowerCase();
                
                // 🔒 فحص الامتداد قبل البدء بالرفع
                if (!ALLOWED_EXTENSIONS.includes(extension)) {
                    showDynamicAlert("❌ صيغة الفيديو غير مدعومة! يرجى اختيار ملف بصيغة (MP4, MOV, WEBM).");
                    this.value = '';
                    return;
                }

                // 🔒 فحص الحجم لتجنب رفض السيرفر لاحقاً
                if (file.size > MAX_VIDEO_SIZE) {
                    showDynamicAlert("❌ حجم الفيديو كبير جداً! الحد الأقصى المسموح به هو 40 ميجابايت.");
                    this.value = '';
                    return;
                }

                statusText.innerText = "تم اختيار: " + file.name;
                const url = URL.createObjectURL(file);
                previewVideo.src = url;
                
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
            const xhr = new XMLHttpRequest();
       
            // تهيئة واجهة أزرار الرفع
            uploadBtn.disabled = true;
            uploadBtn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> جاري الرفع والاتصال...';
            
            if (progressContainer) progressContainer.style.display = 'block';
            if (uploadStatus) uploadStatus.innerText = 'يرجى عدم إغلاق الصفحة حتى اكتمال العملية';

            // مراقبة شريط تقدم الرفع وحساب النسبة المئوية
            xhr.upload.addEventListener('progress', function(event) {
                if (event.lengthComputable) {
                    const percent = Math.round((event.loaded / event.total) * 100);
                    if (progressBar) progressBar.style.width = percent + '%';
                    if (percentText) percentText.innerText = percent + '%';
                    
                    if (percent === 100 && uploadStatus) {
                        uploadStatus.innerText = '⏳ تم الرفع بنجاح! جاري المعالجة السحابية وحفظ البيانات (قد يستغرق ذلك دقيقة)...';
                    }
                }
            });

            // معالجة استجابة السيرفر بعد انتهاء الرفع بالكامل
            xhr.onreadystatechange = function() {
                if (xhr.readyState === 4) {
                    // إذا نجح الطلب أو أعاد التوجيه بنجاح، نقوم بنقل المستخدم لصفحة المعرض الرئيسية مع رسالة النجاح
                    if (xhr.status === 200 || xhr.status === 201) {
                        window.location.href = "/video/?success=added";
                    } else {
                        console.error("Upload Failed. Status:", xhr.status);
                        
                        if (xhr.status === 413) {
                            showDynamicAlert("فشل الرفع: حجم ملف الفيديو يتجاوز الحد الأقصى المسموح به للسيرفر.");
                        } else if (xhr.status === 403) {
                            showDynamicAlert("فشل الرفع: انتهت صلاحية الجلسة أو توكن الأمان (CSRF) غير صالح. يرجى تحديث الصفحة.");
                        } else {
                            showDynamicAlert("حدث خطأ أثناء معالجة أو رفع الفيديو على السيرفر. يرجى المحاولة مجدداً.");
                        }
                        
                        // إعادة تهيئة الزر للمحاولة مرة أخرى
                        uploadBtn.disabled = false;
                        uploadBtn.innerHTML = '<i class="fas fa-cloud-upload-alt"></i> بدء رفع الفيديو';
                        if (progressContainer) progressContainer.style.display = 'none';
                    }
                }
            };

            xhr.open('POST', form.action, true);
            // نرسل الطلب، وسيتكفل الـ Backend الجديد بمعالجة الملف تدفقياً دون سحق الذاكرة
            xhr.send(formData);
        };
    }
});