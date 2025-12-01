document.addEventListener("DOMContentLoaded", function () {

    /* ==================== قائمة الموبايل (الهامبرجر) ==================== */
    const mobileToggle = document.getElementById("mobileToggle");
    const mobileNav = document.getElementById("mobileNav");
    if (mobileToggle && mobileNav) {
        mobileToggle.addEventListener("click", function (e) {
            e.stopPropagation();
            mobileToggle.classList.toggle("active");
            mobileNav.classList.toggle("active");
        });

        mobileNav.querySelectorAll("a").forEach(link => {
            link.addEventListener("click", () => {
                mobileToggle.classList.remove("active");
                mobileNav.classList.remove("active");
            });
        });

        document.addEventListener("click", function (e) {
            if (!mobileToggle.contains(e.target) && !mobileNav.contains(e.target)) {
                mobileToggle.classList.remove("active");
                mobileNav.classList.remove("active");
            }
        });

        mobileNav.addEventListener("click", e => e.stopPropagation());
    }

    /* ==================== دروب داون المستخدم (الديسكتوب) ==================== */
    const userBtn = document.getElementById("userBtn");
    const userDropdown = document.getElementById("userDropdown");
    if (userBtn && userDropdown) {
        userBtn.addEventListener("click", function (e) {
            e.stopPropagation();
            userDropdown.classList.toggle("show");
        });

        document.addEventListener("click", function () {
            userDropdown.classList.remove("show");
        });

        userDropdown.addEventListener("click", e => e.stopPropagation());
    }

    /* ==================== إغلاق كل القوائم عند الضغط على ESC ==================== */
    document.addEventListener("keydown", function (e) {
        if (e.key === "Escape") {
            mobileToggle?.classList.remove("active");
            mobileNav?.classList.remove("active");
            userDropdown?.classList.remove("show");
        }
    });

    /* ==================== تأثير الـ Header عند التمرير (جمالي ملكي) ==================== */
    window.addEventListener("scroll", function () {
        const header = document.querySelector("header");
        if (window.scrollY > 50) {
            header?.classList.add("scrolled");
        } else {
            header?.classList.remove("scrolled");
        }
    });

    /* ==================== تعديل الصلاحيات داخل الجدول (Inline Editing) - ملكي وذكي ==================== */
    // يشتغل فقط في صفحة الصلاحيات
    const inlineInputs = document.querySelectorAll('.inline-input');
    if (inlineInputs.length > 0) {
        inlineInputs.forEach(input => {
            input.addEventListener('input', function () {
                const form = this.closest('form');
                const permId = form.querySelector('input[name="perm_id"]').value;

                // جلب فورم الحفظ المخفي
                const saveForm = document.getElementById('edit-form-' + permId);
                if (!saveForm) return;

                // تحديث الحقول المخفية تلقائيًا
                const hiddenName = saveForm.querySelector('input[name="name"]');
                const hiddenCategory = saveForm.querySelector('input[name="category"]');

                if (this.name === 'name' && hiddenName) {
                    hiddenName.value = this.value;
                } else if (this.name === 'category' && hiddenCategory) {
                    hiddenCategory.value = this.value;
                }

                // إضافة كلاس "تم التعديل" لتأثير بصري فاخر
                this.classList.add('changed');

                // إزالة الكلاس بعد 2 ثانية (اختياري - جمالي)
                clearTimeout(this.changedTimeout);
                this.changedTimeout = setTimeout(() => {
                    this.classList.remove('changed');
                }, 2000);
            });
        });
    }

    /* ==================== تأكيد الحذف في كل الصفحات (حماية ملكية) ==================== */
    // هذه الدالة تم تفعيلها لمنع استخدام alert/confirm الافتراضية المحظورة
    // ولكن في هذا المشروع نحن نستخدم forms دون الحاجة لـ confirm حاليًا في admin.html
    document.querySelectorAll('form[onsubmit*="confirm"]').forEach(form => {
        if (!form.dataset.confirmHooked) {
            form.addEventListener('submit', function (e) {
                const message = this.getAttribute('onsubmit').match(/confirm\(['"]([^'"]+)['"]\)/);
                if (message && !confirm(message[1])) {
                    e.preventDefault();
                }
            });
            form.dataset.confirmHooked = "true";
        }
    });


});