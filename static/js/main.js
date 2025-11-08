  // منع العودة بعد Logout
if (window.history.replaceState) {
    window.history.replaceState(null, null, window.location.href);
}
window.onload = function() {
    window.addEventListener("pageshow", function(event) {
        if (event.persisted) {
            window.location.reload();
        }
    });
}

// مسح الفورم عند عمل Back
window.addEventListener('pageshow', function(event) {
    if (event.persisted) {
        document.querySelectorAll('form').forEach(form => form.reset());
    }
});

// تفعيل الرسائل المنبثقة
window.addEventListener('DOMContentLoaded', () => {
    const toast = document.getElementById('toast');
    if (toast) {
        toast.classList.add('show');
        setTimeout(() => {
            toast.classList.remove('show');
        }, 2000); // تظهر لمدة 2 ثانية
    }
});
