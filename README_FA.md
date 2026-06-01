# SNISPF-HJ

### ابزار خط‌فرمان دور زدن DPI روی همه پلتفرم‌ها — با pool تطبیقی چند-IP/چند-SNI

```
 ███████╗███╗   ██╗██╗███████╗██████╗ ███████╗
 ██╔════╝████╗  ██║██║██╔════╝██╔══██╗██╔════╝
 ███████╗██╔██╗ ██║██║███████╗██████╔╝█████╗
 ╚════██║██║╚██╗██║██║╚════██║██╔═══╝ ██╔══╝
 ███████║██║ ╚████║██║███████║██║     ██║
 ╚══════╝╚═╝  ╚═══╝╚═╝╚══════╝╚═╝     ╚═╝
```

**[EN README](README.md)**

**SNISPF-HJ** یک فورک از [SNISPF](https://github.com/Rainman69/SNISPF) ساختهٔ
[@Rainman69](https://github.com/Rainman69) است که با یک **pool تطبیقی چند-IP / چند-SNI**
تقویت شده — ایده‌ای که از کارهای
[@patterniha](https://github.com/patterniha) و
[@hjfisher](https://github.com/hjfisher) الهام گرفته است.

به‌جای یک upstream ثابت، ابزار به‌طور مداوم ترکیب‌های (IP، SNI) را بررسی
می‌کند و هر اتصال را از طریق سالم‌ترین جفت هدایت می‌کند — بدون قطع شدن
اتصال‌های فعال.

روی **Windows، macOS، Linux و Android (Termux)** کار می‌کند و برای روش
پیش‌فرض نیازی به دسترسی root ندارد.

پیشنهاد یا سؤال؟ → **[SNISPF/discussions](https://github.com/Rainman69/SNISPF/discussions)**

‎**⭐️ فراموش نشه ⭐️**

---

## فهرست

- [چه چیزی جدید است؟](#چه-چیزی-جدید-است)
- [چطور کار می‌کند؟](#چطور-کار-میکند)
- [پیش‌نیازها](#پیشنیازها)
- [نصب](#نصب)
- [شروع سریع](#شروع-سریع)
- [پیکربندی](#پیکربندی)
- [تنظیمات Pool](#تنظیمات-pool)
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
| انتخاب جفت | ثابت | وزن‌دار تصادفی (loss کمتر = احتمال بیشتر) |
| جایگزینی بدون قطعی | ندارد | draining: اتصال‌های زنده تمام می‌شوند، جفت‌های ضعیف جایگزین می‌شوند |
| دستور اجرا | `snispf` | `snispf` **و** `snispf-hj` |
| کلیدهای کانفیگ | `CONNECT_IP`، `FAKE_SNI` | `CONNECT_IPS` (لیست)، `FAKE_SNIS` (لیست) |
| ماژول pool | ندارد | `sni_spoofing/pool.py` |

تمام قابلیت‌های اصلی (fragmentation، fake-SNI، combined، domain checker،
raw injection، TTL trick) کاملاً حفظ شده‌اند.

---

## چطور کار می‌کند؟

وقتی یک سایت HTTPS باز می‌کنی، دستگاهت یک **TLS ClientHello** می‌فرستد که
نام سایت به‌صورت متن خام داخل آن است — این **SNI** (Server Name Indication)
نام دارد. سامانهٔ فیلترینگ (DPI) همین نام را می‌بیند و تصمیم می‌گیرد.

SNISPF-HJ بین برنامه‌ات و اینترنت می‌نشیند و آن «سلام» را یا
**قطعه‌قطعه می‌کند** یا **یک سلام جعلی** قبل از آن می‌فرستد. سرور مقصد
همچنان درخواست صحیح را دریافت می‌کند.

```
┌──────────┐     ┌──────────────┐     ┌──────────┐     ┌──────────────┐
│  برنامه  ├────>│  SNISPF-HJ   ├────>│  DPI /   ├────>│ سرور واقعی   │
│ (مرورگر، │     │ (پروکسی محلی)│     │ فایروال  │     │ (Cloudflare) │
│   v2ray، │     │              │     │          │     │              │
│   ...)   │     │ بهترین جفت   │     │ SNI جعلی │     └──────────────┘
└──────────┘     │ از pool انتخاب│     │ یا تکه‌تکه│
                 └──────────────┘     └──────────┘
```

### Pool اتصال

در هنگام راه‌اندازی، یک نمونهٔ تصادفی از جفت‌های `(IP، SNI)` با تست‌های TCP
connect بررسی می‌شود. جفت‌هایی که پاسخ خوب می‌دهند وارد **pool فعال**
می‌شوند. یک thread پس‌زمینه هر ~۳۰ ثانیه pool را دوباره بررسی می‌کند و
جفت‌هایی که نرخ از دست دادن بسته‌هایشان از حد مجاز بیشتر شده را بیرون
می‌کند و با جایگزین سالم‌تر عوض می‌کند. هر اتصال جدید با
**انتخاب وزن‌دار تصادفی** یک جفت دریافت می‌کند — loss کمتر = احتمال انتخاب
بیشتر.

```
CONNECT_IPS  ×  FAKE_SNIS  →  N × M ترکیب
        ↓ probe (TCP connect) ↓
   [stable]  [weak]  [dead]
        ↓
  Pool فعال  (ACTIVE_SLOTS بهترین جفت)
        ↓  انتخاب وزن‌دار برای هر اتصال
  اتصال تو  →  upstream
```

---

## پیش‌نیازها

- **Python 3.8** یا بالاتر (`python3 --version`)
- بدون وابستگی خارجی، بدون کامپایلر C، بدون ماژول هسته.

---

## نصب

### روش ۱ — نصب با pip (توصیه‌شده)

```bash
git clone https://github.com/hjfisher/SNI-Spoofing-HJ.git
cd SNI-Spoofing-HJ
pip install .
snispf-hj --info
```

یا تک‌خطی بدون کلون:

```bash
pip install git+https://github.com/hjfisher/SNI-Spoofing-HJ.git
```

> **اندروید / Termux:** اگر pip خطای سیستمی داد:
> ```bash
> pip install . --break-system-packages
> ```

> **نکته:** برای جلوگیری از به‌هم‌ریختن Python سیستم از محیط مجازی استفاده کن:
> ```bash
> python3 -m venv .venv && source .venv/bin/activate
> ```

### روش ۲ — اجرا از سورس (بدون نصب)

```bash
git clone https://github.com/hjfisher/SNI-Spoofing-HJ.git
cd SNI-Spoofing-HJ
python3 run.py --info
```

---

## شروع سریع

### ۱. اجرای پروکسی

```bash
# با config.json پیش‌فرض (توصیه‌شده — شامل ۱۱ IP × ۳۸ SNI)
snispf-hj --config config.json

# یا با CLI، بدون pool (تک‌جفت):
snispf-hj \
    --listen 0.0.0.0:40443 \
    --connect 172.66.41.252:443 \
    --sni github.com \
    --method fragment
```

باید چنین خروجی‌ای ببینی:

```
Connection pool active — 418 pair(s), 3 active slot(s)
Upstream selection: POOL (multi-IP / multi-SNI)
Bypass strategy: combined
Listening on 0.0.0.0:40443
Ready! Configure your application to use:
  Address: 127.0.0.1:40443
```

### ۲. برنامه را وصل کن

در هر کلاینتی که استفاده می‌کنی (`v2ray`، `xray`، افزونهٔ پروکسی مرورگر، ...)
به‌جای آی‌پی Cloudflare واقعی، آدرس **`127.0.0.1:40443`** را تنظیم کن.

---

## پیکربندی

پرچم‌های CLI همیشه مقادیر فایل کانفیگ را override می‌کنند.

```jsonc
{
  "LISTEN_HOST": "0.0.0.0",
  "LISTEN_PORT": 40443,
  "CONNECT_PORT": 443,
  "BYPASS_METHOD": "combined",       // fragment | fake_sni | combined
  "FRAGMENT_STRATEGY": "sni_split",  // sni_split | half | multi | tls_record_frag
  "FRAGMENT_DELAY": 0.1,
  "USE_TTL_TRICK": false,
  "FAKE_SNI_METHOD": "prefix_fake",

  // ── تنظیمات Pool ────────────────────────────────────────────────────
  // حاصل‌ضرب دکارتی CONNECT_IPS × FAKE_SNIS به‌عنوان ترکیب‌ها پروب می‌شود.
  // برای حالت تک‌جفت (بدون pool)، هر لیست را به یک عنصر محدود کن.

  "ACTIVE_SLOTS": 3,                 // تعداد جفت‌های همزمان فعال
  "HEALTH_CHECK_INTERVAL": 30,       // ثانیه بین هر دور بررسی
  "HEALTH_CHECK_TIMEOUT": 3,         // تایم‌اوت TCP probe (ثانیه)
  "PROBE_COUNT": 5,                  // تعداد probe در هر دور برای هر جفت
  "LOSS_THRESHOLD": 0.20,            // نرخ loss بالاتر از این → drain
  "DEAD_THRESHOLD": 0.80,            // نرخ loss بالاتر از این → dead

  "CONNECT_IPS": [
    "172.66.41.252",
    "108.162.196.145"
    // ... IP‌های بیشتر اضافه کن
  ],

  "FAKE_SNIS": [
    "github.com",
    "google.com",
    "microsoft.com"
    // ... SNI‌های بیشتر اضافه کن
  ]
}
```

---

## تنظیمات Pool

| کلید | پیش‌فرض | توضیح |
|---|---|---|
| `CONNECT_IPS` | `[]` | لیست آی‌پی‌های upstream برای پروب |
| `FAKE_SNIS` | `[]` | لیست نام‌های میزبان جعلی برای پروب |
| `ACTIVE_SLOTS` | `3` | تعداد جفت‌های همزمان فعال |
| `HEALTH_CHECK_INTERVAL` | `30` | ثانیه بین دورهای بررسی |
| `HEALTH_CHECK_TIMEOUT` | `3` | تایم‌اوت TCP connect هر probe |
| `PROBE_COUNT` | `5` | تعداد probe در هر دور |
| `LOSS_THRESHOLD` | `0.20` | نرخ loss (۰–۱) برای drain کردن جفت |
| `DEAD_THRESHOLD` | `0.80` | نرخ loss برای مرده اعلام کردن جفت |

**حالت تک‌جفت:** اگر هر دو لیست فقط یک عنصر داشته باشند (یا از کلیدهای
قدیمی `CONNECT_IP` / `FAKE_SNI` استفاده کنی)، pool غیرفعال می‌شود و ابزار
در همان حالت مستقیم اصلی کار می‌کند — بدون سربار، بدون thread پس‌زمینه.

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
--ttl-trick               فعال‌سازی ترفند IP TTL برای پکت‌های جعلی
--no-raw                  غیرفعال‌سازی raw socket حتی اگر در دسترس باشد
--check-domains FILE      بررسی گروهی لیست دامنه‌ها برای Cloudflare
--check-workers N         تعداد ورکر موازی (پیش‌فرض: ۵۰)
--check-timeout SEC       تایم‌اوت هر دامنه (پیش‌فرض: ۳ ثانیه)
--output FILE             ذخیرهٔ دامنه‌های تأییدشده در فایل
--check-http              تأیید HTTP هم در حین بررسی دامنه
--verbose, -v             لاگ کامل (debug)
--quiet,   -q             فقط هشدارها
--version, -V             نمایش نسخه و خروج
--info                    نمایش قابلیت‌های سیستم و خروج
```

---

## روش‌های دور زدن

### `fragment` — کار می‌کند روی همه جا

TLS ClientHello را در مرز SNI به چند بخش TCP می‌شکند. DPI فقط بخش‌هایی
از نام میزبان را می‌بیند و نمی‌تواند تصمیم بگیرد.
**بدون نیاز به دسترسی خاص روی هر پلتفرمی.**

```bash
snispf-hj --method fragment --config config.json
snispf-hj --method fragment --fragment-strategy sni_split
```

### `fake_sni`

اول یک یا چند ClientHello جعلی می‌فرستد، بعد نسخهٔ واقعی. DPI به اولین
پکت (جعلی) قضاوت می‌کند. روی Linux + root با ترفند `seq_id` مؤثرتر است.
در غیر این صورت به‌طور خودکار به TTL trick سوئیچ می‌کند.

### `combined` — توصیه‌شده

ترکیب همزمان fragmentation و fake_sni. بهترین انتخاب وقتی فیلتر تهاجمی است.

```bash
snispf-hj --method combined --config config.json
```

---

## استراتژی‌های قطعه‌بندی

| استراتژی | کار |
|---|---|
| `sni_split` (پیش‌فرض) | شکستن دقیقاً روی هاست‌نیم SNI داخل ClientHello |
| `half` | دو نیمهٔ تقریباً مساوی |
| `multi` | چند قطعهٔ کوچک ۵ تا ۱۰ بایتی |
| `tls_record_frag` | شکستن در لایهٔ رکورد TLS به‌جای لایهٔ TCP |

---

## بررسی‌گر دامنه

ابزار بررسی گروهی فهرستی از دامنه‌ها می‌گیرد و می‌گوید کدام‌یک پشت
Cloudflare هستند — مفید برای ساختن لیست `FAKE_SNIS`.

```bash
# domains.txt: هر خط یک دامنه
snispf-hj --check-domains domains.txt
snispf-hj --check-domains domains.txt --output verified.txt
snispf-hj --check-domains domains.txt --check-http -v
```

---

## پشتیبانی از پلتفرم‌ها

| پلتفرم | وضعیت | یادداشت |
|---|---|---|
| Linux (هر توزیع) | ✅ کامل | raw socket با `sudo` یا `CAP_NET_RAW` |
| macOS (Apple Silicon / Intel) | ✅ کامل | TTL trick خودکار (raw socket نیاز به root دارد) |
| Windows 10 / 11 | ✅ کامل | fragment/combined؛ بدون raw socket |
| Android روی Termux | ✅ پشتیبانی | بدون root؛ fragment/combined + TTL trick خودکار |
| OpenBSD / FreeBSD | ⚡ best-effort | fragment کار می‌کند؛ raw injection تست نشده |

برای دیدن قابلیت‌های دقیق سیستمت: `snispf-hj --info`

---

## رفع اشکال

**پورت اشغال است**
```bash
snispf-hj --listen :40444 --config config.json
```

**Permission denied روی پورت کمتر از ۱۰۲۴**
از پورت ≥ 1024 استفاده کن یا با `sudo` اجرا کن.

**Pool همهٔ جفت‌ها را dead نشان می‌دهد**
- مطمئن شو `CONNECT_IPS` روی پورت ۴۴۳ در دسترس هستند.
- `HEALTH_CHECK_TIMEOUT` را بیشتر کن: `"HEALTH_CHECK_TIMEOUT": 6`
- `DEAD_THRESHOLD` را بالاتر ببر: `0.90`

**روی بعضی سایت‌ها کار نمی‌کند**
- `--method combined --fragment-strategy multi` را امتحان کن.
- IP و SNI بیشتری به `CONNECT_IPS` / `FAKE_SNIS` اضافه کن.
- `FRAGMENT_DELAY` را افزایش بده: `--fragment-delay 0.25`
- با `--check-domains` تأیید کن SNI‌هایت واقعاً پشت Cloudflare هستند.

**اندروید / Termux: خطای pip**
```bash
pip install . --break-system-packages
```

---

## ساختار پروژه

```
SNISPF/
├── run.py                        # نقطهٔ ورود (python3 run.py …)
├── config.json                   # کانفیگ پیش‌فرض (چند-IP / چند-SNI)
├── pyproject.toml                # متادیتا — snispf و snispf-hj
├── README.md / README_FA.md      # مستندات (انگلیسی + فارسی)
├── LICENSE                       # MIT
└── sni_spoofing/
    ├── __init__.py               # init پکیج، __version__
    ├── cli.py                    # argparse + نقطهٔ ورود اصلی
    ├── forwarder.py              # فوروردر async TCP + یکپارچه‌سازی pool
    ├── pool.py                   # ★ جدید: PairStats، CombinationExplorer،
    │                             #          ActivePool، ConnectionManager
    ├── bypass/                   # استراتژی‌های fragment / fake-SNI / raw
    ├── tls/                      # ساخت و تجزیهٔ ClientHello
    ├── scanner/                  # بررسی گروهی دامنه‌های Cloudflare
    └── utils/                    # تشخیص پلتفرم، کمک‌های IP/port
```

---

## تشکر و منابع

- **[@Rainman69](https://github.com/Rainman69)** — معماری اصلی SNISPF،
  موتور fragmentation، پشتیبانی cross-platform، و CLI.
- **[@patterniha](https://github.com/patterniha)** — ایدهٔ اولیهٔ SNI spoofing
  و explorer ترکیب چند-IP/چند-SNI.
- **[@hjfisher](https://github.com/hjfisher)** — `CombinationExplorer`،
  `ActivePool`، `ConnectionManager`، و یکپارچه‌سازی pool با forwarder SNISPF.

---

## لایسنس

[MIT](LICENSE) © Rainman69, hjfisher
