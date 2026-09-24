# BotHost Web

موقع ويب عربي لإدارة بوتات Telegram من لوحة تحكم واحدة.

## تشغيل محلي
```bash
python -m venv .venv
# Linux/macOS:
source .venv/bin/activate
# Windows:
# .venv\Scripts\activate
pip install -r requirements.txt
```

أنشئ `.env` من `.env.example` ثم:
```bash
python app.py
```

## متغيرات مهمة
- SECRET_KEY: مفتاح Flask عشوائي طويل.
- ADMIN_PASSWORD: كلمة مرور لوحة الإدارة.
- FERNET_KEY: مفتاح تشفير التوكنات. أنشئه:
  `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`
- PORT: منفذ الخدمة.

## نشر مجاني
يمكن نشر واجهة Flask على مزود يدعم Python، لكن الخطة المجانية قد توقف الخدمة عند الخمول أو تفرض حدودًا. لذلك لا يوجد ضمان 24/7 على الخطة المجانية.

## مهم جدًا
هذا مشروع Single-Admin. رفع كود Python يعني تنفيذ كود على الخادم، لذلك لا تفتحه للعامة كمضيف متعدد المستخدمين بدون sandbox/containers وصلاحيات وحدود موارد.
