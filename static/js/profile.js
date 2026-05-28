// ==========================================
// 1. منطق قراءة وإدارة الرسائل والمودال
// ==========================================
function handleOpenMessage(button) {
    if (!button) return;
    
    const msgId = button.getAttribute('data-id');
    const sender = button.getAttribute('data-sender');
    const fullText = button.getAttribute('data-message') || "";
    const isRead = button.getAttribute('data-is-read') === 'true';

    const modalSender = document.getElementById('modalSender');
    const fullMessageText = document.getElementById('fullMessageText');
    
    if (modalSender) modalSender.innerText = "رسالة من: " + sender;
    
    if (fullMessageText) {
        fullMessageText.innerText = fullText;
        fullMessageText.style.whiteSpace = "pre-line"; 
    }
    
    const modal = document.getElementById('messageModal');
    if (modal) modal.style.display = "block";

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

// استماع للنقر خارج المودال لإغلاقه بأمان
window.addEventListener('click', function(event) {
    const modal = document.getElementById('messageModal');
    if (event.target === modal) {
        closeModal();
    }
});

// ==========================================
// 2. منطق فحص تطابق كلمتي المرور (لحظياً)
// ==========================================
function validatePasswordsMatch() {
    const newPwdField = document.getElementById('new_password');
    const confirmPwdField = document.getElementById('confirm_password');
    const errorLabel = document.getElementById('match-error');

    // تأكيد دفاعي في حال كان الحساب أدمن ولم تظهر الحقول أصلاً في الصفحة
    if (!newPwdField || !confirmPwdField) return true;

    const newPwd = newPwdField.value;
    const confirmPwd = confirmPwdField.value;

    if (newPwd !== confirmPwd) {
        if (errorLabel) {
            errorLabel.innerText = "❌ خطأ: الحقلان غير متطابقين، يرجى كتابة تأكيد كلمة المرور بشكل صحيح.";
            errorLabel.style.display = "block";
        }
        return false;
    }
    
    if (errorLabel) errorLabel.style.display = "none";
    return true;
}