/* ========== ✅ الملف الرئيسي العام للموقع المطور والمؤمن (main.js) ========== */
document.addEventListener("DOMContentLoaded", function () {

    /* ==================== 1. القوائم وتحديد الروابط النشطة ==================== */
    const mobileToggle = document.getElementById("mobileToggle");
    const mobileNav = document.getElementById("mobileNav");
    const userBtn = document.getElementById("userBtn");
    const userDropdown = document.getElementById("userDropdown");
    const onlineToggle = document.getElementById('onlineToggle');
    const onlineList = document.getElementById('onlineList');
    const portal = document.getElementById('onlineDropdownPortal');

    // --- دالة إغلاق الأونلاين الموحدة والمصححة لمنع التضارب ---
    function hideOnlineList() {
        if (!onlineToggle || !onlineList) return;
        
        // 1. سحب كلاس العرض من القائمة لتختفي بصرياً بناءً على قواعد الـ CSS
        onlineList.classList.remove('show');
        
        // 2. إزالة الفتح من السهم ليعود لوضعه الطبيعي
        onlineToggle.classList.remove('active');
        onlineToggle.setAttribute('aria-expanded', 'false');
        
        // 3. إعادة القائمة لمكانها الأصلي داخل كرت الإحصائيات (النوتة)
        const originalParent = document.querySelector('.online-stat'); 
        if (originalParent && onlineList.parentElement === portal) {
            originalParent.appendChild(onlineList);
        }
        
        // 4. حجب بورتال العرض الخارجي
        if (portal) {
            portal.style.display = 'none';
        }
    }

    // إتاحة الدالة الموحدة للنطاق العالمي (Global Scope) لتستدعيها بقية القوائم بأمان
    window.hideOnlineList = hideOnlineList;

    // تحديد الرابط النشط تلقائياً في القائمة
    const currentPath = window.location.pathname.replace(/\/$/, ""); 
    const allNavLinks = document.querySelectorAll('.nav-links a, .mobile-nav a');
    
    allNavLinks.forEach(link => {
        const href = link.getAttribute('href');
        if (!href) return;
        const linkPath = href.replace(/\/$/, "");
        if (linkPath === "" && currentPath === "") {
            link.classList.add('active');
        } else if (linkPath !== "" && currentPath.startsWith(linkPath)) {
            link.classList.add('active');
        } else {
            link.classList.remove('active');
        }
    });

    // 1.1 قائمة الموبايل التفاعلية
    if (mobileToggle && mobileNav) {
        mobileToggle.addEventListener("click", function (e) {
            e.stopPropagation();
            this.classList.toggle("active");
            mobileNav.classList.toggle("active");
            mobileNav.classList.toggle("show"); 
            userDropdown?.classList.remove("show"); 
            hideOnlineList(); // تستدعي الدالة المصححة الآن بنجاح
        });

        mobileNav.querySelectorAll("a").forEach(link => {
            link.addEventListener("click", () => {
                mobileToggle.classList.remove("active");
                mobileNav.classList.remove("active");
                mobileNav.classList.remove("show");
            });
        });
    }

    // 1.2 قائمة حساب المستخدم
    if (userBtn && userDropdown) {
        userBtn.addEventListener("click", function (e) {
            e.stopPropagation();
            hideOnlineList(); // تستدعي الدالة المصححة الآن بنجاح
            if (mobileNav) {
                mobileNav.classList.remove("active", "show");
                mobileToggle?.classList.remove("active");
            }
            userDropdown.classList.toggle("show");
        });
    }

    // 1.3 إغلاق كافة القوائم المنسدلة الذكي عند الضغط الخارجي
    document.addEventListener("click", function (e) {
        if (userDropdown && !userBtn?.contains(e.target) && !userDropdown.contains(e.target)) {
            userDropdown.classList.remove("show");
        }
        if (mobileNav && mobileNav.classList.contains('active') && !mobileToggle?.contains(e.target) && !mobileNav.contains(e.target)) {
            mobileToggle?.classList.remove("active");
            mobileNav.classList.remove("active", "show");
        }
    });


    /* ==================== 2. قائمة المستخدمين أونلاين المحدثة ==================== */
    if (onlineToggle && onlineList) {
        function showOnlineList() {
            // تفعيل الكلاسات الأساسية للـ CSS لتبدأ الأنيميشن فوراً
            onlineList.classList.add('show');
            onlineToggle.classList.add('active');
            onlineToggle.setAttribute('aria-expanded', 'true');

            // إذا كان الـ Portal موجوداً، نقوم بحساب الإحداثيات المطلقة بدقة فوق كل الكروت
            if (portal) {
                portal.appendChild(onlineList);
                const parentCard = onlineToggle.closest('.stat-card'); 
                if (!parentCard) return;
                
                const rect = parentCard.getBoundingClientRect(); 
                const scrollY = window.scrollY || window.pageYOffset;
                const scrollX = window.scrollX || window.pageXOffset;

                portal.style.left = (rect.left + scrollX + rect.width / 2) + 'px'; 
                portal.style.top = (rect.bottom + scrollY + 8) + 'px';
                portal.style.display = 'block';
            }
        }

        // تفاعل الضغط على زر الأونلاين (فتح / إغلاق تبادلي)
        onlineToggle.addEventListener('click', function(e) { 
            e.stopPropagation(); 
            userDropdown?.classList.remove("show"); 
            if (mobileNav) mobileNav.classList.remove("active", "show");
            
            // الفحص بالاعتماد على الكلاس الفعلي المستقر
            if (onlineToggle.classList.contains('active')) {
                hideOnlineList();
            } else {
                showOnlineList();
            }
        });

        // جدار حماية آمن للإغلاق عند الضغط في أي مكان خارجي
        document.addEventListener('click', function(e) { 
            if (!onlineToggle.contains(e.target) && !onlineList.contains(e.target)) {
                hideOnlineList(); 
            }
        });
    }

    /* ==================== 3. تأثيرات عامة التنبيهات والأخبار وتطهير الروابط ==================== */
    document.querySelectorAll('.flash-message, .alert, #success-alert, #error-alert').forEach(msg => {
        setTimeout(() => { 
            msg.style.transition = 'opacity 0.6s ease, transform 0.6s ease'; 
            msg.style.opacity = '0'; 
            msg.style.transform = 'translateY(-10px)';
            setTimeout(() => msg.remove(), 600); 
        }, 5000);
    });

    // ✨ تنظيف شريط العنوان في المتصفح فوراً لحماية الصفحة من تكرار الرسائل عند عمل Refresh
    try {
        const currentUrl = new URL(window.location.href);
        if (currentUrl.searchParams.has('success') || currentUrl.searchParams.has('error')) {
            // مسح بارامترات الحالة فقط والحفاظ على بقية البارامترات مثل رقم الصفحة (page) والبحث (q)
            currentUrl.searchParams.delete('success');
            currentUrl.searchParams.delete('error');
            
            // إحلال الرابط النظيف في المتصفح بدون إعادة تحميل الصفحة
            window.history.replaceState({}, document.title, currentUrl.pathname + currentUrl.search);
        }
    } catch (urlErr) {
        console.error("خطأ أثناء تنظيف رابط المتصفح:", urlErr);
    }

    /* ========================================================================= */

    window.addEventListener("scroll", () => {
        const header = document.querySelector("header");
        if (header) header.classList.toggle("scrolled", window.scrollY > 50);
    });

    // تحريك شريط الأخبار اللانهائي برمجياً بدقة فائقة
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