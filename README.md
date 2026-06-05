# SNISPF-HJ

### Cross-Platform DPI Bypass Tool with Adaptive Multi-IP/SNI Pool

```
 ____  _      _  ____  ____  _____       _        _ 
/ ___\/ \  /|/ \/ ___\/  __\/    /      / \ /|   / |
|    \| |\ ||| ||    \|  \/||  __\_____ | |_||   | |
\___ || | \||| |\___ ||  __/| |   \____\| | ||/\_| |
\____/\_/  \|\_/\____/\_/   \_/         \_/ \|\____/
                                                    
```

**[FA README | توضیحات فارسی](README_FA.md)**

**SNISPF-HJ** is a fork of [SNISPF](https://github.com/Rainman69/SNISPF) by
[@Rainman69](https://github.com/Rainman69), extended with an **adaptive
multi-IP / multi-SNI connection pool** and **dynamic Cloudflare IP discovery**,
ported from ideas by [@patterniha](https://github.com/patterniha) and
[@hjfisher](https://github.com/hjfisher).

Runs on **Windows, macOS, Linux, and Android (Termux)** — no root required for
the default bypass method.

Any idea? → **[SNISPF/discussions](https://github.com/Rainman69/SNISPF/discussions)**

‎**⭐️ Don't forget to star ⭐️**

---

## Table of Contents

- [What's New in this Fork](#whats-new-in-this-fork)
- [How Does It Work?](#how-does-it-work)
- [Requirements](#requirements)
- [Installation](#installation)
- [Building a Standalone Executable](#building-a-standalone-executable)
- [Quick Start](#quick-start)
- [Configuration](#configuration)
- [Pool Settings](#pool-settings)
- [Dynamic IP Discovery](#dynamic-ip-discovery)
- [CLI Flags](#cli-flags)
- [Bypass Methods](#bypass-methods)
- [Fragment Strategies](#fragment-strategies)
- [Domain Checker](#domain-checker)
- [Platform Support](#platform-support)
- [Troubleshooting](#troubleshooting)
- [Project Structure](#project-structure)
- [Credits](#credits)
- [License](#license)

---

## What's New in this Fork

| Feature | Original SNISPF | SNISPF-HJ |
|---|---|---|
| Upstream targets | Single IP + single SNI | Multiple IPs × multiple SNIs |
| Health checking | None | Continuous TCP probe loop |
| Pair selection | Static | Weighted-random (lower loss = higher chance) |
| Graceful rotation | No | Draining: live connections finish, weak pairs replaced |
| Dynamic IP discovery | No | Scans Cloudflare CIDR ranges at runtime |
| Entry point | `snispf` | `snispf` **and** `snispf-hj` |
| Config keys | `CONNECT_IP`, `FAKE_SNI` | `CONNECT_IPS` (list), `FAKE_SNIS` (list) |
| New modules | — | `pool.py`, `ip_discovery.py` |

All original features (fragmentation, fake-SNI, combined, domain checker, raw
injection, TTL trick) are fully preserved.

---

## How Does It Work?

When you open an HTTPS site, your device sends a **TLS ClientHello** containing
the target hostname in plain text — the **SNI** (Server Name Indication). DPI
firewalls read that name and decide whether to block you.

SNISPF-HJ sits between your app and the internet, intercepting that hello and
either **fragmenting it** or **sending a decoy** so the censor cannot read the
real hostname.

```
┌──────────┐     ┌──────────────────┐     ┌──────────┐     ┌──────────────┐
│ Your App ├────>│   SNISPF-HJ      ├────>│  DPI /   ├────>│ Real Server  │
│          │     │  (local proxy)   │     │ Firewall │     │ (Cloudflare) │
│          │     │                  │     │          │     │              │
│          │     │ ① pool picks     │     │ sees fake│     │              │
│          │     │   best (IP, SNI) │     │ or split │     │              │
│          │     │ ② discovery adds │     │   SNI    │     │              │
│          │     │   fresh IPs live │     │          │     │              │
└──────────┘     └──────────────────┘     └──────────┘     └──────────────┘
```

### The Connection Pool

On startup the tool probes a random sample of `(IP, SNI)` pairs. Pairs that
respond well enter the **active pool**. A background thread re-checks the pool
every ~30 seconds and rotates out degraded pairs. Each new connection is
assigned a pair using **weighted-random selection** (lower loss = higher
probability).

### Dynamic IP Discovery

A second background thread continuously samples random IPs from Cloudflare's
official CIDR ranges (e.g. `104.16.0.0/13`, `172.64.0.0/13`, …), probes them
with TCP connects, and injects the healthy ones into the pool — all while the
proxy is serving connections. This means the pool grows stronger over time
without any manual IP hunting.

```
15 Cloudflare CIDRs  →  sample 100 random IPs  →  TCP probe (parallel)
        ↓ accepted (≥50% success)
  inject as new (IP × SNI) pairs into explorer
        ↓ pool.refresh()
  active pool picks up the best new pairs immediately
```

---

## Requirements

- **Python 3.8** or newer
- No external dependencies for normal use

---

## Installation

### Option 1 — pip (recommended)

```bash
git clone https://github.com/hjfisher/SNI-Spoofing-HJ.git
cd SNI-Spoofing-HJ
pip install .
snispf-hj --info
```

Or without cloning:

```bash
pip install git+https://github.com/hjfisher/SNI-Spoofing-HJ.git
```

> **Android / Termux:**
> ```bash
> pip install . --break-system-packages
> ```

### Option 2 — Run from source

```bash
git clone https://github.com/hjfisher/SNI-Spoofing-HJ.git
cd SNI-Spoofing-HJ
python3 run.py --info
```

---

## Building a Standalone Executable

You can package SNISPF-HJ into a **single executable file** (`.exe` on
Windows, a plain binary on Linux/macOS) using
[PyInstaller](https://pyinstaller.org).  The resulting file can be copied to
any machine and run without Python installed.

> **Important:** PyInstaller always builds for the OS it runs on.  To get a
> `.exe` you must run the build on Windows.  To get a Linux binary, build on
> Linux.  Cross-compilation is not supported.

### Step 1 — Install PyInstaller

```bash
pip install pyinstaller
# If the above doesn't work on Windows PowerShell:
python -m pip install pyinstaller
```

### Step 2 — Build

```bash
# From inside the project folder:
cd SNI-Spoofing-HJ

# Single-file executable (recommended)
python -m PyInstaller --onefile --name snispf-hj run.py

# Also bundle config.json into the executable
# Windows:
python -m PyInstaller --onefile --name snispf-hj --add-data "config.json;." run.py
# Linux / macOS:
python -m PyInstaller --onefile --name snispf-hj --add-data "config.json:." run.py
```

The output will be in the `dist/` folder:

```
dist/
├── snispf-hj.exe       ← Windows
└── snispf-hj           ← Linux / macOS
```

### Step 3 — Run

```bash
# Windows
dist\snispf-hj.exe --config config.json

# Linux / macOS
chmod +x dist/snispf-hj
./dist/snispf-hj --config config.json
```

### Notes

- If `config.json` was **not** bundled into the exe, place it next to the
  executable before running.
- The `--onefile` flag produces one portable file but makes startup slightly
  slower (it extracts itself to a temp dir on first run).  Omit it for faster
  startup at the cost of a `dist/snispf-hj/` folder instead of a single file.
- On Windows, antivirus software sometimes flags PyInstaller executables as
  suspicious.  This is a known false positive — the source code is fully open.

---

## Quick Start

```bash
# With bundled config (multi-IP / multi-SNI pool + dynamic discovery)
snispf-hj --config config.json

# Single-pair mode (no pool)
snispf-hj --listen 0.0.0.0:40443 --connect 172.66.41.252:443 --sni github.com --method fragment
```

Expected output:

```
Connection pool active — 418 pair(s), 3 active slot(s)
Dynamic IP discovery active — batch=100  interval=120s
Upstream selection: POOL (multi-IP / multi-SNI)
Bypass strategy: combined
Listening on 0.0.0.0:40443
Ready! Configure your application to use:
  Address: 127.0.0.1:40443
```

Point your client (`v2ray`, `xray`, browser proxy plugin, …) at
**`127.0.0.1:40443`**.

---

## Configuration

CLI flags override config file values.

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

  // ── Static pool ────────────────────────────────────────────────────
  "ACTIVE_SLOTS": 3,
  "HEALTH_CHECK_INTERVAL": 30,
  "HEALTH_CHECK_TIMEOUT": 3,
  "PROBE_COUNT": 5,
  "LOSS_THRESHOLD": 0.20,
  "DEAD_THRESHOLD": 0.80,

  "CONNECT_IPS": [
    "172.66.41.252",
    "108.162.196.145"
    // ...
  ],
  "FAKE_SNIS": [
    "github.com",
    "google.com"
    // ...
  ],

  // ── Dynamic IP discovery ───────────────────────────────────────────
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

## Pool Settings

| Key | Default | Description |
|---|---|---|
| `CONNECT_IPS` | `[]` | Static upstream IP list |
| `FAKE_SNIS` | `[]` | Fake SNI hostname list |
| `ACTIVE_SLOTS` | `3` | Pairs kept active simultaneously |
| `HEALTH_CHECK_INTERVAL` | `30` | Seconds between re-probe cycles |
| `HEALTH_CHECK_TIMEOUT` | `3` | TCP connect timeout per probe (s) |
| `PROBE_COUNT` | `5` | TCP probes per pair per cycle |
| `LOSS_THRESHOLD` | `0.20` | Loss rate above which a pair is drained |
| `DEAD_THRESHOLD` | `0.80` | Loss rate above which a pair is marked dead |

**Single-pair mode:** if both lists have exactly one entry (or legacy
`CONNECT_IP` / `FAKE_SNI` keys are used), the pool is disabled and the tool
runs in direct mode with no overhead.

---

## Dynamic IP Discovery

| Key | Default | Description |
|---|---|---|
| `DYNAMIC_IP_DISCOVERY` | `false` | Enable discovery (set `true` to activate) |
| `DISCOVERY_BATCH` | `100` | Random IPs sampled per round |
| `DISCOVERY_INTERVAL` | `120` | Seconds between scan rounds |
| `DISCOVERY_PROBE_TRIES` | `3` | TCP connect attempts per candidate |
| `DISCOVERY_TIMEOUT` | `2.0` | TCP connect timeout per attempt (s) |
| `DISCOVERY_MIN_SUCCESS` | `0.50` | Minimum success rate to accept an IP (0–1) |
| `DISCOVERY_MAX_IPS` | `200` | Cap on dynamically discovered IPs |

Discovery samples from Cloudflare's official IP ranges and only accepts IPs
that pass the TCP probe threshold.  All logic runs in a daemon thread and never
interrupts live connections.  The first scan starts 15 seconds after launch to
let the pool bootstrap first.

---

## CLI Flags

```
--config, -C FILE         Path to JSON config file
--generate-config PATH    Write a default config and exit
--listen, -l HOST:PORT    Listen address (default: 0.0.0.0:40443)
--connect, -c IP:PORT     Target server (single-pair mode)
--sni,    -s HOSTNAME     Fake SNI hostname (single-pair mode)
--method, -m METHOD       fragment | fake_sni | combined
--fragment-strategy STR   sni_split | half | multi | tls_record_frag
--fragment-delay  SEC     Delay between fragments (seconds)
--ttl-trick               Enable IP TTL trick for decoy packets
--no-raw                  Disable raw socket injection
--check-domains FILE      Bulk-check domains for Cloudflare backing
--check-workers N         Parallel workers (default: 50)
--check-timeout SEC       Per-domain timeout (default: 3.0)
--output FILE             Save verified domains to file
--check-http              Also verify HTTP during domain check
--verbose, -v             Debug logging
--quiet,   -q             Warnings only
--version, -V             Print version and exit
--info                    Show platform capabilities and exit
```

---

## Bypass Methods

| Method | How it works | Privileges needed |
|---|---|---|
| `fragment` | Splits ClientHello at the SNI boundary into multiple TCP segments | None |
| `fake_sni` | Sends decoy ClientHello(s) before the real one | Root for raw sockets; falls back to TTL trick |
| `combined` | Both simultaneously — recommended | Same as `fake_sni` |

---

## Fragment Strategies

| Strategy | Description |
|---|---|
| `sni_split` (default) | Split exactly at the SNI hostname boundary |
| `half` | Two roughly equal halves |
| `multi` | Many 5–10 byte fragments |
| `tls_record_frag` | Split at the TLS record layer |

---

## Domain Checker

```bash
snispf-hj --check-domains domains.txt
snispf-hj --check-domains domains.txt --output verified.txt --check-http -v
```

Outputs which domains are Cloudflare-backed — useful for building `FAKE_SNIS`.

---

## Platform Support

| Platform | Status | Notes |
|---|---|---|
| Linux | ✅ Full | Raw injection with `sudo` / `CAP_NET_RAW` |
| macOS | ✅ Full | TTL trick auto-enabled |
| Windows 10 / 11 | ✅ Full | Fragment/combined; no raw sockets |
| Android (Termux) | ✅ Supported | No root needed; TTL trick auto-on |
| OpenBSD / FreeBSD | ⚡ Best-effort | Fragment works; raw injection untested |

Run `snispf-hj --info` to see what your system supports.

---

## Troubleshooting

**Port already in use**
```bash
snispf-hj --listen :40444 --config config.json
```

**`pyinstaller` not recognized on Windows PowerShell**
```powershell
python -m pip install pyinstaller
python -m PyInstaller --onefile --name snispf-hj run.py
```

**Pool shows all pairs as dead**
- Check that `CONNECT_IPS` are reachable on port 443.
- Raise `HEALTH_CHECK_TIMEOUT` to `6`.
- Raise `DEAD_THRESHOLD` to `0.90`.

**Discovery finds nothing**
- Your network may block outbound probes — try `DISCOVERY_TIMEOUT: 4.0`.
- Set `DISCOVERY_MIN_SUCCESS: 0.34` for a looser threshold.

**Bypass doesn't work for some sites**
- Try `--method combined --fragment-strategy multi`.
- Add more entries to `CONNECT_IPS` / `FAKE_SNIS`.
- Increase `FRAGMENT_DELAY` (e.g. `0.25`).
- Run `--check-domains` to verify your SNIs are Cloudflare-backed.

**Android / Termux: pip error**
```bash
pip install . --break-system-packages
```

---

## Project Structure

```
SNISPF/
├── run.py                        # Entry point (python3 run.py …)
├── config.json                   # Default config
├── pyproject.toml                # Package — exports snispf + snispf-hj
├── README.md / README_FA.md
├── LICENSE
└── sni_spoofing/
    ├── cli.py                    # argparse + main entry point
    ├── forwarder.py              # Async TCP forwarder + pool integration
    ├── pool.py                   # PairStats, CombinationExplorer,
    │                             # ActivePool, ConnectionManager
    ├── ip_discovery.py           # ★ Dynamic Cloudflare IP scanner
    ├── bypass/                   # Fragment / fake-SNI / raw-injection
    ├── tls/                      # ClientHello builder + parser
    ├── scanner/                  # Bulk Cloudflare domain checker
    └── utils/                    # Platform detection, IP/port helpers
```

---

## Credits

- **[@Rainman69](https://github.com/Rainman69)** — original SNISPF architecture,
  fragmentation engine, cross-platform support, and CLI.
- **[@patterniha](https://github.com/patterniha)** — original SNI-spoofing concept
  and the multi-IP/SNI combination explorer idea.
- **[@hjfisher](https://github.com/hjfisher)** — `CombinationExplorer`,
  `ActivePool`, `ConnectionManager`, `IPDiscovery`, and pool integration.
- **[@bia-pain-bache](https://github.com/bia-pain-bache)** and
  **[@Ptechgithub](https://github.com/Ptechgithub)** — Cloudflare IP scanning
  methodology that inspired `ip_discovery.py`.

---

## License

[MIT](LICENSE) © Rainman69, hjfisher
