
#!/usr/bin/env bash
# إنهاء السكربت عند حدوث أي خطأ
set -o errexit

# 1. تحديث المستودعات وتثبيت الأدوات اللازمة
# أضفنا postgresql-client لضمان نجاح عملية الاستيراد (Import)
apt-get update && apt-get install -y ghostscript postgresql-client

# 2. تحديث pip وتثبيت مكتبات بايثون
pip install --upgrade pip
pip install -r requirements.txt