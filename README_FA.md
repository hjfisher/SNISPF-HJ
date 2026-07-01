# SNISPF-HJ

### ابزار خط‌فرمان دور زدن DPI روی همه پلتفرم‌ها — با pool خودترمیم‌شونده و کشف خودکار IP

```
  _____ ____   ____ _____ ____  _____        __ __  ____ 
 / ___/|    \ |    / ___/|    \|     |      |  |  ||    |
(   \_ |  _  | |  (   \_ |  o  )   __|_____ |  |  ||__  |
 \__  ||  |  | |  |\__  ||   _/|  |_ |     ||  _  |__|  |
 /  \ ||  |  | |  |/  \ ||  |  |   _]|_____||  |  /  |  |
 \    ||  |  | |  |\    ||  |  |  |         |  |  \  `  |
  \___||__|__||____|\___||__|  |__|         |__|__|\____j
```

**[EN README](README.md)**

**SNISPF-HJ** یک فورک از [SNISPF](https://github.com/Rainman69/SNISPF) ساختهٔ
[@Rainman69](https://github.com/Rainman69) است، با اضافه شدن یک **pool
خودترمیم‌شونده چند-IP / چند-SNI** و **کشف خودکار IP از رنج‌های رسمی
Cloudflare** — ایده‌هایی برگرفته از کارهای
[@patterniha](https://github.com/patterniha)،
[@hjfisher](https://github.com/hjfisher)، و
[@bia-pain-bache](https://github.com/bia-pain-bache).

روی **Windows، macOS، Linux و Android (Termux)** کار می‌کند و برای روش
پیش‌فرض نیازی به root ندارد.

پیشنهاد یا سؤال؟ → **[SNISPF/discussions](https://github.com/Rainman69/SNISPF/discussions)**

‎**⭐️ فراموش نشه ⭐️**

---

## فهرست

- [چه چیزی جدید است؟](#چه-چیزی-جدید-است)
- [چطور کار می‌کند؟](#چطور-کار-میکند)
- [پیش‌نیازها](#پیشنیازها)
- [نصب](#نصب)
- [ساخت فایل اجرایی (exe)](#ساخت-فایل-اجرایی-exe)
- [شروع سریع](#شروع-سریع)
- [پیکربندی](#پیکربندی)
- [تنظیمات Pool](#تنظیمات-pool)
- [امتیازدهی: سلامت یک جفت چطور سنجیده می‌شود؟](#امتیازدهی-سلامت-یک-جفت-چطور-سنجیده-میشود)
- [حذف، قرنطینه و بازیافت IP](#حذف-قرنطینه-و-بازیافت-ip)
- [کشف خودکار IP](#کشف-خودکار-ip)
- [کشف خودکار SNI](#کشف-خودکار-sni)
- [حذف، قرنطینه و بازیافت SNI](#حذف-قرنطینه-و-بازیافت-sni)
- [شکل‌دهی ترافیک (Traffic Shaping)](#شکلدهی-ترافیک-traffic-shaping)
- [پرچم‌های CLI](#پرچمهای-cli)
- [روش‌های دور زدن](#روشهای-دور-زدن)
- [استراتژی‌های قطعه‌بندی](#استراتژیهای-قطعهبندی)
- [بررسی‌گر دامنه](#بررسیگر-دامنه)
- [پشتیبانی از پلتفرم‌ها](#پشتیبانی-از-پلتفرمها)
- [رفع اشکال](#رفع-اشکال)
- [ساختار پروژه](#ساختار-پروژه)
- [تشکر و منابع](#تشکر-و-منابع)
- [لایسنس](#لایسنس)

---

## چه چیزی جدید است؟

| قابلیت | SNISPF اصلی | SNISPF-HJ |
|---|---|---|
| upstream | یک IP + یک SNI | چند IP × چند SNI |
| بررسی سلامت | ندارد | TLS handshake واقعی (نه فقط TCP) |
| انتخاب جفت | ثابت | وزن‌دار تصادفی، امتیاز = loss + latency |
| ردیابی loss | — | میانگین متحرک نمایی (خودترمیم‌شونده) |
| جایگزینی بدون قطعی | ندارد | draining با timeout قابل تنظیم |
| بستن اجباری drain | ندارد | بعد از `DRAIN_TIMEOUT` ثانیه کانکشن‌ها بسته می‌شوند |
| حذف IP های ضعیف | ندارد | ضعیف‌ترین IP ها دوره‌ای قرنطینه می‌شوند |
| بازیافت IP | ندارد | IP های قرنطینه دوباره تست و بازگردانده می‌شوند |
| دامنهٔ حذف/بازیافت | — | انتخاب فقط static، فقط dynamic، یا هر دو |
| کشف خودکار IP | ندارد | اسکن رنج‌های رسمی Cloudflare در پس‌زمینه |
| کشف خودکار SNI | ندارد | نمونه‌گیری از Tranco/Umbrella/Majestic + لیست seed، تأیید میزبانی Cloudflare + TLS |
| حذف/بازیافت SNI | ندارد | مشابه حذف/بازیافت IP، اما روی محور SNI |
| شکل‌دهی ترافیک | ندارد | تکه‌بندی/تنظیم زمان‌بندی اختیاری بعد از handshake برای پنهان کردن الگوی ترافیک پروکسی |
| دستور اجرا | `snispf` | `snispf` **و** `snispf-hj` |
| ماژول‌های جدید | — | `pool.py`، `ip_discovery.py`، `sni_discovery.py`، `shaping.py` |

تمام قابلیت‌های اصلی کاملاً حفظ شده‌اند.

---

## چطور کار می‌کند؟

وقتی یک سایت HTTPS باز می‌کنی، دستگاهت یک **TLS ClientHello** می‌فرستد که
نام سایت به‌صورت متن خام داخل آن است — این **SNI** نام دارد. DPI همین نام را
می‌بیند و تصمیم می‌گیرد.

SNISPF-HJ بین برنامه‌ات و اینترنت می‌نشیند و آن سلام را یا
**قطعه‌قطعه می‌کند** یا **یک سلام جعلی** قبل از آن می‌فرستد.

```
┌──────────┐     ┌──────────────────┐     ┌──────────┐     ┌──────────────┐
│  برنامه  ├────>│   SNISPF-HJ      ├────>│  DPI /   ├────>│ سرور واقعی   │
│          │     │  (پروکسی محلی)   │     │ فایروال  │     │ (Cloudflare) │
│          │     │                  │     │          │     │              │
│          │     │ ① pool بهترین    │     │ SNI جعلی │     │              │
│          │     │   (IP,SNI) انتخاب│     │ یا تکه‌تکه│     │              │
│          │     │ ② discovery IPهای│     │          │     │              │
│          │     │   جدید اضافه می‌کند│    │          │     │              │
└──────────┘     └──────────────────┘     └──────────┘     └──────────────┘
```

### Pool اتصال

در هنگام راه‌اندازی، یک نمونهٔ تصادفی از جفت‌های `(IP، SNI)` با یک **TLS
handshake واقعی** بررسی می‌شود — نه صرفاً یک TCP connect، چون ممکن است
سروری اتصال TCP را قبول کند ولی لایهٔ TLS را رد کند یا قطع کند؛ پس تنها
handshake واقعی تست معتبری است. جفت‌هایی که پاسخ خوب می‌دهند وارد **pool
فعال** می‌شوند. یک thread پس‌زمینه هر ~۳۰ ثانیه pool را دوباره بررسی و
جفت‌های ضعیف را جایگزین می‌کند. هر اتصال جدید با **انتخاب وزن‌دار تصادفی**
یک جفت دریافت می‌کند — امتیاز کمتر یعنی احتمال انتخاب بیشتر.

### ردیابی خودترمیم‌شوندهٔ Loss

نرخ از دست دادن داده به‌صورت **میانگین متحرک نمایی (EMA)** ردیابی می‌شود،
نه یک شمارندهٔ تمام‌عمر. یعنی جفتی که مدتی عملکرد بدی داشته و بعد بهبود
پیدا کرده، با رسیدن نتایج خوب جدید، امتیازش به‌تدریج بهتر می‌شود — شکست‌های
قدیمی محو می‌شوند به‌جای اینکه برای همیشه روی جفت سنگینی کنند. برای فرمول
دقیق به [امتیازدهی](#امتیازدهی-سلامت-یک-جفت-چطور-سنجیده-میشود) مراجعه کن.

### Draining با Timeout

وقتی یک جفت ضعیف می‌شود وارد حالت **draining** می‌شود: اتصال جدیدی به آن
داده نمی‌شود ولی اتصال‌های قبلی ادامه می‌دهند. بعد از `DRAIN_TIMEOUT` ثانیه
(پیش‌فرض: ۳۰) اتصال‌های باقی‌مانده بسته می‌شوند. سقف `MAX_DRAINING` مانع
بی‌کنترل شدن لیست draining می‌شود.

### حذف IP → قرنطینه → بازیافت

IP های ضعیف برای همیشه حذف نمی‌شوند — به یک لیست **قرنطینه** منتقل و
دوره‌ای دوباره تست می‌شوند. اگر IP واقعاً بهبود یافته باشد، با یک تاریخچهٔ
کاملاً تازه دوباره به pool خوش‌آمد گفته می‌شود. جزئیات کامل در بخش
[حذف، قرنطینه و بازیافت IP](#حذف-قرنطینه-و-بازیافت-ip).

### کشف خودکار IP

یک thread دوم مستقل، از رنج‌های رسمی Cloudflare به‌صورت تصادفی IP نمونه
می‌گیرد، آن‌ها را با یک **TLS handshake واقعی** بررسی می‌کند، و IPهای سالم
را به pool تزریق می‌کند — همزمان با سرویس‌دهی به اتصال‌ها.

```
۱۵ CIDR رسمی Cloudflare  →  نمونه‌گیری ۱۰۰ IP تصادفی  →  TLS handshake موازی
        ↓ پذیرفته‌شده (موفقیت ≥ ۵۰٪)
  تزریق به عنوان جفت‌های جدید (IP × SNI) به explorer
        ↓ pool.refresh()
  pool بلافاصله بهترین جفت‌های جدید را فعال می‌کند
