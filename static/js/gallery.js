/* ========== ✅ سكربت معرض الصور (gallery.js) ========== */

/**
 * فتح المودال وعرض الصورة المختارة
 * @param {string} imgUrl - رابط الصورة
 * @param {string} imgTitle - عنوان الصورة
 */
function openModal(imgUrl, imgTitle) {
    const modal = document.getElementById("imageModal");
    const modalImg = document.getElementById("img01");
    const captionText = document.getElementById("caption");

    modal.style.display = "block";
    modalImg.src = imgUrl;
    captionText.innerHTML = imgTitle;
    
    // منع تمرير الصفحة الخلفية
    document.body.classList.add('modal-open');
}

/**
 * إغلاق المودال
 */
function closeModal() {
    const modal = document.getElementById("imageModal");
    modal.style.display = "none";
    
    // إعادة تفعيل التمرير
    document.body.classList.remove('modal-open');
}

// إغلاق المودال عند الضغط على زر Esc في لوحة المفاتيح
document.addEventListener('keydown', function(event) {
    if (event.key === "Escape") {
        closeModal();
    }
});

// إغلاق المودال عند الضغط في أي مكان خارج الصورة (على الخلفية السوداء)
window.onclick = function(event) {
    const modal = document.getElementById("imageModal");
    if (event.target === modal) {
        closeModal();
    }
};