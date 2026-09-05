# استقرار production روی VPS

این پوشه تنظیمات نمونه تحویل را نگه می‌دارد. هیچ فایل حاوی رمز، توکن یا کلید واقعی نباید وارد Git شود.

## معماری ساده و پایدار

- برنامه FastAPI با `systemd` و دقیقاً **یک worker** اجرا می‌شود. افزایش worker بدون قفل توزیع‌شده باعث polling و ارسال تکراری می‌شود.
- پل WhatsApp به‌صورت سرویس جدا و فقط روی `127.0.0.1:8780` اجرا می‌شود.
- Nginx تنها ورودی عمومی و مسئول HTTPS است.
- n8n همراه PostgreSQL در Docker Compose اجرا می‌شود و فقط برای مانیتورینگ، اعلان خرابی، بکاپ و گردش‌کارهای جانبی است. منطق اصلی انتشار در n8n تکرار نمی‌شود.
- داده برنامه، رسانه و نشست WhatsApp در `/var/lib/hayka` نگهداری می‌شوند.

## اطلاعاتی که مالک باید آماده کند

1. VPS اوبونتو 24.04 با حداقل 4 vCPU، رم 8GB، دیسک NVMe حداقل 80GB و IPv4 ثابت.
2. دو نام دامنه یا زیردامنه، مانند `panel.example.com` و `automation.example.com`، برای HTTPS معتبر.
3. کلید جدید OpenAI، توکن‌های نهایی ربات‌ها، مقصدهای نهایی و رمز مدیر.
4. نسخه مشخص و پشتیبانی‌شده n8n برای `N8N_VERSION`؛ از `latest` استفاده نشود.

## نصب پایه

روی سرور بسته‌های Python 3.12، Node.js 20 یا جدیدتر، FFmpeg، SQLite، Nginx، Docker Engine و Docker Compose نصب شوند. یک کاربر سیستمی بدون shell به نام `hayka` بسازید و مخزن خصوصی را در `/opt/hayka/current` قرار دهید.

```bash
python3.12 -m venv /opt/hayka/venv
/opt/hayka/venv/bin/pip install --upgrade pip
/opt/hayka/venv/bin/pip install /opt/hayka/current
npm ci --prefix /opt/hayka/current/services/whatsapp-bridge
install -d -o hayka -g hayka -m 0700 /var/lib/hayka /etc/hayka
```

از `app.env.example` یک نسخه در `/etc/hayka/app.env` بسازید، همه مقادیر خالی را با مقادیر جدید مالک پر کنید و دسترسی فایل را `0600` قرار دهید. سپس سرویس‌ها را نصب کنید:

```bash
cp deploy/hayka-app.service deploy/hayka-whatsapp.service /etc/systemd/system/
systemctl daemon-reload
systemctl enable --now hayka-whatsapp hayka-app
```

پس از اولین اجرای WhatsApp، QR موجود در `/var/lib/hayka/whatsapp-runtime/qr.png` فقط توسط مالک اسکن شود. نشست این پوشه محرمانه است.

## HTTPS و n8n

دامنه‌های نمونه در `nginx.conf.example` را جایگزین و برای هر دو دامنه گواهی معتبر بگیرید. چون کوکی production امن است و ضبط صدا نیز Secure Context می‌خواهد، اجرای عمومی بدون HTTPS قابل تحویل نیست.

برای n8n، فایل نمونه را خارج از مخزن کپی و رمزهای قوی تولید کنید:

```bash
cp deploy/n8n.env.example /etc/hayka/n8n.env
chmod 0600 /etc/hayka/n8n.env
docker compose --env-file /etc/hayka/n8n.env -f deploy/compose.n8n.yml up -d
```

`N8N_ENCRYPTION_KEY` بعد از ورود credentialها نباید تغییر کند، مگر طبق فرایند رسمی rotation و همراه بکاپ. بعد از راه‌اندازی، security audit داخلی n8n نیز اجرا شود.

## بکاپ و آزمون تحویل

`backup.sh` با SQLite Online Backup از دیتابیس و سپس از رسانه‌ها و نشست WhatsApp نسخه می‌گیرد. ابتدا آن را دستی اجرا و بازیابی را آزمایش کنید؛ سپس اجرای روزانه‌اش را در n8n یا systemd timer قرار دهید. بکاپ n8n/PostgreSQL باید جداگانه با `pg_dump` تنظیم شود.

```bash
install -m 0700 deploy/backup.sh /usr/local/sbin/hayka-backup
/usr/local/sbin/hayka-backup
```

در پایان این موارد باید همگی موفق باشند:

```bash
curl --fail https://panel.example.com/health
curl --fail http://127.0.0.1:8780/health
systemctl --no-pager --full status hayka-app hayka-whatsapp
docker compose --env-file /etc/hayka/n8n.env -f deploy/compose.n8n.yml ps
```

سپس یک انتشار واقعی به هر چهار پلتفرم، دو سؤال خصوصی در هر ربات فعال و یک آزمون backup/restore انجام شود.
