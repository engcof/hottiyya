// static/js/main.js - النسخة النهائية والمثالية
document.addEventListener("DOMContentLoaded", function () {

    /* ==================== Mobile Menu ==================== */
    const mobileMenuToggle = document.querySelector('.mobile-menu-toggle');
    const mobileNav = document.querySelector('.mobile-nav');

    if (mobileMenuToggle && mobileNav) {
        mobileMenuToggle.addEventListener('click', () => {
            mobileMenuToggle.classList.toggle('active');
            mobileNav.classList.toggle('active');
        });

        // إغلاق القائمة لما ننقر على رابط
        document.querySelectorAll('.mobile-nav a').forEach(link => {
            link.addEventListener('click', () => {
                mobileMenuToggle.classList.remove('active');
                mobileNav.classList.remove('active');
            });
        });

        // إغلاق القائمة لما ننقر برا
        document.addEventListener('click', (e) => {
            if (!mobileMenuToggle.contains(e.target) && !mobileNav.contains(e.target)) {
                mobileMenuToggle.classList.remove('active');
                mobileNav.classList.remove('active');
            }
        });
    }

    /* ==================== Desktop User Dropdown ==================== */
    document.querySelectorAll(".user-btn").forEach(btn => {
        btn.addEventListener("click", function (e) {
            e.preventDefault();
            e.stopPropagation();

            const dropdown = this.closest(".user-dropdown");
            const menu = dropdown.querySelector(".dropdown-menu");

            // إغلاق أي قوائم أخرى مفتوحة
            document.querySelectorAll(".dropdown-menu.show").forEach(m => {
                if (m !== menu) m.classList.remove("show");
            });

            // فتح/إغلاق القائمة الحالية
            menu.classList.toggle("show");
        });
    });

    // إغلاق كل القوائم لما ننقر برا
    document.addEventListener("click", function () {
        document.querySelectorAll(".dropdown-menu.show").forEach(menu => {
            menu.classList.remove("show");
        });
    });

    // منع الإغلاق لما ننقر داخل القائمة
    document.querySelectorAll(".dropdown-menu").forEach(menu => {
        menu.addEventListener("click", e => e.stopPropagation());
    });

});

