# 1. اختيار صورة الأساس (Base Image)
# نستخدم نسخة بايثون رسمية وخفيفة (slim) لتقليل حجم الصورة النهائي
FROM python:3.10-slim

# 2. تثبيت التحديثات وبرنامج Ghostscript
# هذه الخطوة تعمل بصلاحيات Root كاملة أثناء البناء
# نقوم بتحديث قوائم الحزم، تثبيت ghostscript، ثم تنظيف ملفات التخزين المؤقت لتقليل الحجم
RUN apt-get update && apt-get install -y \
    ghostscript \
    && rm -rf /var/lib/apt/lists/*

# 3. إعداد مجلد العمل داخل الحاوية
WORKDIR /app

# 4. نسخ ملف المتطلبات وتثبيت المكتبات
# نقوم بهذه الخطوة أولاً للاستفادة من نظام الكاش في Docker وتسريع عمليات البناء اللاحقة
COPY requirements.txt .
# تثبيت المكتبات بدون تخزين مؤقت للحفاظ على المساحة
RUN pip install --no-cache-dir -r requirements.txt

# 5. نسخ باقي ملفات المشروع
# نسخ كل شيء من مجلد مشروعك الحالي إلى مجلد /app داخل الحاوية
COPY . .

# 6. أمر التشغيل (Start Command)
# هذا هو الأمر الذي سيتم تنفيذه عند تشغيل الحاوية في Render
# نستخدم الإعدادات التي اتفقنا عليها: عامل واحد، وقت انتظار طويل، والربط مع المنفذ الذي يحدده Render
CMD gunicorn -w 1 -k uvicorn.workers.UvicornWorker main:app --timeout 400 --bind 0.0.0.0:$PORT