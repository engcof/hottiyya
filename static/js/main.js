document.addEventListener("DOMContentLoaded", function () {

    /* ==================== 1. قائمة الموبايل (Hamburger Menu) ==================== */
    const mobileToggle = document.getElementById("mobileToggle");
    const mobileNav = document.getElementById("mobileNav");

    if (mobileToggle && mobileNav) {
        mobileToggle.addEventListener("click", function (e) {
            e.stopPropagation();
            this.classList.toggle("active");
            mobileNav.classList.toggle("active");
            // إضافة كلاس إضافي للتحكم في ظهور التأثير (إذا لزم الأمر)
            setTimeout(() => mobileNav.classList.toggle("show"), 10);
        });

        // إغلاق القائمة عند الضغط على أي رابط بداخلها
        mobileNav.querySelectorAll("a").forEach(link => {
            link.addEventListener("click", () => {
                mobileToggle.classList.remove("active");
                mobileNav.classList.remove("active");
                mobileNav.classList.remove("show");
            });
        });
    }

    /* ==================== 2. دروب داون المستخدم (Desktop & Mobile) ==================== */
    const userBtn = document.getElementById("userBtn");
    const userDropdown = document.getElementById("userDropdown");

    if (userBtn && userDropdown) {
        userBtn.addEventListener("click", function (e) {
            e.stopPropagation();
            // إغلاق أي قوائم أخرى
            document.getElementById('onlineList')?.classList.remove("show");
            userDropdown.classList.toggle("show");
        });
    }

    /* ==================== 3. إغلاق القوائم عند الضغط في أي مكان ==================== */
    document.addEventListener("click", function (e) {
        // إغلاق قائمة المستخدم
        if (userDropdown && !userBtn?.contains(e.target)) {
            userDropdown.classList.remove("show");
        }
        // إغلاق قائمة الموبايل
        if (mobileNav && !mobileToggle?.contains(e.target) && !mobileNav.contains(e.target)) {
            mobileToggle?.classList.remove("active");
            mobileNav?.classList.remove("active");
        }
    });

    /* ==================== 4. الرسائل (Flash Messages) ==================== */
    const flashMessages = document.querySelectorAll('.flash-message, #success-alert');
    flashMessages.forEach(message => {
        setTimeout(() => {
            message.style.transition = 'opacity 0.6s ease';
            message.style.opacity = '0';
            setTimeout(() => message.remove(), 600);
        }, 5000);
    });

    /* ... باقي الكود الخاص بـ onlineToggle, Ticker, Inline Editing ... */
    
    // ملاحظة: تأكد من إبقاء كود onlineToggle الذي نقلته للبوابة (Portal) هنا كما هو
});