```

---

## پیش‌نیازها

- **Python 3.8** یا بالاتر
- بدون وابستگی خارجی برای استفاده معمول

---

## نصب

### روش ۱ — pip (توصیه‌شده)

```bash
git clone https://github.com/hjfisher/SNISPF-HJ.git
cd SNISPF-HJ
pip install .
snispf-hj --info
```

یا تک‌خطی بدون کلون:

```bash
pip install git+https://github.com/hjfisher/SNISPF-HJ.git
```

> **اندروید / Termux:**
> ```bash
> pip install . --break-system-packages
> ```

### روش ۲ — اجرا از سورس

```bash
git clone https://github.com/hjfisher/SNISPF-HJ.git
cd SNISPF-HJ
python3 run.py --info
```

---

## ساخت فایل اجرایی (exe)

با ابزار [PyInstaller](https://pyinstaller.org) می‌توانی SNISPF-HJ را به یک
**فایل اجرایی تکی** تبدیل کنی که روی هر دستگاهی بدون نصب Python اجرا می‌شود.

> **مهم:** PyInstaller همیشه برای همان سیستم‌عاملی که روی آن اجرا می‌شود
> خروجی می‌سازد. برای `.exe` باید روی Windows و برای باینری Linux باید روی
> Linux build کنی.

### مرحله ۱ — نصب PyInstaller

```bash
pip install pyinstaller
# اگر روی Windows PowerShell شناخته نشد:
python -m pip install pyinstaller
```

### مرحله ۲ — ساخت

```bash
cd SNISPF-HJ

