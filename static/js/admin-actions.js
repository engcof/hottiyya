/**
 * إدارة لوحة التحكم الإدارية - موقع الحوطية
 * مخصص للعمليات والإجراءات الخاصة بالمسؤولين فقط
 */

// 1. دالة تصدير شجرة العائلة بصيغة Excel/CSV
function exportTree() {
    const code = document.getElementById('treeCodeInput').value.trim();
    if (!code) {
        alert("يرجى إدخال كود الشخص أولاً!");
        return;
    }
    window.location.href = `/data/export/family-tree/${code}`;
}

// 💡 يمكنك إضافة أي دالة جديدة هنا مستقبلاً (مثل: تحديث الإحصائيات، جلب بيانات بالـ AJAX، إلخ...)