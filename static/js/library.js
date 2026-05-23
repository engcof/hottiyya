/**
 * سكربت المكتبة الرقمية - موقع الحوطية
 * مخصص لإدارة عدادات القراءة، التحميل، ومراقبة حالة الرفع
 */

function setupCounterUpdates() {
    const actionButtons = document.querySelectorAll('.btn-read, .btn-download-new');
    
    actionButtons.forEach(button => {
        button.addEventListener('click', function(e) {
            // منع النقرات المتتالية السريعة جداً (Debounce) لحماية السيرفر
            if (this.dataset.loading === "true") {
                e.preventDefault();
                return;
            }
            
            this.dataset.loading = "true";
            
            // تحديث العداد بصرياً للمستخدم فوراً
            handleCounterClick(this);
            
            // إعادة تفعيل إمكانية الضغط بعد ثانيتين
            setTimeout(() => {
                this.dataset.loading = "false";
            }, 2000);
            
            // ❌ تم حذف e.preventDefault() من هنا لكي يعمل الرابط الطبيعي للـ <a href> وينتقل المتصفح للراوتر بنجاح
        }); 
    });
}

function handleCounterClick(element) {
    const smallTag = element.querySelector('small');
    
    if (smallTag) {
        let currentText = smallTag.innerText;
        let count = parseInt(currentText.replace(/[^0-9]/g, '')) || 0;
        
        // زيادة العداد بصرياً في الصفحة الحالية
        smallTag.innerText = `(${count + 1})`;
        console.log("تم تحديث العداد البصري بنجاح.");
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