# فایل اجرایی تکی (توصیه‌شده)
python -m PyInstaller --onefile --name snispf-hj run.py

# همراه با config.json:
# Windows:
python -m PyInstaller --onefile --name snispf-hj --add-data "config.json;." run.py
# Linux / macOS:
python -m PyInstaller --onefile --name snispf-hj --add-data "config.json:." run.py
```

خروجی در پوشه `dist/`:

```
dist/
├── snispf-hj.exe       ← Windows
└── snispf-hj           ← Linux / macOS
```

### مرحله ۳ — اجرا

```powershell
# Windows
dist\snispf-hj.exe --config config.json
```
```bash
# Linux / macOS
chmod +x dist/snispf-hj && ./dist/snispf-hj --config config.json
```

**نکات:**
- اگر `config.json` داخل exe نبود، آن را کنار فایل اجرایی قرار بده.
- آنتی‌ویروس‌های Windows گاهی فایل‌های PyInstaller را مشکوک می‌شناسند — این
  یک false positive شناخته‌شده است.

---

## شروع سریع

```bash
# با config.json پیش‌فرض (pool + discovery فعال)
snispf-hj --config config.json

# حالت تک‌جفت (بدون pool)
snispf-hj --listen 0.0.0.0:40443 --connect 172.66.41.252:443 --sni github.com --method fragment
```

خروجی مورد انتظار:

```
Connection pool active — 418 pair(s), 3 active slot(s)
Dynamic IP discovery active — batch=100  interval=120s
Upstream selection: POOL (multi-IP / multi-SNI)
Bypass strategy: combined
Listening on 0.0.0.0:40443
Ready! Configure your application to use:
  Address: 127.0.0.1:40443
```

کلاینت خود (`v2ray`، `xray`، افزونه پروکسی مرورگر، ...) را روی
**`127.0.0.1:40443`** تنظیم کن.

---

## پیکربندی

پرچم‌های CLI همیشه مقادیر فایل کانفیگ را override می‌کنند.

```jsonc
{
  "LISTEN_HOST": "0.0.0.0",
  "LISTEN_PORT": 40443,
  "CONNECT_PORT": 443,
  "BYPASS_METHOD": "combined",
  "FRAGMENT_STRATEGY": "sni_split",
  "FRAGMENT_DELAY": 0.1,
  "USE_TTL_TRICK": false,
  "FAKE_SNI_METHOD": "prefix_fake",

  // ── Pool ───────────────────────────────────────────────────────────
  "ACTIVE_SLOTS": 3,
  "HEALTH_CHECK_INTERVAL": 30,
  "HEALTH_CHECK_TIMEOUT": 3,
  "PROBE_COUNT": 5,
  "LOSS_THRESHOLD": 0.20,
  "DEAD_THRESHOLD": 0.80,
  "DRAIN_TIMEOUT": 30,
  "MAX_DRAINING": 5,

  // ── حذف و بازیافت ──────────────────────────────────────────────────
  "EVICT_EVERY": 3,
  "EVICT_COUNT": 2,
  "RECYCLE_ENABLED": true,
  "RECYCLE_EVERY": 6,
  "RECYCLE_BATCH": 2,
  "RECYCLE_MIN_COOLDOWN": 180,
  "RECYCLE_MAX_QUARANTINE": 100,
  "QUARANTINE_SCOPE": "both",        // static | dynamic | both

  "CONNECT_IPS": ["172.66.41.252", "108.162.196.145"],
  "FAKE_SNIS": ["github.com", "google.com"],

  // ── کشف خودکار IP ─────────────────────────────────────────────────
  "DYNAMIC_IP_DISCOVERY": true,
  "DISCOVERY_BATCH": 100,
  "DISCOVERY_INTERVAL": 120,
  "DISCOVERY_PROBE_TRIES": 3,
  "DISCOVERY_TIMEOUT": 2.0,
  "DISCOVERY_MIN_SUCCESS": 0.50,
  "DISCOVERY_MAX_IPS": 200,

  // ── حذف و بازیافت SNI (مشابه تنظیمات IP در بالا) ────────────────────
  "SNI_EVICT_EVERY": 3,
  "SNI_EVICT_COUNT": 1,
  "SNI_RECYCLE_ENABLED": true,
  "SNI_RECYCLE_EVERY": 6,
  "SNI_RECYCLE_BATCH": 2,
  "SNI_RECYCLE_MIN_COOLDOWN": 180,
  "SNI_RECYCLE_MAX_QUARANTINE": 100,
  "SNI_QUARANTINE_SCOPE": "both",     // static | dynamic | both

  // ── کشف خودکار SNI ───────────────────────────────────────────────
  "DYNAMIC_SNI_DISCOVERY": true,
  "SNI_DISCOVERY_BATCH": 50,
  "SNI_DISCOVERY_INTERVAL": 120,
  "SNI_SOURCE_REFRESH_INTERVAL": 21600,
  "SNI_DISCOVERY_PROBE_TRIES": 3,
  "SNI_DISCOVERY_TIMEOUT": 2.0,
  "SNI_DISCOVERY_MIN_SUCCESS": 0.50,
  "MAX_DYNAMIC_SNIS": 100,
  "SNI_DISCOVERY_DOMAINS_PER_SOURCE": 5000,

  // ── شکل‌دهی ترافیک (پیش‌فرض غیرفعال) ─────────────────────────────
  "TRAFFIC_SHAPING_ENABLED": false,
  "SHAPING_MIN_CHUNK": 200,
  "SHAPING_MAX_CHUNK": 1200,
  "SHAPING_MIN_DELAY_MS": 5,
  "SHAPING_MAX_DELAY_MS": 40,
  "SHAPING_DIRECTION": "download_only" // download_only | both
}
```

---

## تنظیمات Pool

| کلید | پیش‌فرض | توضیح |
|---|---|---|
| `CONNECT_IPS` | `[]` | لیست IP های upstream ثابت |
| `FAKE_SNIS` | `[]` | لیست نام‌های میزبان جعلی |
| `ACTIVE_SLOTS` | `3` | تعداد جفت‌های همزمان فعال |
| `HEALTH_CHECK_INTERVAL` | `30` | ثانیه بین دورهای بررسی |
| `HEALTH_CHECK_TIMEOUT` | `3` | تایم‌اوت TLS handshake هر probe |
| `PROBE_COUNT` | `5` | تعداد probe TLS در هر دور |
| `LOSS_THRESHOLD` | `0.20` | امتیاز loss برای drain کردن جفت |
| `DEAD_THRESHOLD` | `0.80` | امتیاز loss برای مرده اعلام کردن جفت |
| `DRAIN_TIMEOUT` | `30` | ثانیه تا بستن اجباری کانکشن‌های draining |
| `MAX_DRAINING` | `5` | حداکثر جفت‌های همزمان در draining؛ قدیمی‌ترین force-close می‌شود |

**حالت تک‌جفت:** اگر هر دو لیست `CONNECT_IPS`/`FAKE_SNIS` فقط یک عنصر
داشته باشند (یا کلیدهای قدیمی `CONNECT_IP`/`FAKE_SNI` استفاده شوند)، pool
غیرفعال می‌شود و ابزار در حالت مستقیم بدون سربار کار می‌کند.

---

## امتیازدهی: سلامت یک جفت چطور سنجیده می‌شود؟

هر جفت `(IP، SNI)` با یک **TLS handshake واقعی** probe می‌شود — یک TCP
connect ساده کافی نیست، چون سروری ممکن است اتصال TCP را قبول کند ولی لایهٔ
TLS را رد کند یا قطع کند. این probe از همان SNI خود جفت استفاده می‌کند، پس
دقیقاً همان چیزی را تست می‌کند که forwarder در ترافیک واقعی می‌فرستد.

### ردیابی Loss — میانگین متحرک نمایی

به‌جای یک شمارندهٔ تمام‌عمر «موفقیت در برابر شکست»، هر جفت یک **EMA
(میانگین متحرک نمایی)** از loss نگه می‌دارد، جدا برای نتایج probe و
ترافیک واقعی forward‌شده:

```
ema_loss_جدید = α × loss_این_رویداد + (1 − α) × ema_loss_قبلی
```

- `α` (probe) = `0.25` — چون probe ها زمان‌بندی ثابت دارند، یک آلفای
  متوسط امتیاز را به شرایط اخیر واکنش‌پذیر نگه می‌دارد.
- `α` (ترافیک واقعی) = `0.15` — چون اتصال‌های واقعی می‌توانند به‌صورت
  burst بیایند، یک آلفای کوچک‌تر مانع از این می‌شود که یک burst بد بر
  کل امتیاز غلبه کند.

**چرا این مهم است:** جفتی که مدتی نامناسب بوده و از آن زمان بهبود یافته،
با رسیدن نتایج خوب جدید، EMA‌اش به‌تدریج به سمت صفر کاهش می‌یابد —
شکست‌های قدیمی محو می‌شوند به‌جای اینکه برای همیشه روی جفت سنگینی کنند.
هیچ «پنجرهٔ حافظهٔ ثابتی» برای تنظیم وجود ندارد؛ منحنی بهبود نرم و خودکار
است.

### امتیاز ترکیبی

```
score = ۰٫۶۰ × combined_loss_rate
      + ۰٫۲۰ × latency_score
      + ۰٫۲۰ × probe_loss_rate
