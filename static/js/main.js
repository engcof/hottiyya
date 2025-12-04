document.addEventListener("DOMContentLoaded", function () {

    /* ==================== تعريف المتغيرات العامة ==================== */
    const mobileToggle   = document.getElementById("mobileToggle");
    const mobileNav      = document.getElementById("mobileNav");
    const userBtn        = document.getElementById("userBtn");
    const userDropdown   = document.getElementById("userDropdown");
    const onlineToggle   = document.getElementById("onlineToggle");
    const onlineList     = document.getElementById("onlineList");
    const tickerInner    = document.querySelector(".ticker-inner");


    /* ==================== قائمة الموبايل (Hamburger Menu) ==================== */
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


    /* ==================== دروب داون المستخدم (Desktop User Dropdown) ==================== */
    if (userBtn && userDropdown) {
        userBtn.addEventListener("click", function (e) {
            e.stopPropagation();

            // إغلاق قائمة الأونلاين
            onlineList?.classList.remove("show");
            onlineToggle?.classList.remove("active");

            userDropdown.classList.toggle("show");
        });

        document.addEventListener("click", () => {
            userDropdown.classList.remove("show");
        });

        userDropdown.addEventListener("click", e => e.stopPropagation());
    }


    /* ==================== قائمة المستخدمين أونلاين (مع fixed positioning) ==================== */
        if (document.getElementById('onlineToggle')) {
        const toggle = document.getElementById('onlineToggle');
        const list = document.getElementById('onlineList');
        const portal = document.getElementById('onlineDropdownPortal');

        // إخفاء أولي
        list.style.opacity = '0';
        list.style.visibility = 'hidden';
        list.style.pointerEvents = 'none';
        list.style.transition = 'opacity 0.25s ease, transform 0.25s ease';
        list.style.transform = 'translateY(-10px)';

        function show() {
            const rect = toggle.getBoundingClientRect();
            const left = rect.left + rect.width / 2 - list.offsetWidth / 2;
            const top = rect.bottom + 10;

            portal.style.left = Math.max(8, left) + 'px';
            portal.style.top = top + 'px';
            portal.style.pointerEvents = 'all';

            list.style.opacity = '1';
            list.style.visibility = 'visible';
            list.style.pointerEvents = 'all';
            list.style.transform = 'translateY(0)';
            toggle.classList.add('active');
        }

        function hide() {
            list.style.opacity = '0';
            list.style.visibility = 'hidden';
            list.style.pointerEvents = 'none';
            list.style.transform = 'translateY(-10px)';
            portal.style.pointerEvents = 'none';
            toggle.classList.remove('active');
        }

        toggle.addEventListener('click', e => {
            e.stopPropagation();
            if (toggle.classList.contains('active')) hide();
            else show();
        });

        document.addEventListener('click', e => {
            if (!toggle.contains(e.target) && !list.contains(e.target)) hide();
        });

        // تحديث الموقع لو سكرولت وهي مفتوحة
        window.addEventListener('scroll', () => {
            if (toggle.classList.contains('active')) show();
        });
    }
    /* ==================== إغلاق كل القوائم عند الضغط على ESC ==================== */
    document.addEventListener("keydown", function (e) {
        if (e.key === "Escape") {
            mobileToggle?.classList.remove("active");
            mobileNav?.classList.remove("active");
            userDropdown?.classList.remove("show");
            onlineList?.classList.remove("show");
            onlineToggle?.classList.remove("active");
        }
    });


    /* ==================== تأثير الـ Header عند التمرير ==================== */
    window.addEventListener("scroll", function () {
        const header = document.querySelector("header");
        if (window.scrollY > 50) header?.classList.add("scrolled");
        else header?.classList.remove("scrolled");
    });


    /* ==================== تعديل الصلاحيات Inline Editing ==================== */
    const inlineInputs = document.querySelectorAll('.inline-input');
    if (inlineInputs.length > 0) {
        inlineInputs.forEach(input => {
            input.addEventListener('input', function () {
                const form = this.closest('form');
                const permId = form.querySelector('input[name="perm_id"]').value;

                const saveForm = document.getElementById('edit-form-' + permId);
                if (!saveForm) return;

                const hiddenName = saveForm.querySelector('input[name="name"]');
                const hiddenCategory = saveForm.querySelector('input[name="category"]');

                if (this.name === 'name' && hiddenName) hiddenName.value = this.value;
                if (this.name === 'category' && hiddenCategory) hiddenCategory.value = this.value;

                this.classList.add('changed');
                clearTimeout(this.changedTimeout);
                this.changedTimeout = setTimeout(() => {
                    this.classList.remove('changed');
                }, 2000);
            });
        });
    }


    /* ==================== تأكيد الحذف ==================== */
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


    /* ==================== شريط آخر الأخبار / المقالات (Ticker) ==================== */
    if (tickerInner) {

        const content = tickerInner.innerHTML;
        tickerInner.innerHTML = content + content + content;

        let scrollPosition = 0;
        const speed = 0.5;

        function startTickerScroll() {
            scrollPosition += speed;
            tickerInner.style.transform = `translateX(-${scrollPosition}px)`;

            const contentWidth = tickerInner.scrollWidth / 3;
            if (scrollPosition >= contentWidth) scrollPosition = 0;

            requestAnimationFrame(startTickerScroll);
        }

        requestAnimationFrame(startTickerScroll);
    }

});
