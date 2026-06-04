/* ========== ✅ سكربت معرض الصور المحدث والآمن (gallery.js) ========== */

/**
 * فتح المودال وعرض الصورة المختارة مع حماية شاملة من ثغرات XSS
 */
function openModal(imgUrl, imgTitle) {
    const modal = document.getElementById("imageModal");
    const modalImg = document.getElementById("img01");
    const captionText = document.getElementById("caption");

    if (modal && modalImg) {
        modal.style.setProperty('display', 'flex', 'important'); 
        modalImg.src = imgUrl;
        
        if (captionText) {
            // 🔒 حماية XSS صارمة باستخدام textContent
            captionText.textContent = imgTitle; 
        }
        
        document.body.classList.add('modal-open');
    }
}

/**
 * إغلاق المودال
 */
function closeModal() {
    const modal = document.getElementById("imageModal");
    if (modal) {
        modal.style.setProperty('display', 'none', 'important'); 
        document.body.classList.remove('modal-open');
    }
}

// مراقبة الأحداث وانتظار تحميل الـ DOM
document.addEventListener('DOMContentLoaded', () => {

    // 🚀 إلغاء الـ onclick من الـ HTML وإدارته هنا برمجياً بطريقة engcof الاحترافية
    const galleryItems = document.querySelectorAll('.gallery-clickable-item');
    galleryItems.forEach(item => {
        item.addEventListener('click', function() {
            const url = this.getAttribute('data-url');
            const title = this.getAttribute('data-title');
            openModal(url, title);
        });
    });

    // إغلاق المودال عند الضغط على زر Esc
    document.addEventListener('keydown', function(event) {
        if (event.key === "Escape") {
            closeModal();
        }
    });

    // إغلاق المودال عند الضغط على الخلفية الضبابية للمودال
    document.addEventListener('click', function(event) {
        const modal = document.getElementById("imageModal");
        if (modal && event.target === modal) {
            closeModal();
        }
    });
});