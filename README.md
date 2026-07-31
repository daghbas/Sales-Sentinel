# Sales Sentinel | حارس المبيعات

نظام Flask ثنائي اللغة لتحليل المبيعات اليومية والتنبؤ المبكر بالانخفاض. النسخة الحالية **Pilot** مبنية على بيانات Redsea السعودية الحقيقية: 2,700 صفًا خلال يوليو–أكتوبر 2023.

## تشغيل Windows
```bat
py -3.12 -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
set SECRET_KEY=change-this
python run.py
```

الحسابات في `docs/demo_accounts.md`. قاعدة البيانات: `instance/sales_sentinel.db`.

## القيود
- معرض واحد وفترة قصيرة؛ 90 يومًا معطل بدل عرض نتيجة غير موثوقة.
- لا يتوفر مخزون أو قاموس رسمي لرموز قنوات البيع.
- نشر Vercel للعرض؛ تغييرات SQLite مؤقتة في بيئة Serverless.

## بنية النشر
يحتوي `api/index.py` على حزمة مصدر مضغوطة قابلة للاستخراج عند تشغيل Vercel. النسخة الكاملة المفكوكة، والبيانات الخام، وقاعدة SQLite، والنموذج، والتقارير متاحة في حزمة التسليم ZIP.