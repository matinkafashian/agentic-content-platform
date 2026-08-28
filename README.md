# سامانه هوشمند مدیریت محتوا — فاز یک

این مخزن فاز پایه سامانه‌ای است که در ادامه، آماده‌سازی تصویر و کپشن با OpenAI، انتشار کنترل‌شده در کانال‌ها و پاسخ‌گویی خصوصی مشتری را انجام خواهد داد. فاز یک عمداً کوچک و قابل‌اعتماد نگه داشته شده و یک پنل RTL امن برای مدیریت کاتالوگ محصول ارائه می‌کند.

## قابلیت‌های آماده در فاز یک

- ورود و خروج مدیر با رمز Argon2 و Session امضاشده؛
- محافظت CSRF برای Login، Logout و فرم‌های تغییردهنده؛
- داشبورد responsive با شاخص واقعی کل، فعال و دارای تصویر؛
- ایجاد، مشاهده و ویرایش محصول؛
- قیمت، موجودی، ارسال، ویژگی‌ها و هشتگ‌های ساخت‌یافته؛
- بررسی Extension، MIME، Signature، حجم و تعداد پیکسل تصویر؛
- ذخیره عکس با نام opaque زیر پوشه اختصاصی محصول؛
- Migration برگشت‌پذیر Alembic؛
- حذف خودکار محصول ناقص اگر ذخیره فایل شکست بخورد؛
- حذف مقادیر شبیه token، API key و password از Logها.

در این فاز هنوز هیچ تماس OpenAI، تولید یا ادیت تصویر، Voice، زمان‌بندی، انتشار تلگرام/بله/روبیکا/واتساپ یا Support Bot وجود ندارد. نبودن این گزینه‌ها در پنل عمدی است؛ کنترل نمایشی و غیرواقعی ارائه نمی‌شود.

## پیش‌نیاز

- Python 3.12 یا جدیدتر؛
- دسترسی نوشتن برای پوشه دیتابیس و `uploads/`؛
- مرورگر جدید با JavaScript فعال.

## راه‌اندازی در Windows PowerShell

از ریشه پروژه اجرا کنید:

```powershell
py -3.12 -m venv .venv
& .\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
Copy-Item .env.example .env
```

برای ساخت Secret تصادفی Session:

```powershell
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

خروجی را در `SECRET_KEY` فایل `.env` قرار دهید. برای ساخت Hash رمز مدیر، دستور زیر رمز را تعاملی و بدون نمایش روی صفحه دریافت می‌کند؛ بنابراین خود رمز در History شل ذخیره نمی‌شود:

```powershell
python -c "from getpass import getpass; from app.core.security import hash_password; print(hash_password(getpass('Admin password: ')))"
```

خروجی Argon2 را بدون کوتاه‌کردن در `ADMIN_PASSWORD_HASH` قرار دهید. نمونه نهایی `.env` باید متغیرهای زیر را مقداردهی کند:

```dotenv
APP_NAME=Agentic Content Platform
APP_TIMEZONE=Asia/Tehran
DATABASE_URL=sqlite:///./data/app.db
UPLOAD_DIR=uploads
SECRET_KEY=<generated-value>
ADMIN_USERNAME=admin
ADMIN_PASSWORD_HASH=<argon2-hash>
DEBUG=false
```

مقادیر واقعی `.env` را commit، در پیام‌رسان ارسال یا در Screenshot منتشر نکنید.

## دیتابیس و اجرای برنامه

Schema را ایجاد یا به آخرین نسخه ارتقا دهید:

```powershell
python -m alembic upgrade head
```

برنامه را اجرا کنید:

```powershell
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

- Health check: `http://127.0.0.1:8000/health`
- ورود مدیر: `http://127.0.0.1:8000/admin/login`

در محیط production، `DEBUG=false` الزامی است تا Cookie نشست فقط روی HTTPS ارسال شود. برنامه باید پشت reverse proxy دارای TLS اجرا شود.

## اجرای تست‌ها

تست متمرکز یک بخش:

```powershell
python -m pytest tests/admin/test_product_routes.py -v
```

Gate کامل فاز یک:

```powershell
python -m ruff check app tests
python -m pytest -v --cov=app --cov-report=term-missing
python -m alembic downgrade base
python -m alembic upgrade head
git diff --check
```

