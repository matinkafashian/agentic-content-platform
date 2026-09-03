# WhatsApp bridge

این سرویس محلی، انتشار پایتون را به نشست WhatsApp Web متصل می‌کند. استفاده از آن
رسمی نیست و ممکن است با تغییرات WhatsApp Web نیازمند به‌روزرسانی شود.

این bridge فقط روی `127.0.0.1` گوش می‌دهد و endpointهای عملیاتی با یک Bearer
token تصادفی محافظت می‌شوند. کلید در اولین اجرا داخل پوشه محلی runtime ساخته
می‌شود. زنجیره Puppeteer نسخه ۱.۳۴.۷ در زمان نگارش یک هشدار
`npm audit` مرتبط با استخراج آرشیو Chromium دارد؛ سرویس یا پوشه session را در
شبکه عمومی قرار ندهید و به‌روزرسانی upstream را پیش از استقرار نهایی بازبینی کنید.

## راه‌اندازی

بار اول داخل پوشه سرویس نصب کنید و سپس از ریشه پروژه اجرا کنید:

```powershell
npm install
npm --prefix services/whatsapp-bridge start
```

در اولین اجرا، QR در `.whatsapp-runtime/qr.png` ساخته می‌شود. آن را از بخش
Linked devices برنامه واتساپ اسکن کنید. نشست در `.whatsapp-session/` نگهداری
می‌شود و کلید اتصال در `.whatsapp-runtime/bridge-token` قرار می‌گیرد. هیچ‌کدام
نباید در Git یا نسخه پشتیبان عمومی قرار بگیرند.

پس از اتصال، `GET /destinations` با هدر Bearer فهرست شناسه گروه‌ها و کانال‌های
قابل مشاهده را برمی‌گرداند. شناسه انتخابی در `WHATSAPP_DEFAULT_DESTINATION`
قرار می‌گیرد.
