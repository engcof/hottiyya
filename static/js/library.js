   /**
 * سكربت المكتبة الرقمية - موقع الحوطية
 * مخصص لإدارة عدادات القراءة، التحميل، ومراقبة حالة الرفع
 */
/**
 * سكربت المكتبة الرقمية - نسخة منع الازدواجية البصرية
 */

function setupCounterUpdates() {
    const actionButtons = document.querySelectorAll('.btn-read, .btn-download-new');
    
    actionButtons.forEach(button => {
        // نستخدم { once: true } لضمان أن الضغطة الواحدة لا تنفذ الكود مرتين أبداً
        button.addEventListener('click', function(e) {
            handleCounterClick(this);
        }, { once: true }); 
    });
}

function handleCounterClick(element) {
    const smallTag = element.querySelector('small');
    
    if (smallTag) {
        // 1. استخراج الرقم الحالي
        let currentText = smallTag.innerText;
        let count = parseInt(currentText.replace(/[^0-9]/g, '')) || 0;
        
        // 2. التحقق: إذا كان المتصفح سيقوم بفتح صفحة جديدة (مثل القراءة)
        // فمن الأفضل عدم الزيادة يدوياً لأن الصفحة ستتحدث أصلاً
        const isViewAction = element.classList.contains('btn-read');
        
        if (!isViewAction) {
            // فقط في حالة التحميل (التي لا تغير الصفحة) نزيد الرقم بصرياً مرة واحدة
            smallTag.innerText = `(${count + 1})`;
        }
        
        console.log("تم تسجيل الضغطة وإرسال الطلب للسيرفر.");
    }
}


// 1. وظيفة مراقبة الرفع (Polling)
async function monitorUploads() {
    const pendingBooks = document.querySelectorAll('.btn-pending');
    
    // إذا لم يوجد أي كتاب قيد الرفع، نخرج من الدالة فوراً
    if (pendingBooks.length === 0) return;

    console.log("🔍 هناك كتب قيد الرفع، بدأت مراقبة الحالة...");
    
    const interval = setInterval(async () => {
        try {
            // نطلب نسخة خفيفة من الصفحة الحالية للتأكد من الحالة
            const response = await fetch(window.location.href, { cache: "no-store" });
            const html = await response.text();
            const parser = new DOMParser();
            const doc = parser.parseFromString(html, 'text/html');
            
            // نحسب عدد الكتب التي لا تزال في حالة pending في النسخة الجديدة
            const stillPending = doc.querySelectorAll('.btn-pending').length;
            
            // إذا نقص العدد، فهذا يعني أن كتاباً واحداً على الأقل اكتمل رفعه
            if (stillPending < pendingBooks.length) {
                console.log("✅ اكتمل رفع الكتاب، جاري تحديث الصفحة...");
                clearInterval(interval);
                window.location.reload(); 
            }
        } catch (error) { 
            console.error("عذراً، فشلت محاولة مراقبة الرفع:", error);
        }
    }, 10000); // الفحص يتم كل 10 ثوانٍ لتقليل استهلاك البيانات
}



// 3. تشغيل الوظائف عند اكتمال تحميل الصفحة
document.addEventListener('DOMContentLoaded', () => {
    monitorUploads();
    setupCounterUpdates();
});