```

- `combined_loss_rate` ترکیبی از ۷۰٪ EMA loss ترافیک واقعی + ۳۰٪ EMA loss
  probe است (وقتی حداقل ۱۰ پکت واقعی مشاهده شده باشد؛ قبل از آن فقط loss
  probe استفاده می‌شود).
- `latency_score` میانگین زمان TLS handshake است، نرمال‌شده نسبت به سقف
  ۱۵۰۰ میلی‌ثانیه — جفتی که loss ندارد ولی پیوسته کند است، باز هم امتیاز
  بدتری از یک جفت سریع می‌گیرد.
- `probe_loss_rate` به‌طور مستقل هم در امتیاز لحاظ می‌شود (علاوه بر اینکه
  بخشی از `combined_loss_rate` است) تا سلامت probe همیشه وزن مستقیمی
  داشته باشد حتی وقتی ترافیک واقعی وجود دارد.

امتیاز کمتر یعنی بهتر. جفت مرده امتیاز `+inf` می‌گیرد (هرگز انتخاب
نمی‌شود). جفتی که هنوز probe نشده امتیاز `0.5` می‌گیرد تا ناشناخته‌ها
شانس عادلانهٔ اول را داشته باشند به‌جای اینکه فرض شوند بد هستند.

---

## حذف، قرنطینه و بازیافت IP

Pool نباید بی‌نهایت بزرگ شود، و وزنهٔ مرده نباید بنشیند و میانگین را
خراب کند. هر `EVICT_EVERY` چرخهٔ سلامت، تعداد `EVICT_COUNT` IP با بدترین
امتیاز میانگین حذف می‌شوند — ولی **پاک نمی‌شوند**. آن‌ها به یک لیست
**قرنطینه** منتقل می‌شوند.

```
Pool فعال → ضعیف شد → EVICT_EVERY چرخه → قرنطینه
                                              │
                          RECYCLE_EVERY      │  نمونه تصادفی،
                          چرخه                ▼  probe دوباره با TLS
                                       ┌─────────────┐
                                       │   سالم؟      │
                                       └──────┬──────┘
                            بله ───────────────┤─────────────── خیر
                             │                                  │
                             ▼                                  ▼
                  بازگردانده با یک PairStats           در قرنطینه می‌ماند
                  تازه و بدون تاریخچه                  تا تلاش بعدی
                  (دوباره در چرخهٔ فعال)                 (رعایت cooldown)
