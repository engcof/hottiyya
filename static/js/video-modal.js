//* ========== ✅ نظام تشغيل مودال الفيديوهات المطور والأكثر أماناً ========== */

const lightbox = document.getElementById('videoLightboxModal');
const player = document.getElementById('lightboxVideoPlayer');
const lightboxTitle = document.getElementById('lightboxVideoTitle');
const fsIcon = document.getElementById('fsIcon');

// فتح المودال وتجهيز المشغل بحماية تامة
function openVideoModal(videoUrl, title) {
    if (!lightbox || !player) return;

    if (lightboxTitle) {
        // 🔒 حماية XSS صارمة باستخدام textContent بدلاً من innerText أو innerHTML
        lightboxTitle.textContent = title; 
    }
    player.src = videoUrl;
    
    lightbox.classList.add('show');
    player.load();
    player.play().catch(error => {
        console.log("تم حظر التشغيل التلقائي بواسطة المتصفح، ينتظر تفاعل المستخدم.");
    });
}

function closeVideoModal(eOrForce) {
    if (eOrForce === true || eOrForce.target === lightbox || eOrForce.currentTarget?.classList.contains('close-btn')) {
        lightbox.classList.remove('show');
        player.pause();
        player.src = ""; 
        
        if (document.fullscreenElement) {
            document.exitFullscreen().catch(err => console.log(err));
        }
    }
}

function toggleLightboxFullscreen() {
    const dialog = lightbox.querySelector('.lightbox-dialog');
    if (!document.fullscreenElement) {
        if (dialog.requestFullscreen) dialog.requestFullscreen();
    } else {
        document.exitFullscreen();
    }
}

document.addEventListener('fullscreenchange', () => {
    if (document.fullscreenElement) {
        if (fsIcon) fsIcon.className = "fas fa-compress";
    } else {
        if (fsIcon) fsIcon.className = "fas fa-expand";
    }
});

// تفعيل ميزة الـ Data Attributes للتخلص النهائي من الـ inline javascript في قوالب العرض
document.addEventListener('DOMContentLoaded', () => {
    const clickableThumbnails = document.querySelectorAll('.video-frame-wrapper-clickable');
    clickableThumbnails.forEach(item => {
        item.addEventListener('click', function() {
            const videoUrl = this.getAttribute('data-video-url');
            const videoTitle = this.getAttribute('data-video-title');
            openVideoModal(videoUrl, videoTitle);
        });
    });

    document.addEventListener('keydown', (e) => {
        if (e.key === "Escape" && lightbox && lightbox.classList.contains('show')) {
            closeVideoModal(true);
        }
    });
});