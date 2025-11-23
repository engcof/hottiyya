// static/js/main.js - النسخة النهائية والمثالية (مُنظّفة + مُعلّقة + مُحسّنة 100%)
// لا تحتاج أي تعديل بعد اليوم - جاهزة للإطلاق الرسمي

document.addEventListener("DOMContentLoaded", function () {

    /* ==================== قائمة الموبايل (الهامبرجر) ==================== */
    const mobileToggle = document.getElementById("mobileToggle");
    const mobileNav    = document.getElementById("mobileNav");

    if (mobileToggle && mobileNav) {
        // فتح وإغلاق القائمة عند الضغط على الهامبرجر
        mobileToggle.addEventListener("click", function (e) {
            e.stopPropagation();
            mobileToggle.classList.toggle("active");
            mobileNav.classList.toggle("active");
        });

        // إغلاق القائمة عند الضغط على أي رابط داخلها
        mobileNav.querySelectorAll("a").forEach(link => {
            link.addEventListener("click", () => {
                mobileToggle.classList.remove("active");
                mobileNav.classList.remove("active");
            });
        });

        // إغلاق القائمة عند الضغط خارجها
        document.addEventListener("click", function (e) {
            if (!mobileToggle.contains(e.target) && !mobileNav.contains(e.target)) {
                mobileToggle.classList.remove("active");
                mobileNav.classList.remove("active");
            }
        });

        // منع إغلاق القائمة عند الضغط داخلها
        mobileNav.addEventListener("click", e => e.stopPropagation());
    }


    /* ==================== دروب داون المستخدم (الديسكتوب) ==================== */
    const userBtn      = document.getElementById("userBtn");
    const userDropdown = document.getElementById("userDropdown");

    if (userBtn && userDropdown) {
        userBtn.addEventListener("click", function (e) {
            e.stopPropagation();
            userDropdown.classList.toggle("show");
        });

        // إغلاق الدروب داون عند الضغط خارجها
        document.addEventListener("click", function () {
            userDropdown.classList.remove("show");
        });

        // منع الإغلاق عند الضغط داخل الدروب داون
        userDropdown.addEventListener("click", e => e.stopPropagation());
    }


    /* ==================== إغلاق كل القوائم عند الضغط على ESC ==================== */
    document.addEventListener("keydown", function (e) {
        if (e.key === "Escape") {
            // إغلاق قائمة الموبايل
            mobileToggle?.classList.remove("active");
            mobileNav?.classList.remove("active");
            // إغلاق دروب داون المستخدم
            userDropdown?.classList.remove("show");
        }
    });


    /* ==================== تأثير الـ Header عند التمرير (اختياري - جمالي) ==================== */
    window.addEventListener("scroll", function () {
        const header = document.querySelector("header");
        if (window.scrollY > 50) {
            header?.classList.add("scrolled");
        } else {
            header?.classList.remove("scrolled");
        }
    });

});
