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

    // 🔴 التعديل يبدأ من هنا لإصلاح خطأ 422 🔴
    if (!isRead && msgId) {
        // 1. جلب توكن الـ CSRF من الصفحة (تأكد من وجود حقل مخفي يحمل هذا الاسم في ملف الـ HTML)
        const csrfInput = document.querySelector('input[name="csrf_token"]');
        const csrfToken = csrfInput ? csrfInput.value : '';

        // 2. تجهيز البيانات كـ FormData ليتوافق مع Form(...) في FastAPI
        const formData = new FormData();
        formData.append('csrf_token', csrfToken);

        fetch(`/profile/mark-read/${msgId}`, {
            method: 'POST',
            body: formData, // إرسال التوكن بصيغة Form
            headers: { 
                'X-Requested-With': 'XMLHttpRequest'
                // لا تضع Content-Type يدوياً هنا، المتصفح سيقوم بضبطها تلقائياً كـ multipart/form-data
            }
        }).then(response => {
            if (response.ok) {
                button.setAttribute('data-is-read', 'true');
                const card = document.getElementById(`msg-card-${msgId}`);
                if (card) card.classList.remove('unread-msg');
                
                // 💡 تلميح اختياري: إذا أردت أن تختفي الشارة فوراً من القائمة العلوية بدون عمل تحديث كامل للصفحة:
                const badge = document.querySelector('.notification-badge');
                if (badge) {
                    let count = parseInt(badge.innerText) || 0;
                    if (count > 1) {
                        badge.innerText = count - 1;
                    } else {
                        badge.remove(); // احذف الشارة إذا كانت هذه آخر رسالة غير مقروءة
                    }
                }
            } else {
                console.error("السيرفر رفض الطلب، كود الحالة:", response.status);
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