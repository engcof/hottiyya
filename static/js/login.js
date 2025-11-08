// ✅ دالة عرض رسالة Toast
function showToast(message, type = "info", duration = 3000) {
    const toast = document.createElement("div");
    toast.className = `toast ${type}`;
    toast.textContent = message;
    document.body.appendChild(toast);

    // إظهار الرسالة
    setTimeout(() => toast.classList.add("show"), 100);

    // إخفاؤها بعد المدة المحددة
    setTimeout(() => {
        toast.classList.remove("show");
        setTimeout(() => toast.remove(), 400);
    }, duration);
}

window.onload = function() {
    const passwordField = document.getElementById("password");

    // مسح كلمة المرور عند تحميل الصفحة
    if (passwordField) {
        passwordField.value = "";
        passwordField.setAttribute("autocomplete", "new-password");
    }

    // عند الرجوع أو تحميل الصفحة من الكاش
    window.addEventListener("pageshow", function(event) {
        if (event.persisted) {
            passwordField.value = "";
        }
    });

    // زر إظهار/إخفاء كلمة المرور
    const toggleBtn = document.getElementById("togglePassword");
    if (toggleBtn && passwordField) {
        toggleBtn.addEventListener("click", () => {
            const type = passwordField.getAttribute("type") === "password" ? "text" : "password";
            passwordField.setAttribute("type", type);
            toggleBtn.textContent = type === "password" ? "👁️" : "🙈";
        });
    }

    // ✅ أمثلة على التوست (يمكنك إزالتها لاحقًا)
    // showToast("مرحبًا بك مجددًا!", "success");
    // showToast("حدث خطأ أثناء تسجيل الدخول", "error");
};

