// static/js/profile.js

function handleOpenMessage(button) {
    const msgId = button.getAttribute('data-id');
    const sender = button.getAttribute('data-sender');
    const fullText = button.getAttribute('data-message');
    const isRead = button.getAttribute('data-is-read') === 'true';

    // 1. عرض البيانات
    document.getElementById('modalSender').innerText = "رسالة من: " + sender;
    document.getElementById('fullMessageText').innerHTML = fullText.replace(/\n/g, '<br>');
    
    // 2. إظهار النافذة
    document.getElementById('messageModal').style.display = "block";

    // 3. التحديث الصامت
    if (!isRead) {
        fetch(`/profile/mark-read/${msgId}`, {
            method: 'POST',
            headers: { 'X-Requested-With': 'XMLHttpRequest' }
        }).then(response => {
            if (response.ok) {
                button.setAttribute('data-is-read', 'true');
                const card = document.getElementById(`msg-card-${msgId}`);
                if (card) card.classList.remove('unread-msg');
            }
        });
    }
}

function closeModal() {
    const modal = document.getElementById('messageModal');
    if (modal) modal.style.display = "none";
}

// إغلاق النافذة عند الضغط خارجها
window.onclick = function(event) {
    const modal = document.getElementById('messageModal');
    if (event.target == modal) {
        closeModal();
    }
}