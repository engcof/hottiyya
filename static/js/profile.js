// static/js/profile.js

function handleOpenMessage(button) {
    if (!button) return;
    
    const msgId = button.getAttribute('data-id');
    const sender = button.getAttribute('data-sender');
    const fullText = button.getAttribute('data-message') || "";
    const isRead = button.getAttribute('data-is-read') === 'true';

    // 1. عرض البيانات بأمان تام (XSS Protection)
    const modalSender = document.getElementById('modalSender');
    const fullMessageText = document.getElementById('fullMessageText');
    
    if (modalSender) modalSender.innerText = "رسالة من: " + sender;
    
    // استخدام تكتيك التطهير النصي الآمن مع الحفاظ على الأسطر الجديدة
    if (fullMessageText) {
        fullMessageText.innerText = fullText;
        fullMessageText.style.whiteSpace = "pre-line"; // ميزة CSS مذهلة تحول \n لأسطر جديدة دون استخدام innerHTML الخطر
    }
    
    // 2. إظهار النافذة
    const modal = document.getElementById('messageModal');
    if (modal) modal.style.display = "block";

    // 3. التحديث الصامت عبر السيرفر (AJAX Fetch)
    if (!isRead && msgId) {
        fetch(`/profile/mark-read/${msgId}`, {
            method: 'POST',
            headers: { 'X-Requested-With': 'XMLHttpRequest' }
        }).then(response => {
            if (response.ok) {
                button.setAttribute('data-is-read', 'true');
                const card = document.getElementById(`msg-card-${msgId}`);
                if (card) card.classList.remove('unread-msg');
            }
        }).catch(err => console.error("فشل التحديث المتزامن لحالة القراءة:", err));
    }
}

function closeModal() {
    const modal = document.getElementById('messageModal');
    if (modal) modal.style.display = "none";
}

// [تصحيح جوهري] استخدام استماع الأحداث لتجنب قتل الأكواد الأخرى في الموقع من قِبل window.onclick
window.addEventListener('click', function(event) {
    const modal = document.getElementById('messageModal');
    if (event.target === modal) {
        closeModal();
    }
});