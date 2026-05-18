/**
 * سكربت المكتبة الرقمية - موقع الحوطية
 * مخصص لإدارة عدادات القراءة، التحميل، ومراقبة حالة الرفع
 */

function setupCounterUpdates() {
    const actionButtons = document.querySelectorAll('.btn-read, .btn-download-new');
    
    actionButtons.forEach(button => {
        button.addEventListener('click', function(e) {
            // --- [تصحيح] بدلاً من once: true الذي يعطل الزر للأبد، نستخدم الـ Dataset لمنع النقرات المتتالية السريعة ---
            if (this.dataset.clicked === "true") {
                e.preventDefault(); // منع النقرة الثانية
                return;
            }
            
            this.dataset.clicked = "true";
            handleCounterClick(this);
            
            // إعادة تفعيل الزر بعد ثانيتين للسماح بالتحميل مرة أخرى إذا لزم الأمر
            setTimeout(() => {
                this.dataset.clicked = "false";
            }, 2000);
        }); 
    });
}

function handleCounterClick(element) {
    const smallTag = element.querySelector('small');
    
    if (smallTag) {
        let currentText = smallTag.innerText;
        let count = parseInt(currentText.replace(/[^0-9]/g, '')) || 0;
        
        const isViewAction = element.classList.contains('btn-read');
        
        // إذا لم يكن إجراء عرض (أي أنه إجراء تحميل لا يغير الصفحة الحالية)
        if (!isViewAction) {
            smallTag.innerText = `(${count + 1})`;
        }
        
        console.log("تم تسجيل الضغطة بنجاح.");
    }
}

// وظيفة مراقبة الرفع (Polling)
async function monitorUploads() {
    const pendingBooks = document.querySelectorAll('.btn-pending');
    if (pendingBooks.length === 0) return;

    console.log("🔍 هناك كتب قيد الرفع، بدأت مراقبة الحالة...");
    
    const interval = setInterval(async () => {
        try {
            const response = await fetch(window.location.href, { cache: "no-store" });
            const html = await response.text();
            const parser = new DOMParser();
            const doc = parser.parseFromString(html, 'text/html');
            
            const stillPending = doc.querySelectorAll('.btn-pending').length;
            
            if (stillPending < pendingBooks.length) {
                console.log("✅ اكتمل رفع الكتاب، جاري تحديث الصفحة...");
                clearInterval(interval);
                window.location.reload(); 
            }
        } catch (error) { 
            console.error("عذراً، فشلت محاولة مراقبة الرفع:", error);
        }
    }, 10000); 
}

// تشغيل الوظائف عند اكتمال تحميل الصفحة
document.addEventListener('DOMContentLoaded', () => {
    monitorUploads();
    setupCounterUpdates();
});