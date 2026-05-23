/* ========== ✅ سكربت الصفحة الرئيسية (home.js) ========== */

document.addEventListener('DOMContentLoaded', function() {
    // جلب التيكر الخاص بالهوم (home-ticker-inner) لحقنه بمميزات الماوس فقط
    const ticker = document.querySelector('.home-ticker-inner');

    if (ticker) {
        // توقف الحركة عند وضع الماوس لراحة المستخدم أثناء القراءة
        ticker.addEventListener('mouseenter', () => {
            ticker.style.animationPlayState = 'paused';
        });
        
        // استئناف الحركة عند إبعاد الماوس
        ticker.addEventListener('mouseleave', () => {
            ticker.style.animationPlayState = 'running';
        });
    }
});