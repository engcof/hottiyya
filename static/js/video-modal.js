/**
 * نظام تشغيل مودال الفيديوهات المنفصل - مجتمع الحوطية
 */

const lightbox = document.getElementById('videoLightboxModal');
const player = document.getElementById('lightboxVideoPlayer');
const lightboxTitle = document.getElementById('lightboxVideoTitle');
const fsIcon = document.getElementById('fsIcon');

// 1. فتح المودال وتجهيز المشغل
function openVideoModal(videoUrl, title) {
    if (!lightbox || !player) return;

    lightboxTitle.innerText = title;
    player.src = videoUrl;
    
    // إظهار المودال وتفعيل التشغيل التلقائي
    lightbox.classList.add('show');
    player.load();
    player.play().catch(error => {
        console.log("تم حظر التشغيل التلقائي بواسطة السياسة، ينتظر ضغطة المستخدم.");
    });
}

// 2. إغلاق المودال بشكل آمن وإيقاف الصوت
function closeVideoModal(eOrForce) {
    // التحقق إذا كان الضغط على الخلفية المعتمة أو زر الإغلاق الإجباري
    if (eOrForce === true || eOrForce.target === lightbox) {
        lightbox.classList.remove('show');
        player.pause();
        player.src = ""; // تفريغ الذاكرة لعدم استهلاك البيانات الخلفية
        
        // الخروج من ملء الشاشة إذا كان مفعلاً عند الإغلاق
        if (document.fullscreenElement) {
            document.exitFullscreen().catch(err => console.log(err));
        }
    }
}

// 3. ميزة ملء الشاشة التفاعلية حسب الطلب (Fullscreen Toggle)
function toggleLightboxFullscreen() {
    const dialog = lightbox.querySelector('.lightbox-dialog');
    
    if (!document.fullscreenElement) {
        // الدخول في مود ملء الشاشة للحاوية بالكامل لراحة المشاهد
        if (dialog.requestFullscreen) {
            dialog.requestFullscreen();
        } else if (dialog.webkitRequestFullscreen) { /* Safari */
            dialog.webkitRequestFullscreen();
        } else if (dialog.msRequestFullscreen) { /* IE11 */
            dialog.msRequestFullscreen();
        }
    } else {
        // الخروج والعودة للحجم الطبيعي المحدد بالـ CSS
        document.exitFullscreen();
    }
}

// مراقبة تغير وضعية الشاشة لتحديث شكل الأيقونة تلقائياً (Expand / Compress)
document.addEventListener('fullscreenchange', () => {
    if (document.fullscreenElement) {
        fsIcon.className = "fas fa-compress";
    } else {
        fsIcon.className = "fas fa-expand";
    }
});

// إغلاق المودال تلقائياً في حال ضغط المستخدم على زر Escape في الكيبورد
document.addEventListener('keydown', (e) => {
    if (e.key === "Escape" && lightbox.classList.contains('show')) {
        closeVideoModal(true);
    }
});