/* ========== ✅ الملف الرئيسي العام للموقع (main.js) ========== */
document.addEventListener("DOMContentLoaded", function () {

    /* ==================== 1. القوائم وتحديد الروابط النشطة ==================== */
    const mobileToggle = document.getElementById("mobileToggle");
    const mobileNav = document.getElementById("mobileNav");
    const userBtn = document.getElementById("userBtn");
    const userDropdown = document.getElementById("userDropdown");
    const onlineToggle = document.getElementById('onlineToggle');
    const onlineList = document.getElementById('onlineList');
    const portal = document.getElementById('onlineDropdownPortal');

    // --- [تصحيح] تعريف دالة إغلاق الأونلاين في الأعلى لتكون متاحة لبقية القوائم فوراً ---
    function hideOnlineList() {
        if (!onlineToggle || !onlineList) return;
        
        const originalParent = document.querySelector('.online-stat'); // الأب الأصلي
        if (originalParent && onlineList.parentElement === portal) {
            originalParent.appendChild(onlineList);
        }
        
        Object.assign(onlineList.style, { opacity: '0', visibility: 'hidden', pointerEvents: 'none', transform: 'translateY(-10px)' });
        if (portal) {
            portal.style.pointerEvents = 'none';
            portal.style.display = 'none';
        }
        onlineToggle.classList.remove('active');
        onlineToggle.setAttribute('aria-expanded', 'false');
    }

    // إتاحة الدالة للنطاق العالمي (Global Scope)
    window.hideOnlineList = hideOnlineList;

    // تحديد الرابط النشط تلقائياً في القائمة
    const currentPath = window.location.pathname.replace(/\/$/, ""); 
    const allNavLinks = document.querySelectorAll('.nav-links a, .mobile-nav a');
    
    allNavLinks.forEach(link => {
        const linkPath = link.getAttribute('href').replace(/\/$/, "");
        if (linkPath === "" && currentPath === "") {
            link.classList.add('active');
        } else if (linkPath !== "" && currentPath.startsWith(linkPath)) {
            link.classList.add('active');
        } else {
            link.classList.remove('active');
        }
    });

    // 1.1 قائمة الموبايل
    if (mobileToggle && mobileNav) {
        mobileToggle.addEventListener("click", function (e) {
            e.stopPropagation();
            this.classList.toggle("active");
            mobileNav.classList.toggle("active");
            mobileNav.classList.toggle("show"); 
            userDropdown?.classList.remove("show"); // إغلاق قائمة المستخدم
            hideOnlineList(); // إغلاق الأونلاين
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
            hideOnlineList();
            mobileNav?.classList.remove("active");
            mobileNav?.classList.remove("show");
            mobileToggle?.classList.remove("active");
            
            userDropdown.classList.toggle("show");
        });
    }

    // 1.3 إغلاق القوائم عند الضغط خارجها
    document.addEventListener("click", function (e) {
        if (userDropdown && !userBtn?.contains(e.target) && !userDropdown.contains(e.target)) {
            userDropdown.classList.remove("show");
        }
        if (mobileNav && mobileNav.classList.contains('active') && !mobileToggle?.contains(e.target) && !mobileNav.contains(e.target)) {
            mobileToggle?.classList.remove("active");
            mobileNav?.classList.remove("active");
            mobileNav?.classList.remove("show");
        }
    });

    /* ==================== 2. قائمة المستخدمين أونلاين (Portal) ==================== */
    if (onlineToggle && onlineList && portal) {
        function showOnlineList() {
            portal.appendChild(onlineList);
            const parentCard = onlineToggle.closest('.stat-card'); 
            if (!parentCard) return;
            
            const rect = parentCard.getBoundingClientRect(); 
            const scrollY = window.scrollY || window.pageYOffset;
            const scrollX = window.scrollX || window.pageXOffset;

            portal.style.left = (rect.left + scrollX + rect.width / 2) + 'px'; 
            portal.style.top = (rect.bottom + scrollY + 10) + 'px';
            portal.style.transform = 'translateX(-50%)'; 
            portal.style.pointerEvents = 'all';
            portal.style.display = 'block';
            
            Object.assign(onlineList.style, { 
                opacity: '1', 
                visibility: 'visible', 
                pointerEvents: 'all', 
                transform: 'translateY(0)' 
            });
            onlineToggle.classList.add('active');
            onlineToggle.setAttribute('aria-expanded', 'true');
        }

        onlineToggle.addEventListener('click', e => { 
            e.stopPropagation(); 
            userDropdown?.classList.remove("show"); 
            mobileNav?.classList.remove("active"); 
            onlineToggle.classList.contains('active') ? hideOnlineList() : showOnlineList(); 
        });

        document.addEventListener('click', e => { 
            if (!onlineToggle.contains(e.target) && !onlineList.contains(e.target)) hideOnlineList(); 
        });
    }

    /* ==================== 3. تأثيرات عامة (Flash & Scroll & Ticker) ==================== */
    // [تحسين] شمل كافة التنبيهات الموحدة بالصفحات (Success & Error Alerts) للاختفاء التلقائي
    document.querySelectorAll('.flash-message, .alert, #success-alert, #error-alert').forEach(msg => {
        setTimeout(() => { 
            msg.style.transition = 'opacity 0.6s ease'; 
            msg.style.opacity = '0'; 
            setTimeout(() => msg.remove(), 600); 
        }, 5000);
    });

    window.addEventListener("scroll", () => {
        const header = document.querySelector("header");
        if (header) header.classList.toggle("scrolled", window.scrollY > 50);
    });

    // شريط الأخبار المتحرك برمجياً
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