# SNISPF-HJ

### ابزار خط‌فرمان دور زدن DPI روی همه پلتفرم‌ها — با pool تطبیقی و کشف خودکار IP

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
[@Rainman69](https://github.com/Rainman69) است، با اضافه شدن **pool تطبیقی
چند-IP / چند-SNI** و **کشف خودکار IP از رنج‌های رسمی Cloudflare** — ایده‌هایی
برگرفته از کارهای [@patterniha](https://github.com/patterniha)،
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
- [کشف خودکار IP](#کشف-خودکار-ip)
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
| بررسی سلامت | ندارد | حلقهٔ TCP probe مداوم |
| انتخاب جفت | ثابت | وزن‌دار تصادفی |
| جایگزینی بدون قطعی | ندارد | draining با timeout قابل تنظیم |
| بستن اجباری drain | ندارد | بعد از `DRAIN_TIMEOUT` ثانیه کانکشن‌ها بسته می‌شوند |
| حذف IP های ضعیف | ندارد | ضعیف‌ترین IP ها دوره‌ای حذف می‌شوند |
| کشف خودکار IP | ندارد | اسکن رنج‌های رسمی Cloudflare در پس‌زمینه |
| دستور اجرا | `snispf` | `snispf` **و** `snispf-hj` |
| ماژول‌های جدید | — | `pool.py`، `ip_discovery.py` |

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

در هنگام راه‌اندازی، یک نمونهٔ تصادفی از جفت‌های `(IP، SNI)` با TCP probe
بررسی می‌شود. جفت‌هایی که پاسخ خوب می‌دهند وارد **pool فعال** می‌شوند.
یک thread پس‌زمینه هر ~۳۰ ثانیه pool را دوباره بررسی و جفت‌های ضعیف را
جایگزین می‌کند.

### Draining با Timeout

وقتی یک جفت ضعیف می‌شود وارد حالت **draining** می‌شود: اتصال جدیدی به آن
داده نمی‌شود ولی اتصال‌های قبلی ادامه می‌دهند. بعد از `DRAIN_TIMEOUT` ثانیه
(پیش‌فرض: ۳۰) اتصال‌های باقی‌مانده بسته می‌شوند. سقف `MAX_DRAINING` مانع
بی‌کنترل شدن لیست draining می‌شود.

### حذف IP های ضعیف (Eviction)

هر `EVICT_EVERY` چرخه (پیش‌فرض: هر ۳ × ۳۰ ثانیه = ۹۰ ثانیه)، تعداد
`EVICT_COUNT` ضعیف‌ترین IP (بر اساس میانگین نرخ loss) به‌طور دائمی از pool
حذف می‌شوند تا جای خود را به IP های تازه‌تر بدهند. IP هایی که الان اتصال
فعال دارند محافظت می‌شوند.

### کشف خودکار IP

یک thread دوم مستقل، از رنج‌های رسمی Cloudflare به‌صورت تصادفی IP نمونه
می‌گیرد، آن‌ها را با TCP probe بررسی می‌کند، و IPهای سالم را به pool
تزریق می‌کند — همزمان با سرویس‌دهی به اتصال‌ها.

```
۱۵ CIDR رسمی Cloudflare  →  نمونه‌گیری ۱۰۰ IP تصادفی  →  TCP probe موازی
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

کلاینت خود را روی **`127.0.0.1:40443`** تنظیم کن.

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

  // ── Pool ثابت ──────────────────────────────────────────────────────
  "ACTIVE_SLOTS": 3,
  "HEALTH_CHECK_INTERVAL": 30,
  "HEALTH_CHECK_TIMEOUT": 3,
  "PROBE_COUNT": 5,
  "LOSS_THRESHOLD": 0.20,
  "DEAD_THRESHOLD": 0.80,
  "DRAIN_TIMEOUT": 30,
  "MAX_DRAINING": 5,
  "EVICT_EVERY": 3,
  "EVICT_COUNT": 2,

  "CONNECT_IPS": ["172.66.41.252", "108.162.196.145"],
  "FAKE_SNIS": ["github.com", "google.com"],

  // ── کشف خودکار IP ─────────────────────────────────────────────────
  "DYNAMIC_IP_DISCOVERY": true,
  "DISCOVERY_BATCH": 100,
  "DISCOVERY_INTERVAL": 120,
  "DISCOVERY_PROBE_TRIES": 3,
  "DISCOVERY_TIMEOUT": 2.0,
  "DISCOVERY_MIN_SUCCESS": 0.50,
  "DISCOVERY_MAX_IPS": 200
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
| `HEALTH_CHECK_TIMEOUT` | `3` | تایم‌اوت TCP connect هر probe |
| `PROBE_COUNT` | `5` | تعداد probe در هر دور |
| `LOSS_THRESHOLD` | `0.20` | نرخ loss برای drain کردن جفت |
| `DEAD_THRESHOLD` | `0.80` | نرخ loss برای مرده اعلام کردن جفت |
| `DRAIN_TIMEOUT` | `30` | ثانیه تا بستن اجباری کانکشن‌های draining |
| `MAX_DRAINING` | `5` | حداکثر جفت‌های همزمان در draining؛ قدیمی‌ترین force-close می‌شود |
| `EVICT_EVERY` | `3` | هر چند چرخه یک‌بار eviction اجرا شود |
| `EVICT_COUNT` | `2` | تعداد IP حذف‌شده در هر دور eviction |

**حالت تک‌جفت:** اگر هر دو لیست فقط یک عنصر داشته باشند، pool غیرفعال
می‌شود و ابزار در حالت مستقیم کار می‌کند.

**مثال زمان‌بندی eviction:** با `HEALTH_CHECK_INTERVAL=30`، `EVICT_EVERY=3`،
`EVICT_COUNT=2` → هر ۹۰ ثانیه ۲ تا از ضعیف‌ترین IP ها حذف و جایگزین می‌شوند.

---

## کشف خودکار IP

| کلید | پیش‌فرض | توضیح |
|---|---|---|
| `DYNAMIC_IP_DISCOVERY` | `false` | فعال‌سازی کشف خودکار (`true` برای فعال) |
| `DISCOVERY_BATCH` | `100` | تعداد IP نمونه‌گیری‌شده در هر دور |
| `DISCOVERY_INTERVAL` | `120` | ثانیه بین دورهای اسکن |
| `DISCOVERY_PROBE_TRIES` | `3` | تعداد TCP connect برای هر کاندیدا |
| `DISCOVERY_TIMEOUT` | `2.0` | تایم‌اوت هر TCP connect (ثانیه) |
| `DISCOVERY_MIN_SUCCESS` | `0.50` | حداقل نرخ موفقیت برای پذیرش IP (۰–۱) |
| `DISCOVERY_MAX_IPS` | `200` | سقف تعداد IPهای داینامیک |

اولین اسکن ۱۵ ثانیه بعد از راه‌اندازی شروع می‌شود. تمام عملیات در daemon
thread اجرا می‌شود و هیچ اتصال فعالی را قطع نمی‌کند.

---

## پرچم‌های CLI

```
--config, -C FILE         مسیر فایل کانفیگ JSON
--generate-config PATH    ساخت کانفیگ پیش‌فرض و خروج
--listen, -l HOST:PORT    آدرس گوش‌دادن (پیش‌فرض: 0.0.0.0:40443)
--connect, -c IP:PORT     آدرس سرور مقصد (حالت تک‌جفت)
--sni,    -s HOSTNAME     نام میزبان جعلی (حالت تک‌جفت)
--method, -m METHOD       fragment | fake_sni | combined
--fragment-strategy STR   sni_split | half | multi | tls_record_frag
--fragment-delay  SEC     فاصله بین قطعات (ثانیه)
--ttl-trick               فعال‌سازی ترفند IP TTL
--no-raw                  غیرفعال‌سازی raw socket
--check-domains FILE      بررسی گروهی دامنه‌ها برای Cloudflare
--check-workers N         تعداد ورکر موازی (پیش‌فرض: ۵۰)
--check-timeout SEC       تایم‌اوت هر دامنه (پیش‌فرض: ۳ ثانیه)
--output FILE             ذخیرهٔ دامنه‌های تأییدشده
--check-http              تأیید HTTP هم در حین بررسی دامنه
--verbose, -v             لاگ کامل (debug)
--quiet,   -q             فقط هشدارها
--version, -V             نمایش نسخه و خروج
--info                    نمایش قابلیت‌های سیستم و خروج
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
- مطمئن شو `CONNECT_IPS` روی پورت ۴۴۳ در دسترس هستند.
- `HEALTH_CHECK_TIMEOUT` را به `6` افزایش بده.
- `DEAD_THRESHOLD` را به `0.90` افزایش بده.

**کانکشن‌ها به‌طور غیرمنتظره بسته می‌شوند**
- احتمالاً `DRAIN_TIMEOUT` فعال شده — مقدار را بیشتر کن: `"DRAIN_TIMEOUT": 60`
- یا `EVICT_COUNT` را به `1` کاهش بده تا rotation کندتر باشد.

**Discovery هیچ IP ای پیدا نمی‌کند**
- `DISCOVERY_TIMEOUT` را افزایش بده: `4.0`
- آستانه را شل‌تر کن: `"DISCOVERY_MIN_SUCCESS": 0.34`

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
    ├── pool.py                   # PairStats، CombinationExplorer،
    │                             # ActivePool، ConnectionManager
    ├── ip_discovery.py           # ★ اسکنر خودکار IP از CIDRهای Cloudflare
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
  `ActivePool`، `ConnectionManager`، `IPDiscovery`، drain timeout، IP eviction،
  و یکپارچه‌سازی با SNISPF.
- **[@bia-pain-bache](https://github.com/bia-pain-bache)** و
  **[@Ptechgithub](https://github.com/Ptechgithub)** — روش اسکن IP Cloudflare
  که الهام‌بخش `ip_discovery.py` بود.

---

## لایسنس

[MIT](LICENSE) © Rainman69, hjfisher
