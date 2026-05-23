/* ========== ✅ سكربت معرض الصور المحدث (gallery.js) ========== */

/**
 * فتح المودال وعرض الصورة المختارة
 * @param {string} imgUrl - رابط الصورة
 * @param {string} imgTitle - عنوان الصورة
 */
function openModal(imgUrl, imgTitle) {
    const modal = document.getElementById("imageModal");
    const modalImg = document.getElementById("img01");
    const captionText = document.getElementById("caption");

    if (modal && modalImg) {
        // 🌟 تعديل السطر لفرض الـ flex وإلغاء الـ none الافتراضي
        modal.style.setProperty('display', 'flex', 'important'); 
        
        modalImg.src = imgUrl;
        if (captionText) captionText.innerHTML = imgTitle;
        
        // منع تمرير الصفحة الخلفية
        document.body.classList.add('modal-open');
    }
}

/**
 * إغلاق المودال
 */
function closeModal() {
    const modal = document.getElementById("imageModal");
    if (modal) {
        // 🌟 إرجاع الخاصية لـ none لإخفاء المودال مجدداً بأمان
        modal.style.setProperty('display', 'none', 'important'); 
        
        // إعادة تفعيل التمرير
        document.body.classList.remove('modal-open');
    }
}

// عزل الأحداث وانتظار تحميل الـ DOM لحماية المتصفح
document.addEventListener('DOMContentLoaded', () => {

    // إغلاق المودال عند الضغط على زر Esc في لوحة المفاتيح
    document.addEventListener('keydown', function(event) {
        if (event.key === "Escape") {
            closeModal();
        }
    });

    // إغلاق المودال عند الضغط على الخلفية باستخدام الطريقة القياسية الآمنة
    document.addEventListener('click', function(event) {
        const modal = document.getElementById("imageModal");
        if (modal && event.target === modal) {
            closeModal();
        }
    });
});