```

هر `RECYCLE_EVERY` چرخه، یک دسته تصادفی از IP های قرنطینه‌شده با یک TLS
handshake واقعی دوباره تست می‌شوند. IP ای که قبول شود با یک `PairStats`
**کاملاً تازه** بازگردانده می‌شود — بدون هیچ خاطره‌ای از شکست‌های قبلی —
پس صرفاً بر اساس عملکرد فعلی‌اش قضاوت می‌شود. IP هایی که شکست بخورند تا
تلاش مجاز بعدی (طبق `RECYCLE_MIN_COOLDOWN`) در قرنطینه می‌مانند.

خود لیست قرنطینه با `RECYCLE_MAX_QUARANTINE` سقف دارد — اگر از این مقدار
بیشتر شود، قدیمی‌ترین‌ها برای همیشه حذف می‌شوند، تا مصرف حافظه حتی در
اجراهای بسیار طولانی محدود بماند.

### انتخاب اینکه کدام IP ها واجد شرایط هستند: `QUARANTINE_SCOPE`

به‌طور پیش‌فرض، هم IP هایی که خودت دستی انتخاب کرده‌ای (`CONNECT_IPS` در
کانفیگ) و هم IP هایی که اسکنر discovery پیدا کرده، واجد شرایط حذف و
بازیافت هستند. می‌توانی این را با `QUARANTINE_SCOPE` محدود کنی:

| مقدار | رفتار |
|---|---|
| `"both"` (پیش‌فرض) | هم IP های static و هم IP های کشف‌شدهٔ dynamic می‌توانند حذف/بازیافت شوند |
| `"static"` | فقط IP هایی که در `CONNECT_IPS` لیست کرده‌ای حذف/بازیافت می‌شوند — IP های کشف‌شده دست‌نخورده می‌مانند |
| `"dynamic"` | فقط IP هایی که اسکنر discovery پیدا کرده حذف/بازیافت می‌شوند — لیست دستی‌ات هرگز لمس نمی‌شود |

این برای زمانی مفید است که، مثلاً، به لیست IP دستی خودت اعتماد داری و
فقط می‌خواهی رفتار چرخش/بازیافت روی چیزی که اسکنر discovery پیدا می‌کند
اعمال شود.

| کلید | پیش‌فرض | توضیح |
|---|---|---|
| `EVICT_EVERY` | `3` | هر چند چرخه یک‌بار eviction اجرا شود |
| `EVICT_COUNT` | `2` | تعداد IP حذف‌شده در هر دور eviction |
| `RECYCLE_ENABLED` | `true` | فعال/غیرفعال کردن مکانیزم بازیافت |
| `RECYCLE_EVERY` | `6` | هر چند چرخه یک‌بار تلاش بازیافت اجرا شود |
| `RECYCLE_BATCH` | `2` | چند IP قرنطینه در هر تلاش دوباره تست شوند |
| `RECYCLE_MIN_COOLDOWN` | `180` | حداقل ثانیه بین دو تلاش روی همان IP |
| `RECYCLE_MAX_QUARANTINE` | `100` | سقف اندازه قرنطینه؛ قدیمی‌ترها برای همیشه حذف می‌شوند |
| `QUARANTINE_SCOPE` | `"both"` | کدام مبدأ IP واجد شرایط است: `"static"`، `"dynamic"`، یا `"both"` |

**مثال زمان‌بندی:** با مقادیر پیش‌فرض (`HEALTH_CHECK_INTERVAL=30`،
`EVICT_EVERY=3`، `EVICT_COUNT=2`) → هر ۹۰ ثانیه ۲ تا از ضعیف‌ترین IP ها
قرنطینه می‌شوند. با `RECYCLE_EVERY=6` → هر ۱۸۰ ثانیه، ۲ IP تصادفی از
قرنطینه شانس دوباره دریافت می‌کنند.

---

## کشف خودکار IP

| کلید | پیش‌فرض | توضیح |
|---|---|---|
| `DYNAMIC_IP_DISCOVERY` | `false` | فعال‌سازی کشف خودکار (`true` برای فعال) |
| `DISCOVERY_BATCH` | `100` | تعداد IP نمونه‌گیری‌شده در هر دور |
| `DISCOVERY_INTERVAL` | `120` | ثانیه بین دورهای اسکن |
| `DISCOVERY_PROBE_TRIES` | `3` | تعداد TLS handshake برای هر کاندیدا |
| `DISCOVERY_TIMEOUT` | `2.0` | تایم‌اوت هر TLS handshake (ثانیه) |
| `DISCOVERY_MIN_SUCCESS` | `0.50` | حداقل نرخ موفقیت برای پذیرش IP (۰–۱) |
| `DISCOVERY_MAX_IPS` | `200` | سقف تعداد IPهای داینامیک |

کشف خودکار از رنج‌های رسمی IP کلودفلر نمونه‌گیری می‌کند و فقط IP هایی را
قبول می‌کند که یک TLS handshake واقعی را با موفقیت در حد آستانه کامل
کنند — یک TCP connect ساده کافی نیست، چون بعضی IP ها اتصال را قبول
می‌کنند ولی هرگز TLS را کامل نمی‌کنند. تمام عملیات در daemon thread
اجرا می‌شود و هیچ اتصال فعالی را قطع نمی‌کند. اولین اسکن ۱۵ ثانیه بعد از
راه‌اندازی شروع می‌شود تا pool اول bootstrap شود.

IP هایی که این‌طور کشف می‌شوند، داخلاً با `origin = "dynamic"` برچسب
می‌خورند — همین برچسب است که `QUARANTINE_SCOPE` برای تفکیک آن‌ها از
`CONNECT_IPS` استفاده می‌کند.

---

## کشف خودکار SNI

معادل کشف خودکار IP اما روی محور SNI، برگرفته از
[`cf_sni_scanner`](https://github.com/hjfisher/cf_sni_scanner). به‌جای
نمونه‌گیری IP تصادفی از رنج‌های کلودفلر، این ماژول نام دامنه‌های تصادفی را
از لیست‌های بزرگ رتبه‌بندی عمومی (Tranco، Cisco Umbrella، Majestic
Million) به‌علاوهٔ یک لیست seed دستچین‌شده نمونه‌گیری می‌کند، بررسی می‌کند
که آیا به یک IP کلودفلر resolve می‌شود یا نه، و آن را با یک TLS handshake
واقعی روی یکی از IP های فعال pool تست می‌کند. دامنه‌هایی که قبول شوند به
عنوان SNI جدید وارد pool می‌شوند و فقط با IP هایی جفت می‌شوند که در حال
حاضر قرنطینه نیستند.

چون دانلود لیست‌های رتبه‌بندی نسبتاً سنگین است (هرکدام چند مگابایت
CSV/ZIP) و این لیست‌ها روز به روز تغییر چندانی نمی‌کنند، کار به دو
تایمر مستقل تقسیم شده:

- **رفرش منبع** — هر `SNI_SOURCE_REFRESH_INTERVAL` ثانیه (پیش‌فرض: ۶
  ساعت)، لیست‌های عمومی یک‌بار دانلود، با لیست seed ترکیب، و در حافظه
  کش می‌شوند. هیچ probeای اینجا انجام نمی‌شود.
- **کشف** — هر `SNI_DISCOVERY_INTERVAL` ثانیه، یک batch از استخر کش‌شده
  نمونه‌گیری، resolve، برای میزبانی کلودفلر فیلتر، و با TLS تست می‌شود
  و در صورت موفقیت وارد pool می‌شود.

| کلید | پیش‌فرض | توضیح |
|---|---|---|
| `DYNAMIC_SNI_DISCOVERY` | `false` | فعال‌سازی کشف خودکار SNI (`true` برای فعال) |
| `SNI_DISCOVERY_BATCH` | `50` | تعداد دامنهٔ کاندیدا نمونه‌گیری‌شده در هر دور |
| `SNI_DISCOVERY_INTERVAL` | `120` | ثانیه بین دورهای کشف |
| `SNI_SOURCE_REFRESH_INTERVAL` | `21600` | ثانیه بین دانلود مجدد Tranco/Umbrella/Majestic (پیش‌فرض: ۶ ساعت) |
| `SNI_DISCOVERY_PROBE_TRIES` | `3` | تعداد تلاش TLS handshake برای هر کاندیدا |
| `SNI_DISCOVERY_TIMEOUT` | `2.0` | تایم‌اوت هر TLS handshake (ثانیه) |
| `SNI_DISCOVERY_MIN_SUCCESS` | `0.50` | حداقل نرخ موفقیت برای پذیرش SNI (۰–۱) |
| `MAX_DYNAMIC_SNIS` | `100` | سقف تعداد SNIهای داینامیک |
| `SNI_DISCOVERY_DOMAINS_PER_SOURCE` | `5000` | حداکثر دامنه دریافتی از هر منبع رتبه‌بندی |

SNI هایی که این‌طور کشف می‌شوند، مثل کشف IP با `origin = "dynamic"` برچسب
می‌خورند — همین برچسب است که `SNI_QUARANTINE_SCOPE` برای تفکیک آن‌ها از
`FAKE_SNIS` دستی‌ات استفاده می‌کند.

---

## حذف، قرنطینه و بازیافت SNI

همان چرخهٔ حذف/قرنطینه/بازیافتی که بالاتر برای IP توضیح داده شد، به‌طور
مستقل روی SNI هم اعمال می‌شود. هر `SNI_EVICT_EVERY` چرخهٔ سلامت، ضعیف‌ترین
`SNI_EVICT_COUNT` تا SNI به‌جای حذف کامل، قرنطینه می‌شوند؛ هر
`SNI_RECYCLE_EVERY` چرخه، دسته‌ای از SNI های قرنطینه با یک TLS handshake
واقعی دوباره تست و در صورت موفقیت با امتیاز تازه بازگردانده می‌شوند.

| کلید | پیش‌فرض | توضیح |
|---|---|---|
| `SNI_EVICT_EVERY` | `3` | هر چند چرخه یک‌بار ضعیف‌ترین SNI حذف شود |
| `SNI_EVICT_COUNT` | `1` | تعداد SNI حذف‌شده در هر دور eviction |
| `SNI_RECYCLE_ENABLED` | `true` | فعال/غیرفعال کردن بازیافت SNI |
| `SNI_RECYCLE_EVERY` | `6` | هر چند چرخه یک‌بار تلاش بازیافت SNI اجرا شود |
| `SNI_RECYCLE_BATCH` | `2` | چند SNI قرنطینه در هر تلاش دوباره تست شوند |
| `SNI_RECYCLE_MIN_COOLDOWN` | `180` | حداقل ثانیه بین دو تلاش روی همان SNI |
| `SNI_RECYCLE_MAX_QUARANTINE` | `100` | سقف اندازهٔ قرنطینهٔ SNI؛ قدیمی‌ترها برای همیشه حذف می‌شوند |
| `SNI_QUARANTINE_SCOPE` | `"both"` | کدام مبدأ SNI واجد شرایط است: `"static"` (فقط `FAKE_SNIS`)، `"dynamic"` (فقط کشف‌شده)، یا `"both"` |

این به تو اجازه می‌دهد، مثلاً، `FAKE_SNIS` دستی‌ات را از حذف شدن مصون
نگه‌داری (با کنار گذاشتن حالت `"static"` در `SNI_QUARANTINE_SCOPE`) در
حالی که SNI های کشف‌شده همچنان چرخش دارند — یا برعکس — کاملاً مستقل از
تنظیم `QUARANTINE_SCOPE` برای IP ها.

---

## شکل‌دهی ترافیک (Traffic Shaping)

بعضی شبکه‌ها (روی برخی اپراتورهای موبایل مشاهده شده) اجازه می‌دهند
TLS handshake به‌درستی رد شود — یعنی روش‌های fragmentation/fake-SNI کار
می‌کنند — اما بعد از آن، خود جریان داده *بعد از handshake* را
فینگرپرینت می‌کنند. پروتکل‌های پروکسی که ابزارهای بالادستی (VLESS،
VMess، Trojan، Hysteria و غیره) روی آن حمل می‌شوند، بار ترافیکی بزرگ،
پیوسته و دوطرفه‌ای تولید می‌کنند که شبیه مرور معمولی HTTPS نیست و به‌محض
شروع ترافیک واقعی، محدود یا قطع می‌شود.

SNISPF-HJ فقط handshake را مدیریت می‌کند — بعد از آن هر چیزی بایت‌به‌بایت
بین کلاینت و core بالادستی relay می‌شود. شکل‌دهی ترافیک در همین مسیر
relay قرار می‌گیرد و جریان بایت خروجی را به تکه‌های تصادفیِ کوچک‌تر با
تأخیرهای تصادفی بین آن‌ها بازآرایی می‌کند، تا بیشتر شبیه ترافیک معمولی
وب به‌نظر برسد تا یک تونل پروکسی صاف و سریع.

این قابلیت **به‌طور پیش‌فرض غیرفعال** است، چون تأخیر اضافه می‌کند و فقط
روی شبکه‌هایی که این نوع فینگرپرینتینگ مبتنی بر جریان را انجام می‌دهند
مفید است.

| کلید | پیش‌فرض | توضیح |
|---|---|---|
| `TRAFFIC_SHAPING_ENABLED` | `false` | فعال‌سازی شکل‌دهی ترافیک |
| `SHAPING_MIN_CHUNK` | `200` | حداقل اندازهٔ تکه به بایت |
| `SHAPING_MAX_CHUNK` | `1200` | حداکثر اندازهٔ تکه به بایت |
| `SHAPING_MIN_DELAY_MS` | `5` | حداقل تأخیر بین تکه‌ها (میلی‌ثانیه) |
| `SHAPING_MAX_DELAY_MS` | `40` | حداکثر تأخیر بین تکه‌ها (میلی‌ثانیه) |
| `SHAPING_DIRECTION` | `"download_only"` | `"download_only"` فقط ترافیک سرور→کلاینت را شکل می‌دهد (جایی که معمولاً تشخیص جریان اتفاق می‌افتد)؛ `"both"` آپلود کلاینت→سرور را هم شامل می‌شود |

---

## پرچم‌های CLI

```
--config, -C FILE         مسیر فایل کانفیگ JSON
--generate-config PATH    ساخت کانفیگ پیش‌فرض و خروج
--listen, -l HOST:PORT     آدرس گوش‌دادن (پیش‌فرض: 0.0.0.0:40443)
--connect, -c IP:PORT      آدرس سرور مقصد (حالت تک‌جفت)
--sni,    -s HOSTNAME      نام میزبان جعلی (حالت تک‌جفت)
--method, -m METHOD        fragment | fake_sni | combined
--fragment-strategy STR    sni_split | half | multi | tls_record_frag
--fragment-delay  SEC      فاصله بین قطعات (ثانیه)
--ttl-trick                فعال‌سازی ترفند IP TTL
--no-raw                   غیرفعال‌سازی raw socket
--check-domains FILE       بررسی گروهی دامنه‌ها برای Cloudflare
--check-workers N          تعداد ورکر موازی (پیش‌فرض: ۵۰)
--check-timeout SEC        تایم‌اوت هر دامنه (پیش‌فرض: ۳ ثانیه)
--output FILE              ذخیرهٔ دامنه‌های تأییدشده
--check-http                تأیید HTTP هم در حین بررسی دامنه
--verbose, -v               لاگ کامل (debug)
--quiet,   -q               فقط هشدارها
--version, -V               نمایش نسخه و خروج
--info                      نمایش قابلیت‌های سیستم و خروج
```

---

## روش‌های دور زدن

| روش | نحوه کار | نیاز به دسترسی |
|---|---|---|
| `fragment` | شکستن ClientHello در مرز SNI به چند بخش TCP | هیچ |
| `fake_sni` | ارسال ClientHello جعلی قبل از واقعی | root برای raw socket؛ بدون آن TTL trick |
| `combined` | هر دو همزمان — توصیه‌شده | مثل fake_sni |

---

## استراتژی‌های قطعه‌بندی

| استراتژی | کار |
|---|---|
| `sni_split` (پیش‌فرض) | شکستن دقیقاً روی هاست‌نیم SNI |
| `half` | دو نیمهٔ تقریباً مساوی |
| `multi` | چند قطعهٔ ۵–۱۰ بایتی |
| `tls_record_frag` | شکستن در لایهٔ رکورد TLS |

---

## بررسی‌گر دامنه

```bash
snispf-hj --check-domains domains.txt
snispf-hj --check-domains domains.txt --output verified.txt --check-http -v
```

می‌گوید کدام دامنه‌ها پشت Cloudflare هستند — مفید برای ساختن `FAKE_SNIS`.

---

## پشتیبانی از پلتفرم‌ها

| پلتفرم | وضعیت | یادداشت |
|---|---|---|
| Linux | ✅ کامل | raw socket با `sudo` یا `CAP_NET_RAW` |
| macOS | ✅ کامل | TTL trick خودکار |
| Windows 10 / 11 | ✅ کامل | fragment/combined؛ بدون raw socket |
| Android روی Termux | ✅ پشتیبانی | بدون root؛ TTL trick خودکار |
| OpenBSD / FreeBSD | ⚡ best-effort | fragment کار می‌کند |

برای دیدن قابلیت‌های دقیق سیستم: `snispf-hj --info`

---

## رفع اشکال

**پورت اشغال است**
```bash
snispf-hj --listen :40444 --config config.json
```

**`pyinstaller` روی Windows PowerShell شناخته نشد**
```powershell
python -m pip install pyinstaller
python -m PyInstaller --onefile --name snispf-hj run.py
```

**Pool همهٔ جفت‌ها را dead نشان می‌دهد**
- مطمئن شو `CONNECT_IPS` روی پورت ۴۴۳ یک TLS handshake واقعی را قبول
  می‌کنند (نه فقط TCP — بعضی سرورها اتصال را قبول می‌کنند ولی لایهٔ TLS
  را رد می‌کنند).
- `HEALTH_CHECK_TIMEOUT` را به `6` افزایش بده.
- `DEAD_THRESHOLD` را به `0.90` افزایش بده.

**کانکشن‌ها به‌طور غیرمنتظره بسته می‌شوند**
- احتمالاً `DRAIN_TIMEOUT` فعال شده — مقدار را بیشتر کن: `"DRAIN_TIMEOUT": 60`
- یا `EVICT_COUNT` را به `1` کاهش بده تا rotation کندتر باشد.

**جفتی که قبلاً کار می‌کرد، برای همیشه «بد» باقی مانده**
- این دیگر نباید اتفاق بیفتد — چون loss به‌صورت EMA ردیابی می‌شود، جفتی
  که بهبود یابد امتیازش خودکار با رسیدن probe/کانکشن‌های موفق جدید بهتر
  می‌شود. اگر هنوز گیر کرده به نظر می‌رسد، چک کن آیا کاملاً evict شده؛
  IP های قرنطینه‌شده فقط هر `RECYCLE_EVERY` چرخه (با رعایت
  `RECYCLE_MIN_COOLDOWN`) دوباره تست می‌شوند، پس بهبود فوری نیست.

**Discovery هیچ IP ای پیدا نمی‌کند**
- `DISCOVERY_TIMEOUT` را افزایش بده: `4.0`
- آستانه را شل‌تر کن: `"DISCOVERY_MIN_SUCCESS": 0.34`

**می‌خواهم IP های دستی‌ام از eviction محفوظ بمانند**
- `"QUARANTINE_SCOPE": "dynamic"` تنظیم کن — فقط IP های کشف‌شده توسط
  discovery حذف/بازیافت می‌شوند؛ لیست `CONNECT_IPS` تو دست‌نخورده می‌ماند.

**روی بعضی سایت‌ها کار نمی‌کند**
- `--method combined --fragment-strategy multi` را امتحان کن.
- IP و SNI بیشتری اضافه کن.
- `FRAGMENT_DELAY` را افزایش بده (مثلاً `0.25`).
- با `--check-domains` تأیید کن SNI‌هایت پشت Cloudflare هستند.

**اندروید / Termux: خطای pip**
```bash
pip install . --break-system-packages
```

---

## ساختار پروژه

```
SNISPF-HJ/
├── run.py                        # نقطهٔ ورود (python3 run.py …)
├── config.json                   # کانفیگ پیش‌فرض
├── pyproject.toml                # متادیتا — snispf و snispf-hj
├── README.md / README_FA.md
├── LICENSE
└── sni_spoofing/
    ├── cli.py                    # argparse + نقطهٔ ورود اصلی
    ├── forwarder.py              # فوروردر async TCP + یکپارچه‌سازی pool
    ├── pool.py                   # PairStats (EMA، latency، امتیازدهی)،
    │                             # CombinationExplorer (probe، eviction،
    │                             # قرنطینه، بازیافت)، ActivePool،
    │                             # ConnectionManager
    ├── ip_discovery.py           # اسکنر خودکار IP از Cloudflare (probe با TLS)
    ├── sni_discovery.py          # اسکنر خودکار SNI (Tranco/Umbrella/Majestic + لیست seed)
    ├── shaping.py                # شکل‌دهی ترافیک بعد از handshake (chunking/pacing)
    ├── bypass/                   # استراتژی‌های fragment / fake-SNI / raw
    ├── tls/                      # ساخت و تجزیهٔ ClientHello
    ├── scanner/                  # بررسی گروهی دامنه‌های Cloudflare
    └── utils/                    # تشخیص پلتفرم، کمک‌های IP/port
