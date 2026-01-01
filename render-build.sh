#!/usr/bin/env bash
# إنهاء السكربت عند حدوث أي خطأ
set -o errexit

# 1. تثبيت Ghostscript (محرك الضغط)
# ملاحظة: في بيئة Render قد لا تحتاج لـ sudo
apt-get update && apt-get install -y ghostscript

# 2. تحديث pip وتثبيت مكتبات بايثون
pip install --upgrade pip
pip install -r requirements.txt