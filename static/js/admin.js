document.addEventListener("DOMContentLoaded", function() {
    const usersTable = document.getElementById("users-table").querySelector("tbody");

    // ------------------- جلب المستخدمين عند تحميل الصفحة -------------------
    async function loadUsers() {
        const res = await fetch("/admin/users/json");  // تأكد أن لديك endpoint يعيد كل المستخدمين بصيغة JSON
        const data = await res.json();

        usersTable.innerHTML = ""; // مسح أي بيانات موجودة مسبقًا

        data.forEach(user => {
            const row = document.createElement("tr");
            row.dataset.userId = user.id;
            row.innerHTML = `
                <td>${user.username}</td>
                <td>${user.email}</td>
                <td>
                    ${user.permissions.map(p => `<input type="checkbox" class="perm-checkbox" data-perm-name="${p}"> ${p}<br>`).join('')}
                </td>
                <td><button class="delete-user-btn">حذف</button></td>
            `;
            usersTable.appendChild(row);
        });
    }

    loadUsers(); // استدعاء الدالة عند تحميل الصفحة

    // ------------------- إضافة مستخدم جديد -------------------
    const addUserForm = document.getElementById("add-user-form");

    addUserForm.addEventListener("submit", async function(e) {
        e.preventDefault();
        const formData = new FormData(this);
        const res = await fetch("/admin/users/add-json", { method: "POST", body: formData });
        const data = await res.json();

        if (data.success) {
            alert("تم إضافة المستخدم: " + data.username);
            loadUsers();  // إعادة تحميل المستخدمين بعد الإضافة
        } else {
            alert(data.message);
        }
    });

    // ------------------- إضافة صلاحية جديدة -------------------
    const addPermForm = document.getElementById("add-permission-form");

    addPermForm.addEventListener("submit", async function(e) {
        e.preventDefault();
        const formData = new FormData(this);
        const res = await fetch("/admin/permissions/add-json", { method: "POST", body: formData });
        const data = await res.json();

        if (data.success) {
            alert("تم إضافة الصلاحية: " + data.name);
            loadUsers(); // إعادة تحميل جدول المستخدمين لتحديث الصلاحيات
        } else {
            alert(data.message);
        }
    });

    // ------------------- حذف مستخدم -------------------
    usersTable.addEventListener("click", async function(e) {
        if (e.target.classList.contains("delete-user-btn")) {
            const tr = e.target.closest("tr");
            const userId = tr.dataset.userId;

            if (!confirm("هل تريد حذف المستخدم؟")) return;

            const res = await fetch(`/admin/users/delete-json/${userId}`, { method: "DELETE" });
            const data = await res.json();

            if (data.success) {
                tr.remove();
                alert("تم حذف المستخدم.");
            } else {
                alert(data.message);
            }
        }
    });

});

// admin.js

document.getElementById('add-user-form').addEventListener('submit', function(event) {
    event.preventDefault();
    
    const formData = new FormData(event.target);
    
    // إرسال البيانات عبر AJAX (Fetch API) لإضافة المستخدم الجديد
    fetch('/api/add_user', {
        method: 'POST',
        body: formData
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            // تحديث الجدول بشكل ديناميكي بإضافة المستخدم الجديد
            const tableBody = document.querySelector('#users-table tbody');
            const newRow = document.createElement('tr');
            newRow.innerHTML = `
                <td>${data.user.username}</td>
                <td>${data.user.email}</td>
                <td>${data.user.permissions.join('<br>')}</td>
                <td><button class="btn btn-danger" onclick="deleteUser(${data.user.id})">حذف</button></td>
            `;
            tableBody.appendChild(newRow);
        }
    })
    .catch(error => console.error('Error:', error));
});


function deleteUser(userId) {
    if (confirm('هل أنت متأكد من حذف هذا المستخدم؟')) {
        // إرسال طلب حذف المستخدم
        fetch(`/api/delete_user/${userId}`, {
            method: 'DELETE'
        })
        .then(response => response.json())
        .then(data => {
            if (data.success) {
                // حذف الصف من الجدول بعد النجاح
                const row = document.querySelector(`#users-table tr[data-user-id="${userId}"]`);
                row.remove();
            } else {
                alert('حدث خطأ أثناء الحذف.');
            }
        })
        .catch(error => console.error('Error:', error));
    }
}
