# SNISPF-HJ

### Cross-Platform DPI Bypass Tool with Adaptive Multi-IP/SNI Pool

```
 ███████╗███╗   ██╗██╗███████╗██████╗ ███████╗
 ██╔════╝████╗  ██║██║██╔════╝██╔══██╗██╔════╝
 ███████╗██╔██╗ ██║██║███████╗██████╔╝█████╗
 ╚════██║██║╚██╗██║██║╚════██║██╔═══╝ ██╔══╝
 ███████║██║ ╚████║██║███████║██║     ██║
 ╚══════╝╚═╝  ╚═══╝╚═╝╚══════╝╚═╝     ╚═╝
```

**[FA README | توضیحات فارسی](README_FA.md)**

**SNISPF-HJ** is a fork of [SNISPF](https://github.com/Rainman69/SNISPF) by
[@Rainman69](https://github.com/Rainman69), extended with an **adaptive
multi-IP / multi-SNI connection pool** ported from ideas by
[@patterniha](https://github.com/patterniha) and
[@hjfisher](https://github.com/hjfisher).

Instead of a single fixed upstream, the tool continuously probes a large list
of (IP, SNI) combinations and automatically routes each connection through the
healthiest pair — replacing degraded upstreams without dropping live sessions.

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
- [Quick Start](#quick-start)
- [Configuration](#configuration)
- [Pool Settings](#pool-settings)
- [CLI Flags](#cli-flags)
- [Bypass Methods](#bypass-methods)
- [Fragment Strategies](#fragment-strategies)
- [Domain Checker](#domain-checker)
- [Platform Support](#platform-support)
- [Troubleshooting](#troubleshooting)
- [Project Structure](#project-structure)
- [Running the Tests](#running-the-tests)
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
| Entry point | `snispf` | `snispf` **and** `snispf-hj` |
| Config keys | `CONNECT_IP`, `FAKE_SNI` | `CONNECT_IPS` (list), `FAKE_SNIS` (list) |
| Pool module | — | `sni_spoofing/pool.py` |

All original features (fragmentation, fake-SNI, combined, domain checker, raw
injection, TTL trick) are fully preserved.

---

## How Does It Work?

When you open an HTTPS site, your device sends a **TLS ClientHello** that
contains the target hostname in plain text — the **SNI** (Server Name
Indication). DPI (Deep Packet Inspection) firewalls read that name and decide
whether to block you.

SNISPF-HJ sits between your app and the internet, intercepting that hello and
either **fragmenting it** or **sending a decoy** so the censor can't read the
real hostname. The destination server still receives the correct request.

```
┌──────────┐     ┌──────────────┐     ┌──────────┐     ┌──────────────┐
│ Your App ├────>│  SNISPF-HJ   ├────>│  DPI /   ├────>│ Real Server  │
│ (browser,│     │ (local proxy)│     │ Firewall │     │ (Cloudflare  │
│  v2ray,  │     │              │     │          │     │  edge node)  │
│  etc.)   │     │  picks best  │     │ sees fake│     │              │
└──────────┘     │  (IP, SNI)   │     │ or split │     └──────────────┘
                 │  from pool   │     │   SNI    │
                 └──────────────┘     └──────────┘
```

### The Connection Pool

On startup the tool probes a random sample of `(IP, SNI)` pairs with plain TCP
connect tests. Pairs that respond well enter the **active pool**. A background
thread re-checks the pool every ~30 seconds and rotates out any pair whose
packet-loss rate exceeds the threshold, replacing it with a healthier
alternative. Each new incoming connection is assigned a pair using
**weighted-random selection** — lower loss rate means higher probability of
being picked.

```
CONNECT_IPS  × FAKE_SNIS  →  N × M combinations
     ↓ probe (TCP connect) ↓
  [stable]  [weak]  [dead]
     ↓
 Active Pool  (ACTIVE_SLOTS best pairs)
     ↓  weighted-random pick per connection
  Your connection → upstream
```

---

## Requirements

- **Python 3.8** or newer (`python3 --version`)
- No external dependencies, no C compilers, no kernel modules.

---

## Installation

### Option 1 — pip install from the repo

```bash
git clone https://github.com/hjfisher/SNI-Spoofing-HJ.git
cd SNI-Spoofing-HJ
pip install .
snispf-hj --info
```

Or in one line without cloning:

```bash
pip install git+https://github.com/hjfisher/SNI-Spoofing-HJ.git
```

> **Android / Termux:** if pip complains about system packages, add the flag:
> ```bash
> pip install . --break-system-packages
> ```

> **Tip:** use a virtual environment (`python3 -m venv .venv && source
> .venv/bin/activate`) to keep the install isolated.

### Option 2 — Run from source (no install)

```bash
git clone https://github.com/hjfisher/SNI-Spoofing-HJ.git
cd SNI-Spoofing-HJ
python3 run.py --info
```

---

## Quick Start

### 1. Start the proxy

```bash
# Use the bundled config.json (recommended — includes 11 IPs × 38 SNIs)
snispf-hj --config config.json

# Or specify everything on the CLI (single-pair, no pool):
snispf-hj \
    --listen 0.0.0.0:40443 \
    --connect 172.66.41.252:443 \
    --sni github.com \
    --method fragment
```

You should see:

```
Connection pool active — 418 pair(s), 3 active slot(s)
Upstream selection: POOL (multi-IP / multi-SNI)
Bypass strategy: combined
Listening on 0.0.0.0:40443
Ready! Configure your application to use:
  Address: 127.0.0.1:40443
```

### 2. Point your app at it

In whatever client you use (`v2ray`, `xray`, browser proxy plugin, …),
set the upstream to **`127.0.0.1:40443`**. Everything else (TLS, routing on
the CDN) is unchanged.

---

## Configuration

CLI flags override config file values. Run with `--config config.json` to use
the bundled file, or pass everything inline.

### Config file reference

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

  // ── Multi-IP / Multi-SNI Pool ───────────────────────────────────────
  // The full cartesian product (CONNECT_IPS × FAKE_SNIS) is probed.
  // Use single-element lists to disable the pool and use direct mode.

  "ACTIVE_SLOTS": 3,                 // How many pairs stay warm in the pool
  "HEALTH_CHECK_INTERVAL": 30,       // Seconds between re-probe cycles
  "HEALTH_CHECK_TIMEOUT": 3,         // TCP connect probe timeout (seconds)
  "PROBE_COUNT": 5,                  // TCP probes per pair per cycle
  "LOSS_THRESHOLD": 0.20,            // Loss rate above which a pair is rotated out
  "DEAD_THRESHOLD": 0.80,            // Loss rate above which a pair is marked dead

  "CONNECT_IPS": [
    "172.66.41.252",
    "108.162.196.145",
    "172.65.13.230"
    // ... add more Cloudflare edge IPs
  ],

  "FAKE_SNIS": [
    "github.com",
    "google.com",
    "microsoft.com"
    // ... add more allowed-domain hostnames
  ]
}
```

---

## Pool Settings

| Key | Default | Description |
|---|---|---|
| `CONNECT_IPS` | `[]` | List of upstream IP addresses to probe |
| `FAKE_SNIS` | `[]` | List of fake SNI hostnames to probe |
| `ACTIVE_SLOTS` | `3` | Number of pairs kept active simultaneously |
| `HEALTH_CHECK_INTERVAL` | `30` | Seconds between full re-probe cycles |
| `HEALTH_CHECK_TIMEOUT` | `3` | TCP connect timeout per probe (seconds) |
| `PROBE_COUNT` | `5` | Number of TCP probes per pair per cycle |
| `LOSS_THRESHOLD` | `0.20` | Loss rate (0–1) above which a pair is drained |
| `DEAD_THRESHOLD` | `0.80` | Loss rate above which a pair is marked dead |

**Single-pair mode:** if `CONNECT_IPS` and `FAKE_SNIS` each contain exactly
one entry (or if the legacy `CONNECT_IP` / `FAKE_SNI` keys are used), the pool
is disabled and the tool runs in the original direct-target mode — no overhead,
no background thread.

---

## CLI Flags

```
--config, -C FILE         Path to JSON config file
--generate-config PATH    Write a default config and exit
--listen, -l HOST:PORT    Listen address (default: 0.0.0.0:40443)
--connect, -c IP:PORT     Target server address (single-pair mode)
--sni,    -s HOSTNAME     Fake SNI hostname (single-pair mode)
--method, -m METHOD       fragment | fake_sni | combined
--fragment-strategy STR   sni_split | half | multi | tls_record_frag
--fragment-delay  SEC     Delay between fragments (seconds)
--ttl-trick               Enable IP TTL trick for decoy packets
--no-raw                  Disable raw socket injection even if available
--check-domains FILE      Bulk-check a domain list for Cloudflare backing
--check-workers N         Parallel workers for domain check (default: 50)
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

### `fragment` (works everywhere)

Cuts the TLS ClientHello into multiple TCP segments at the SNI boundary.
The DPI middlebox only sees partial hostname fragments and cannot make a
blocking decision. **No privileges required on any platform.**

```bash
snispf-hj --method fragment --config config.json
snispf-hj --method fragment --fragment-strategy sni_split
```

### `fake_sni`

Sends one or more decoy ClientHello packets with a fake hostname, then sends
the real one. The DPI locks onto the first (decoy) packet. Most effective with
raw sockets (Linux + root). Without them, falls back automatically to TTL-trick
mode.

### `combined` (recommended)

Both fragmentation and a decoy hello simultaneously. Best choice when the
censor uses aggressive multi-packet reassembly.

```bash
snispf-hj --method combined --config config.json
```

---

## Fragment Strategies

| Strategy | What it does |
|---|---|
| `sni_split` (default) | Splits exactly at the SNI hostname boundary inside the ClientHello |
| `half` | Splits into two roughly equal halves |
| `multi` | Many small fragments of 5–10 bytes each |
| `tls_record_frag` | Splits at the TLS record layer rather than the TCP layer |

---

## Domain Checker

The bundled checker takes a list of hostnames and tells you which are backed by
Cloudflare — useful for building your `FAKE_SNIS` list.

```bash
# domains.txt: one hostname per line
snispf-hj --check-domains domains.txt
snispf-hj --check-domains domains.txt --output verified.txt
snispf-hj --check-domains domains.txt --check-http -v
```

---

## Platform Support

| Platform | Status | Notes |
|---|---|---|
| Linux (any distro) | ✅ Full | Raw socket injection with `sudo` / `CAP_NET_RAW` |
| macOS (Apple Silicon / Intel) | ✅ Full | TTL trick auto-enabled (no raw sockets on Darwin) |
| Windows 10 / 11 | ✅ Full | Fragment/combined methods; no raw sockets |
| Android via Termux | ✅ Supported | Works without root; fragment/combined + TTL trick auto-on |
| OpenBSD / FreeBSD | ⚡ Best-effort | Fragment methods work; raw injection untested |

Run `snispf-hj --info` to see what your system supports.

---

## Troubleshooting

**Port already in use**
```bash
snispf-hj --listen :40444 --config config.json
```

**Permission denied on port < 1024**
Use a port ≥ 1024, or run with `sudo`.

**Pool shows all pairs as dead**
- Check that your `CONNECT_IPS` are reachable on port 443.
- Increase `HEALTH_CHECK_TIMEOUT` (e.g. `"HEALTH_CHECK_TIMEOUT": 6`).
- Lower `DEAD_THRESHOLD` (e.g. `0.90`) to be more forgiving.

**Bypass doesn't work for some sites**
- Try `--method combined --fragment-strategy multi`.
- Add more IPs / SNIs to `CONNECT_IPS` / `FAKE_SNIS` in your config.
- Increase `FRAGMENT_DELAY` (e.g. `--fragment-delay 0.25`).
- Run `--check-domains` to verify your SNIs are Cloudflare-backed.

**Android / Termux: `pip` errors**
```bash
pip install . --break-system-packages
```

---

## Project Structure

```
SNISPF/
├── run.py                        # Entry point (python3 run.py …)
├── config.json                   # Default config (multi-IP / multi-SNI)
├── pyproject.toml                # Package metadata — exports snispf + snispf-hj
├── README.md / README_FA.md      # Docs (English + Farsi)
├── LICENSE                       # MIT
└── sni_spoofing/
    ├── __init__.py               # Package init, __version__
    ├── cli.py                    # argparse + main entry point
    ├── forwarder.py              # Async TCP forwarder + pool integration
    ├── pool.py                   # ★ NEW: PairStats, CombinationExplorer,
    │                             #         ActivePool, ConnectionManager
    ├── bypass/                   # Fragment / fake-SNI / raw-injection strategies
    ├── tls/                      # ClientHello builder + parser
    ├── scanner/                  # Bulk Cloudflare domain checker
    └── utils/                    # Platform detection, IP/port helpers
```

---

## Running the Tests

```bash
cd SNISPF
python3 -m unittest discover -s tests -v
```

---

## Credits

- **[@Rainman69](https://github.com/Rainman69)** — original SNISPF architecture,
  fragmentation engine, cross-platform support, and CLI.
- **[@patterniha](https://github.com/patterniha)** — original SNI-spoofing concept
  and the multi-IP/SNI combination explorer idea.
- **[@hjfisher](https://github.com/hjfisher)** — `CombinationExplorer`,
  `ActivePool`, `ConnectionManager`, and pool integration into SNISPF's forwarder.

---

## License

[MIT](LICENSE) © Rainman69, hjfisher
