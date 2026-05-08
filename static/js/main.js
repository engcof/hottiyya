document.addEventListener("DOMContentLoaded", function () {

    /* ==================== 1. القوائم (Mobile & User & Online) ==================== */
    const mobileToggle = document.getElementById("mobileToggle");
    const mobileNav = document.getElementById("mobileNav");
    const userBtn = document.getElementById("userBtn");
    const userDropdown = document.getElementById("userDropdown");
    const onlineToggle = document.getElementById('onlineToggle');
    const onlineList = document.getElementById('onlineList');

// --- إضافة: تحديد الرابط النشط تلقائياً (نسخة مطورة) ---
    const currentPath = window.location.pathname.replace(/\/$/, ""); // إزالة الشرطة المائلة الأخيرة إن وجدت
    const allNavLinks = document.querySelectorAll('.nav-links a, .mobile-nav a');
    
    allNavLinks.forEach(link => {
        const linkPath = link.getAttribute('href').replace(/\/$/, "");
        
        // 1. حالة الصفحة الرئيسية (تطابق تام)
        if (linkPath === "" && currentPath === "") {
            link.classList.add('active');
        } 
        // 2. باقي الصفحات (تطابق المسار أو أن يكون جزءاً من المسار الحالي)
        // هذا يسمح ببقاء قسم "المقالات" فعالاً حتى لو كنت تقرأ مقالة فرعية
        else if (linkPath !== "" && currentPath.startsWith(linkPath)) {
            link.classList.add('active');
        } 
        else {
            link.classList.remove('active');
        }
    });

    // 1.1 قائمة الموبايل
    if (mobileToggle && mobileNav) {
        mobileToggle.addEventListener("click", function (e) {
            e.stopPropagation();
            this.classList.toggle("active");
            mobileNav.classList.toggle("active");
            // مسح كلاس show إذا كنت تستخدم opacity/visibility للتنقل
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
            // إغلاق القوائم الأخرى عند فتح قائمة المستخدم
            document.getElementById('onlineList')?.classList.remove("show");
            document.getElementById('onlineToggle')?.classList.remove("active");
            mobileNav?.classList.remove("active"); // إغلاق قائمة الموبايل أيضاً
            
            userDropdown.classList.toggle("show");
        });
    }

    // 1.3 إغلاق كل القوائم عند الضغط في أي مكان خارجها
    document.addEventListener("click", function (e) {
        // إغلاق دروب داون المستخدم
        if (userDropdown && !userBtn?.contains(e.target) && !userDropdown.contains(e.target)) {
            userDropdown.classList.remove("show");
        }
        // إغلاق قائمة الموبايل
        if (mobileNav && mobileNav.classList.contains('active') && !mobileToggle?.contains(e.target) && !mobileNav.contains(e.target)) {
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
            
            // بدلاً من أخذ قياسات الزر الصغير، نأخذ قياسات "النوتة" الأب
            const parentCard = onlineToggle.closest('.stat-card'); 
            const rect = parentCard.getBoundingClientRect(); 
            
            const scrollY = window.scrollY || window.pageYOffset;
            const scrollX = window.scrollX || window.pageXOffset;

            // الحساب الجديد لضمان التوسيط تحت النوتة تماماً
            portal.style.left = (rect.left + scrollX + rect.width / 2) + 'px'; 
            portal.style.top = (rect.bottom + scrollY + 10) + 'px';
            portal.style.transform = 'translateX(-50%)'; // السحر هنا لتوسيط القائمة مهما كان عرضها
            portal.style.pointerEvents = 'all';
            
            Object.assign(onlineList.style, { 
                opacity: '1', 
                visibility: 'visible', 
                pointerEvents: 'all', 
                transform: 'translateY(0)' 
            });
            onlineToggle.classList.add('active');
        }

        function hide() {
            if (originalParent) originalParent.appendChild(onlineList);
            Object.assign(onlineList.style, { opacity: '0', visibility: 'hidden', pointerEvents: 'none', transform: 'translateY(-10px)' });
            portal.style.pointerEvents = 'none';
            onlineToggle.classList.remove('active');
        }

        onlineToggle.addEventListener('click', e => { 
            e.stopPropagation(); 
            // إغلاق القوائم الأخرى عند فتح الأونلاين
            userDropdown?.classList.remove("show");
            onlineToggle.classList.contains('active') ? hide() : show(); 
        });

        document.addEventListener('click', e => { 
            if (!onlineToggle.contains(e.target) && !onlineList.contains(e.target)) hide(); 
        });
    }

    /* ==================== 3. وظائف أخرى (Flash, Scroll, Ticker) ==================== */
    // تلاشي رسائل النظام تلقائياً
    document.querySelectorAll('.flash-message, #success-alert').forEach(msg => {
        setTimeout(() => { 
            msg.style.transition = 'opacity 0.6s'; 
            msg.style.opacity = '0'; 
            setTimeout(() => msg.remove(), 600); 
        }, 5000);
    });

    // تأثير الهيدر عند التمرير (Scrolled State)
    window.addEventListener("scroll", () => {
        const header = document.querySelector("header");
        if (header) {
            header.classList.toggle("scrolled", window.scrollY > 50);
        }
    });

    // شريط الأخبار المتحرك (Ticker)
    const tickerInner = document.getElementById('tickerInner');
    if (tickerInner) {
        tickerInner.innerHTML += tickerInner.innerHTML + tickerInner.innerHTML; // مضاعفة المحتوى لسلاسة الحركة
        let pos = 0;
        function animate() {
            pos += 0.5; // سرعة الحركة
            tickerInner.style.transform = `translateX(-${pos}px)`;
            if (pos >= tickerInner.scrollWidth / 3) pos = 0;
            requestAnimationFrame(animate);
        }
        animate();
    }
});