```

---

## تشکر و منابع

- **[@Rainman69](https://github.com/Rainman69)** — معماری اصلی SNISPF، موتور
  fragmentation، پشتیبانی cross-platform، و CLI.
- **[@patterniha](https://github.com/patterniha)** — ایدهٔ اولیهٔ SNI spoofing
  و explorer ترکیب چند-IP/چند-SNI.
- **[@hjfisher](https://github.com/hjfisher)** — `CombinationExplorer`،
  `ActivePool`، `ConnectionManager`، `IPDiscovery`، `SNIDiscovery`،
  `TrafficShaper`، امتیازدهی مبتنی بر EMA، drain timeout، حذف/قرنطینه/بازیافت
  IP و SNI، و یکپارچه‌سازی کلی pool.
- **[@bia-pain-bache](https://github.com/bia-pain-bache)** و
  **[@Ptechgithub](https://github.com/Ptechgithub)** — روش اسکن IP Cloudflare
  که الهام‌بخش `ip_discovery.py` بود.
- [`cf_sni_scanner`](https://github.com/hjfisher/cf_sni_scanner) — روش
  نمونه‌گیری دامنه از Tranco/Umbrella/Majestic که الهام‌بخش
  `sni_discovery.py` بود.

---

## لایسنس

[MIT](LICENSE) © Rainman69, hjfisher
