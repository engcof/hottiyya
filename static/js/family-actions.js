/**
 * سكربت إدارة أعضاء الشجرة - موقع الحوطية - النسخة المؤمنة والمحسنة (إضافة وتعديل)
 */
document.addEventListener('DOMContentLoaded', () => {
    // ==========================================
    // 1️⃣ أولاً: كود التحقق التلقائي من الكود (خاص بالإضافة)
    // ==========================================
    const codeInput = document.getElementById('memberCode');
    const statusIcon = document.getElementById('codeStatusIcon');
    const feedback = document.getElementById('codeFeedback');
    
    let abortController = null;

    if (codeInput) {
        codeInput.addEventListener('input', async function(e) {
            let val = e.target.value.trim().toUpperCase();
            e.target.value = val;

            if (abortController) abortController.abort();
            abortController = new AbortController();
            const { signal } = abortController;

            if (val.length === 1 && /^[A-Z]$/.test(val)) {
                try {
                    const res = await fetch(`/family/get-next-code?prefix=${val}`, { signal });
                    const data = await res.json();
                    if (data.next_code) {
                        e.target.value = data.next_code;
                        e.target.setSelectionRange(1, data.next_code.length);
                        validateCode(data.next_code);
                    }
                } catch (err) { 
                    if (err.name !== 'AbortError') console.error("Error fetching next code by letter:", err); 
                }
            }
            else if (val.length === 6 && val.includes('-')) {
                try {
                    const response = await fetch(`/family/get-next-code?prefix=${val}`, { signal });
                    const data = await response.json();
                    if (data.next_code) {
                        e.target.value = data.next_code;
                        validateCode(data.next_code); 
                    }
                } catch (error) {
                    if (error.name !== 'AbortError') console.error("خطأ في جلب الكود بالبادئة:", error);
                }
            }
        });

        codeInput.addEventListener('blur', function() {
            validateCode(this.value);
        });
    }

    async function validateCode(code) {
        if (code.length < 3 || !statusIcon || !feedback || !codeInput) return;

        try {
            const response = await fetch(`/family/check-code-availability?code=${encodeURIComponent(code)}`);
            const data = await response.json();

            if (data.available) {
                statusIcon.innerHTML = '✅';
                feedback.innerText = 'هذا الكود متاح للاستخدام';
                feedback.style.color = '#10b981';
                codeInput.style.borderColor = '#10b981';
            } else {
                statusIcon.innerHTML = '❌';
                feedback.innerText = 'عذراً، هذا الكود محجوز مسبقاً!';
                feedback.style.color = '#ef4444';
                codeInput.style.borderColor = '#ef4444';
            }
        } catch (err) {
            console.error("خطأ في التحقق من إتاحة الكود:", err);
        }
    }

    // ==========================================
    // 2️⃣ ثانياً: كود معاينة الصورة عند الإضافة الجديدة
    // ==========================================
    const imageInput = document.getElementById('memberImageInput');
    const imageDropZone = document.getElementById('imageDropZone');
    const defaultPrompt = document.getElementById('defaultUploadPrompt');
    const previewContainer = document.getElementById('imagePreviewContainer');
    const imagePreview = document.getElementById('memberImagePreview');
    const removeImageBtn = document.getElementById('removeMemberImageBtn');

    if (imageInput && imagePreview && previewContainer && defaultPrompt) {
        imageInput.addEventListener('change', function() {
            const file = this.files[0];
            if (file) {
                if (!file.type.startsWith('image/')) {
                    alert('من فضلك اختر ملف صورة صالح فقط.');
                    this.value = '';
                    return;
                }

                const reader = new FileReader();
                reader.onload = function(e) {
                    imagePreview.src = e.target.result;
                    defaultPrompt.style.display = 'none';
                    previewContainer.style.display = 'block';
                    imageInput.style.zIndex = '1';
                };
                reader.readAsDataURL(file);
            }
        });

        if (removeImageBtn) {
            removeImageBtn.addEventListener('click', function(e) {
                e.preventDefault();
                e.stopPropagation();
                imageInput.value = '';
                imagePreview.src = '';
                previewContainer.style.display = 'none';
                defaultPrompt.style.display = 'block';
                imageInput.style.zIndex = '5';
            });
        }

        ['dragenter', 'dragover'].forEach(eventName => {
            imageInput.addEventListener(eventName, () => {
                imageDropZone.style.borderColor = '#3b82f6';
                imageDropZone.style.background = '#eff6ff';
            }, false);
        });

        ['dragleave', 'drop'].forEach(eventName => {
            imageInput.addEventListener(eventName, () => {
                imageDropZone.style.borderColor = '#cbd5e0';
                imageDropZone.style.background = '#f8fafc';
            }, false);
        });
    }

    // ==========================================
    // 3️⃣ ثالثاً: كود معاينة الصورة عند تعديل العضو (النظام الجديد المتكامل)
    // ==========================================
    const editImageInput = document.getElementById('editImageInput');
    const editImageDropZone = document.getElementById('editImageDropZone');
    const currentImageWrapper = document.getElementById('currentImageWrapper');
    const editDefaultPrompt = document.getElementById('editDefaultPrompt');
    const editImagePreviewContainer = document.getElementById('editImagePreviewContainer');
    const editImagePreview = document.getElementById('editImagePreview');
    const cancelEditImageBtn = document.getElementById('cancelEditImageBtn');

    if (editImageInput && editImagePreview && editImagePreviewContainer) {
        editImageInput.addEventListener('change', function() {
            const file = this.files[0];
            if (file) {
                if (!file.type.startsWith('image/')) {
                    alert('من فضلك اختر ملف صورة صالح فقط.');
                    this.value = '';
                    return;
                }

                const reader = new FileReader();
                reader.onload = function(e) {
                    // إخفاء الصورة السحابية القديمة مؤقتاً لعرض التعديل الجديد مقدماً
                    if (currentImageWrapper) currentImageWrapper.style.display = 'none';
                    if (editDefaultPrompt) editDefaultPrompt.style.display = 'none';
                    
                    editImagePreview.src = e.target.result;
                    editImagePreviewContainer.style.display = 'block';
                    editImageInput.style.zIndex = '1';
                };
                reader.readAsDataURL(file);
            }
        });

        if (cancelEditImageBtn) {
            cancelEditImageBtn.addEventListener('click', function(e) {
                e.preventDefault();
                e.stopPropagation();
                
                editImageInput.value = '';
                editImagePreview.src = '';
                editImagePreviewContainer.style.display = 'none';
                
                // التراجع الذكي: إعادة الصورة السحابية الخضراء إن وجدت، أو استعادة الواجهة الفارغة
                if (currentImageWrapper && currentImageWrapper.querySelector('img')) {
                    currentImageWrapper.style.display = 'block';
                    if (editDefaultPrompt) editDefaultPrompt.style.display = 'none';
                } else {
                    if (currentImageWrapper) currentImageWrapper.style.display = 'none';
                    if (editDefaultPrompt) editDefaultPrompt.style.display = 'block';
                }
                
                editImageInput.style.zIndex = '5';
            });
        }

        ['dragenter', 'dragover'].forEach(eventName => {
            editImageInput.addEventListener(eventName, () => {
                editImageDropZone.style.borderColor = '#3b82f6';
                editImageDropZone.style.background = '#eff6ff';
            }, false);
        });

        ['dragleave', 'drop'].forEach(eventName => {
            editImageInput.addEventListener(eventName, () => {
                editImageDropZone.style.borderColor = '#cbd5e1';
                editImageDropZone.style.background = '#f8fafc';
            }, false);
        });
    }
});