دستور `downgrade base` همه جدول‌های این فاز را حذف می‌کند و فقط باید روی دیتابیس توسعه یا نسخه‌ای با Backup معتبر اجرا شود.

## تست دستی تحویل فاز یک

پس از پاس‌شدن Gate خودکار، کاربر پروژه می‌تواند این سناریو را جداگانه بررسی کند:

1. با نام کاربری یا رمز اشتباه وارد شوید و پیام عمومی و بدون افشای جزئیات را ببینید.
2. با اطلاعات صحیح وارد شوید و شاخص‌های داشبورد را بررسی کنید.
3. یک محصول با عکس واقعی PNG، JPEG یا WebP ایجاد کنید.
4. قیمت فارسی، تصویر و هشتگ‌ها را در صفحه جزئیات ببینید.
5. محصول را بدون انتخاب عکس جدید ویرایش کنید و باقی‌ماندن عکس قبلی را ببینید.
6. پنل را در عرض دسکتاپ و موبایل بررسی کنید؛ اسکرول افقی نباید وجود داشته باشد.
7. Logout را اجرا کنید و مطمئن شوید `/admin` دوباره به Login هدایت می‌شود.

## فایل‌های Upload و Backup

فقط زیرشاخه `uploads/products/` به‌صورت عمومی mount می‌شود. نام اصلی فایل کاربر در مسیر سرور استفاده نمی‌شود و مسیر absolute در HTML نمایش داده نمی‌شود. کاربر سرویس باید فقط روی `UPLOAD_DIR` و پوشه دیتابیس دسترسی لازم داشته باشد.

Backup معتبر شامل هر دو مورد زیر و مربوط به یک لحظه زمانی واحد است:

- فایل SQLite در `data/app.db`؛
- کل پوشه `uploads/`.

پیش از کپی ساده، سرویس را متوقف کنید؛ در استقرار حرفه‌ای از snapshot سازگار دیتابیس و فایل استفاده شود. حذف یکی از این دو بخش باعث رکورد بدون عکس یا فایل بدون رکورد می‌شود.

SQLite برای MVP تک‌سروری و حجم اولیه مناسب است، اما برای چند worker، نوشتن هم‌زمان زیاد و گزارش‌گیری سنگین انتخاب نهایی نیست. مسیر ارتقا، افزودن PostgreSQL driver، تغییر `DATABASE_URL` و اجرای همان Migrationهای Alembic روی PostgreSQL است؛ منطق Catalog به دیتابیس خاص وابسته نشده است.

## ورودی‌های لازم برای فازهای بعد

هیچ‌کدام از موارد زیر برای اجرای فاز یک لازم نیست. پیش از فاز مربوط، جداگانه و از مسیر امن تحویل شوند:

- OpenAI API key، سقف هزینه و مدل‌های مجاز برای متن/تصویر/Voice؛
- فایل لوگو، رنگ برند، فونت مجاز و نمونه لحن کپشن؛
- Telegram Bot token، شناسه کانال تست و دسترسی Admin ربات؛
- Bale Bot token، شناسه کانال تست و دسترسی لازم؛
- حساب و شناسه کانال Rubika به‌همراه روش رسمی قابل‌تأیید در زمان اجرا؛
- FAQ، قوانین فروش، ارسال، مرجوعی و مسیر ارجاع به انسان برای Support Bot؛
- سرور ۲۴ساعته، دامنه، TLS، Backup و مانیتورینگ؛
- WhatsApp فقط در فاز آخر و به‌صورت best-effort، با پذیرش ریسک روش غیررسمی گروه‌ها.

## ساختار فاز یک

- `app/core`: تنظیمات، دیتابیس، امنیت، logging و templateهای مشترک؛
- `app/catalog`: مدل، schema، repository، service و routeهای محصول؛
- `app/media`: اعتبارسنجی و ذخیره امن عکس؛
- `app/admin`: ورود، guard و داشبورد؛
- `migrations`: تاریخچه Schema؛
- `tests`: تست‌های واحد و integration.

معماری فعلی Modular Monolith است. Microservice، Celery، Redis، LangChain و React تا زمانی که نیاز واقعی اثبات نشود وارد پروژه نمی‌شوند.
