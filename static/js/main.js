document.addEventListener("DOMContentLoaded", function () {

    /* ==================== 1. القوائم (Mobile & User & Online) ==================== */
    const mobileToggle = document.getElementById("mobileToggle");
    const mobileNav = document.getElementById("mobileNav");
    const userBtn = document.getElementById("userBtn");
    const userDropdown = document.getElementById("userDropdown");
    const onlineToggle = document.getElementById('onlineToggle');
    const onlineList = document.getElementById('onlineList');

    // 1.1 قائمة الموبايل
    if (mobileToggle && mobileNav) {
        mobileToggle.addEventListener("click", function (e) {
            e.stopPropagation();
            this.classList.toggle("active");
            mobileNav.classList.toggle("active");
            mobileNav.classList.toggle("show");
        });

        mobileNav.querySelectorAll("a").forEach(link => {
            link.addEventListener("click", () => {
                mobileToggle.classList.remove("active");
                mobileNav.classList.remove("active");
                mobileNav.classList.remove("show");
            });
        });
    }

    // 1.2 قائمة المستخدم
    if (userBtn && userDropdown) {
        userBtn.addEventListener("click", function (e) {
            e.stopPropagation();
            // إغلاق قائمة الأونلاين إذا كانت مفتوحة
            document.getElementById('onlineList')?.classList.remove("show");
            document.getElementById('onlineToggle')?.classList.remove("active");
            userDropdown.classList.toggle("show");
        });
    }

    // 1.3 إغلاق كل القوائم عند الضغط في أي مكان
    document.addEventListener("click", function (e) {
        if (userDropdown && !userBtn?.contains(e.target)) userDropdown.classList.remove("show");
        if (mobileNav && !mobileToggle?.contains(e.target) && !mobileNav.contains(e.target)) {
            mobileToggle?.classList.remove("active");
            mobileNav?.classList.remove("active");
            mobileNav?.classList.remove("show");
        }
    });

    /* ==================== 2. قائمة المستخدمين أونلاين (Portal) ==================== */
    if (onlineToggle && onlineList) {
        const portal = document.getElementById('onlineDropdownPortal');
        const originalParent = onlineList.parentElement;

        function show() {
            portal.appendChild(onlineList);
            const rect = onlineToggle.getBoundingClientRect();
            portal.style.left = Math.max(8, rect.left + rect.width / 2 - onlineList.offsetWidth / 2) + 'px';
            portal.style.top = (rect.bottom + 10) + 'px';
            portal.style.pointerEvents = 'all';
            
            Object.assign(onlineList.style, { opacity: '1', visibility: 'visible', pointerEvents: 'all', transform: 'translateY(0)' });
            onlineToggle.classList.add('active');
            userDropdown?.classList.remove("show");
        }

        function hide() {
            if (originalParent) originalParent.appendChild(onlineList);
            Object.assign(onlineList.style, { opacity: '0', visibility: 'hidden', pointerEvents: 'none', transform: 'translateY(-10px)' });
            portal.style.pointerEvents = 'none';
            onlineToggle.classList.remove('active');
        }

        onlineToggle.addEventListener('click', e => { e.stopPropagation(); onlineToggle.classList.contains('active') ? hide() : show(); });
        document.addEventListener('click', e => { if (!onlineToggle.contains(e.target) && !onlineList.contains(e.target)) hide(); });
    }

    /* ==================== 3. وظائف أخرى (Flash, Scroll, Inline, Confirm) ==================== */
    // الرسائل
    document.querySelectorAll('.flash-message, #success-alert').forEach(msg => {
        setTimeout(() => { msg.style.transition = 'opacity 0.6s'; msg.style.opacity = '0'; setTimeout(() => msg.remove(), 600); }, 5000);
    });

    // الـ Header عند التمرير
    window.addEventListener("scroll", () => {
        const header = document.querySelector("header");
        header?.classList.toggle("scrolled", window.scrollY > 50);
    });

    // تأكيد الحذف
    document.querySelectorAll('form[onsubmit*="confirm"]').forEach(form => {
        if (!form.dataset.confirmHooked) {
            form.addEventListener('submit', function(e) {
                const match = this.getAttribute('onsubmit').match(/confirm\(['"]([^'"]+)['"]\)/);
                if (match && !confirm(match[1])) e.preventDefault();
            });
            form.dataset.confirmHooked = "true";
        }
    });

    // الـ Ticker
    const tickerInner = document.getElementById('tickerInner');
    if (tickerInner) {
        tickerInner.innerHTML += tickerInner.innerHTML + tickerInner.innerHTML;
        let pos = 0;
        function animate() {
            pos += 0.5;
            tickerInner.style.transform = `translateX(-${pos}px)`;
            if (pos >= tickerInner.scrollWidth / 3) pos = 0;
            requestAnimationFrame(animate);
        }
        animate();
    }
});