# SNISPF-HJ

### Cross-Platform DPI Bypass Tool with Adaptive Multi-IP/SNI Pool

```
  _____ ____   ____ _____ ____  _____        __ __  ____ 
 / ___/|    \ |    / ___/|    \|     |      |  |  ||    |
(   \_ |  _  | |  (   \_ |  o  )   __|_____ |  |  ||__  |
 \__  ||  |  | |  |\__  ||   _/|  |_ |     ||  _  |__|  |
 /  \ ||  |  | |  |/  \ ||  |  |   _]|_____||  |  /  |  |
 \    ||  |  | |  |\    ||  |  |  |         |  |  \  `  |
  \___||__|__||____|\___||__|  |__|         |__|__|\____j
```

**[FA README | توضیحات فارسی](README_FA.md)**

**SNISPF-HJ** is a fork of [SNISPF](https://github.com/Rainman69/SNISPF) by
[@Rainman69](https://github.com/Rainman69), extended with a **self-healing
multi-IP / multi-SNI connection pool** and **dynamic Cloudflare IP
discovery**, built on ideas from [@patterniha](https://github.com/patterniha),
[@hjfisher](https://github.com/hjfisher), and
[@bia-pain-bache](https://github.com/bia-pain-bache).

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
- [Building Your Config Visually](#building-your-config-visually)
- [Configuration](#configuration)
- [Pool Settings](#pool-settings)
- [Scoring: How a Pair's Health Is Measured](#scoring-how-a-pairs-health-is-measured)
- [IP Eviction, Quarantine & Recycling](#ip-eviction-quarantine--recycling)
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
| Health checking | None | Real TLS handshake probes (not just TCP) |
| Pair selection | Static | Weighted-random, score = loss + latency |
| Loss tracking | — | Exponential moving average (self-recovering) |
| Graceful rotation | No | Draining with configurable timeout |
| Forced drain close | No | Connections closed after `DRAIN_TIMEOUT` seconds |
| IP eviction | No | Weakest IPs periodically quarantined |
| IP recycling | No | Quarantined IPs re-tested and restored if healthy |
| Eviction/recycle scope | — | Choose static-only, dynamic-only, or both |
| Dynamic IP discovery | No | Scans Cloudflare CIDR ranges at runtime |
| Visual config builder | No | Built-in browser UI (`--config-ui`) |
| Entry point | `snispf` | `snispf` **and** `snispf-hj` |
| Config keys | `CONNECT_IP`, `FAKE_SNI` | `CONNECT_IPS` (list), `FAKE_SNIS` (list) |
| New modules | — | `pool.py`, `ip_discovery.py`, `config_server.py` |

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

On startup the tool probes a random sample of `(IP, SNI)` pairs with a real
**TLS handshake** (not just a TCP connect — a server can accept TCP but still
reject or drop TLS traffic, so a true handshake is the only reliable test).
Pairs that respond well enter the **active pool**. A background thread
re-checks the pool every ~30 seconds and rotates out degraded pairs. Each new
connection is assigned a pair using **weighted-random selection** — lower
score means higher probability of being picked.

### Self-Healing Loss Tracking

Loss is tracked as an **exponential moving average (EMA)**, not a lifetime
counter. This means a pair that performed badly for a while and has since
recovered will see its score improve as fresh good results arrive — old
failures fade out instead of permanently dragging the pair down. See
[Scoring](#scoring-how-a-pairs-health-is-measured) for the exact formula.

### Draining with Timeout

When a pair degrades it enters **draining** mode: no new connections are
assigned to it, but existing ones keep running. After `DRAIN_TIMEOUT` seconds
(default: 30) any remaining connections on that pair are forcefully closed so
the pair can be fully retired. A cap of `MAX_DRAINING` pairs prevents the
draining list from growing out of control.

### IP Eviction → Quarantine → Recycling

Weak IPs aren't deleted forever — they're **quarantined** and periodically
re-tested. If an IP genuinely recovers, it's welcomed back with a clean slate.
See [IP Eviction, Quarantine & Recycling](#ip-eviction-quarantine--recycling).

### Dynamic IP Discovery

A second background thread continuously samples random IPs from Cloudflare's
official CIDR ranges (e.g. `104.16.0.0/13`, `172.64.0.0/13`, …), probes them
with a real TLS handshake, and injects the healthy ones into the pool — all
while the proxy is serving connections.

```
15 Cloudflare CIDRs  →  sample 100 random IPs  →  TLS handshake probe (parallel)
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
git clone https://github.com/hjfisher/SNISPF-HJ.git
cd SNISPF-HJ
pip install .
snispf-hj --info
```

Or without cloning:

```bash
pip install git+https://github.com/hjfisher/SNISPF-HJ.git
```

> **Android / Termux:**
> ```bash
> pip install . --break-system-packages
> ```

### Option 2 — Run from source

```bash
git clone https://github.com/hjfisher/SNISPF-HJ.git
cd SNISPF-HJ
python3 run.py --info
```

---

## Building a Standalone Executable

You can package SNISPF-HJ into a **single executable file** (`.exe` on
Windows, a plain binary on Linux/macOS) using
[PyInstaller](https://pyinstaller.org). The resulting file runs on any machine
without Python installed.

> **Important:** PyInstaller always builds for the OS it runs on. To get a
> `.exe` build on Windows; for a Linux binary build on Linux.
> Cross-compilation is not supported.

### Step 1 — Install PyInstaller

```bash
pip install pyinstaller
# If not recognized on Windows PowerShell:
python -m pip install pyinstaller
```

### Step 2 — Build

```bash
cd SNISPF-HJ

# Single-file executable (recommended)
python -m PyInstaller --onefile --name snispf-hj run.py

# Bundle config.json inside the executable:
# Windows:
python -m PyInstaller --onefile --name snispf-hj --add-data "config.json;." run.py
# Linux / macOS:
python -m PyInstaller --onefile --name snispf-hj --add-data "config.json:." run.py
```

Output in `dist/`:

```
dist/
├── snispf-hj.exe       ← Windows
└── snispf-hj           ← Linux / macOS
```

### Step 3 — Run

```powershell
# Windows
dist\snispf-hj.exe --config config.json
```
```bash
# Linux / macOS
chmod +x dist/snispf-hj && ./dist/snispf-hj --config config.json
```

**Notes:**
- If `config.json` was not bundled, place it next to the executable.
- `--onefile` is portable but slightly slower on first launch (extracts to a
  temp dir). Omit it for a `dist/snispf-hj/` folder with faster startup.
- Windows antivirus may flag PyInstaller outputs as suspicious — this is a
  known false positive; the source code is fully open.

---

## Quick Start

```bash
# Multi-IP / multi-SNI pool + dynamic discovery
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

## Building Your Config Visually

Editing JSON by hand isn't for everyone. SNISPF-HJ ships with a built-in
**Config Builder UI** that opens directly in your browser — no separate
download, no copy-pasting a link.

```bash
snispf-hj --config-ui

# Custom port
snispf-hj --config-ui --ui-port 8080

# Save directly over your existing config file
snispf-hj --config-ui --config my_config.json
```

This starts a small local server (bound to `127.0.0.1` only — never exposed
to your network) and automatically opens the UI in your default browser. From
there you can:

- Add/remove IPs and SNIs with quick-add buttons (built-in Cloudflare IP list)
- Tune pool, drain, eviction, and discovery parameters with sliders
- Preview the generated `config.json` with syntax highlighting
- Click **"Save to server"** to write the file directly, or **"Download"**
  to save it manually

Press `Ctrl+C` in the terminal to stop the config server when you're done.

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

  // ── Pool ───────────────────────────────────────────────────────────
  "ACTIVE_SLOTS": 3,
  "HEALTH_CHECK_INTERVAL": 30,
  "HEALTH_CHECK_TIMEOUT": 3,
  "PROBE_COUNT": 5,
  "LOSS_THRESHOLD": 0.20,
  "DEAD_THRESHOLD": 0.80,
  "DRAIN_TIMEOUT": 30,
  "MAX_DRAINING": 5,

  // ── Eviction & recycling ───────────────────────────────────────────
  "EVICT_EVERY": 3,
  "EVICT_COUNT": 2,
  "RECYCLE_ENABLED": true,
  "RECYCLE_EVERY": 6,
  "RECYCLE_BATCH": 2,
  "RECYCLE_MIN_COOLDOWN": 180,
  "RECYCLE_MAX_QUARANTINE": 100,
  "QUARANTINE_SCOPE": "both",        // static | dynamic | both

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
| `HEALTH_CHECK_TIMEOUT` | `3` | TLS handshake timeout per probe (s) |
| `PROBE_COUNT` | `5` | TLS probes per pair per cycle |
| `LOSS_THRESHOLD` | `0.20` | Loss score above which a pair is drained |
| `DEAD_THRESHOLD` | `0.80` | Loss score above which a pair is marked dead |
| `DRAIN_TIMEOUT` | `30` | Seconds before a draining pair's connections are force-closed |
| `MAX_DRAINING` | `5` | Max simultaneous draining pairs; oldest is force-closed if exceeded |

**Single-pair mode:** if both `CONNECT_IPS`/`FAKE_SNIS` lists have exactly one
entry (or legacy `CONNECT_IP` / `FAKE_SNI` keys are used), the pool is
disabled and the tool runs in direct mode with no overhead.

---

## Scoring: How a Pair's Health Is Measured

Every `(IP, SNI)` pair is probed with a **real TLS handshake** — a plain TCP
connect isn't enough, since a server can accept the TCP connection and still
refuse or drop the TLS layer. The probe uses the pair's own SNI, so the test
reflects exactly what the forwarder will send in production traffic.

### Loss tracking — exponential moving average

Instead of a lifetime "successes vs failures" counter, each pair keeps an
**EMA (exponential moving average)** of its loss, separately for probe
results and real forwarded traffic:

```
ema_loss_new = α × loss_this_event + (1 − α) × ema_loss_previous
```

- `α` (probe) = `0.25` — probes happen on a fixed schedule, so a moderate
  alpha keeps the score responsive to recent conditions.
- `α` (real traffic) = `0.15` — real connections can arrive in bursts, so a
  smaller alpha prevents one bad burst from dominating the score.

**Why this matters:** a pair that was unhealthy for a while and has since
recovered will see its EMA decay back toward zero as fresh successful results
come in — old failures fade out rather than permanently weighing the pair
down. There's no fixed "memory window" to tune; the recovery curve is smooth
and automatic.

### Composite score

```
score = 0.60 × combined_loss_rate
      + 0.20 × latency_score
      + 0.20 × probe_loss_rate
```

- `combined_loss_rate` blends 70% real-traffic EMA loss + 30% probe EMA loss
  (once at least 10 real packets have been observed; before that, pure probe
  loss is used).
- `latency_score` is the average TLS handshake time, normalised against a
  1500 ms cap — a pair that's loss-free but consistently slow still scores
  worse than a fast one.
- `probe_loss_rate` is included on its own (in addition to being part of
  `combined_loss_rate`) so probe health always has some direct weight even
  once real traffic exists.

Lower score = better. A dead pair scores `+inf` (never selected). A
not-yet-probed pair scores `0.5` so unknowns get a fair first chance instead
of being assumed bad.

---

## IP Eviction, Quarantine & Recycling

Pools don't grow forever, and dead weight shouldn't sit there hurting your
average. Every `EVICT_EVERY` health cycles, the `EVICT_COUNT` IPs with the
worst average score are evicted — but **not deleted**. They move to a
**quarantine** list.

```
Active pool → degraded → EVICT_EVERY cycles → quarantine
                                                    │
                                    RECYCLE_EVERY   │  random sample,
                                    cycles           ▼  re-probed with TLS
                                              ┌─────────────┐
                                              │  healthy?   │
                                              └──────┬──────┘
                                      yes ───────────┤─────────── no
                                       │                          │
                                       ▼                          ▼
                          restored with a fresh,         stays in quarantine
                          zero-history PairStats           until next attempt
                          (back in the active rotation)    (respecting cooldown)
```

Every `RECYCLE_EVERY` cycles, a random batch of quarantined IPs is re-tested
with a real TLS handshake. An IP that passes is restored with a **brand new**
`PairStats` object — no memory of its previous failures — so it's judged
purely on how it performs now. IPs that fail stay quarantined until their next
eligible attempt (governed by `RECYCLE_MIN_COOLDOWN`).

The quarantine list itself is capped at `RECYCLE_MAX_QUARANTINE` entries — the
oldest are permanently dropped if it grows past that, so memory use stays
bounded even over very long runs.

### Choosing which IPs are eligible: `QUARANTINE_SCOPE`

By default, both your hand-picked IPs (`CONNECT_IPS` in the config) and IPs
found by the discovery scanner are eligible for eviction and recycling. You
can narrow this with `QUARANTINE_SCOPE`:

| Value | Behaviour |
|---|---|
| `"both"` (default) | Both static and dynamically-discovered IPs can be evicted/recycled |
| `"static"` | Only IPs you listed in `CONNECT_IPS` are evicted/recycled — discovered IPs are left alone |
| `"dynamic"` | Only IPs found by the discovery scanner are evicted/recycled — your hand-picked list is never touched |

This is useful if, say, you trust your own curated IP list and only want the
churn/recycling behaviour applied to whatever the discovery scanner finds.

| Key | Default | Description |
|---|---|---|
| `EVICT_EVERY` | `3` | Evict weakest IPs every N health cycles |
| `EVICT_COUNT` | `2` | Number of IPs to evict per eviction cycle |
| `RECYCLE_ENABLED` | `true` | Enable/disable the recycling mechanism |
| `RECYCLE_EVERY` | `6` | Attempt recycling every N health cycles |
| `RECYCLE_BATCH` | `2` | How many quarantined IPs to re-test per attempt |
| `RECYCLE_MIN_COOLDOWN` | `180` | Minimum seconds between re-test attempts on the same IP |
| `RECYCLE_MAX_QUARANTINE` | `100` | Cap on quarantine size; oldest entries are dropped permanently beyond this |
| `QUARANTINE_SCOPE` | `"both"` | Which IP origin is eligible: `"static"`, `"dynamic"`, or `"both"` |

**Timing example:** with the defaults (`HEALTH_CHECK_INTERVAL=30`,
`EVICT_EVERY=3`, `EVICT_COUNT=2`) → every 90 seconds the 2 weakest IPs are
quarantined. With `RECYCLE_EVERY=6` → every 180 seconds, 2 random quarantined
IPs get a second chance.

---

## Dynamic IP Discovery

| Key | Default | Description |
|---|---|---|
| `DYNAMIC_IP_DISCOVERY` | `false` | Enable discovery (set `true` to activate) |
| `DISCOVERY_BATCH` | `100` | Random IPs sampled per round |
| `DISCOVERY_INTERVAL` | `120` | Seconds between scan rounds |
| `DISCOVERY_PROBE_TRIES` | `3` | TLS handshake attempts per candidate |
| `DISCOVERY_TIMEOUT` | `2.0` | TLS handshake timeout per attempt (s) |
| `DISCOVERY_MIN_SUCCESS` | `0.50` | Minimum success rate to accept an IP (0–1) |
| `DISCOVERY_MAX_IPS` | `200` | Cap on dynamically discovered IPs |

Discovery samples from Cloudflare's official IP ranges and only accepts IPs
that complete a real TLS handshake at or above the success threshold — a bare
TCP connect isn't enough, since some IPs accept the connection but never
complete TLS. All logic runs in a daemon thread and never interrupts live
connections. The first scan starts 15 seconds after launch to let the pool
bootstrap first.

IPs found this way are tagged with `origin = "dynamic"` internally, which is
what `QUARANTINE_SCOPE` uses to distinguish them from your `CONNECT_IPS`.

---

## CLI Flags

```
--config, -C FILE         Path to JSON config file
--generate-config PATH    Write a default config and exit
--config-ui                Open the built-in Config Builder UI in your browser
--ui-port PORT             Port for the Config Builder UI (default: 40080)
--listen, -l HOST:PORT     Listen address (default: 0.0.0.0:40443)
--connect, -c IP:PORT      Target server (single-pair mode)
--sni,    -s HOSTNAME      Fake SNI hostname (single-pair mode)
--method, -m METHOD        fragment | fake_sni | combined
--fragment-strategy STR    sni_split | half | multi | tls_record_frag
--fragment-delay  SEC      Delay between fragments (seconds)
--ttl-trick                Enable IP TTL trick for decoy packets
--no-raw                   Disable raw socket injection
--check-domains FILE       Bulk-check domains for Cloudflare backing
--check-workers N          Parallel workers (default: 50)
--check-timeout SEC        Per-domain timeout (default: 3.0)
--output FILE              Save verified domains to file
--check-http               Also verify HTTP during domain check
--verbose, -v              Debug logging
--quiet,   -q              Warnings only
--version, -V              Print version and exit
--info                     Show platform capabilities and exit
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
- Check that `CONNECT_IPS` are reachable on port 443 with a real TLS handshake
  (not just TCP — some hosts accept the connection but drop the TLS layer).
- Raise `HEALTH_CHECK_TIMEOUT` to `6`.
- Raise `DEAD_THRESHOLD` to `0.90`.

**Connections getting closed unexpectedly**
- This may be `DRAIN_TIMEOUT` firing. Raise it: `"DRAIN_TIMEOUT": 60`.
- Or reduce `EVICT_COUNT` to `1` to slow down IP rotation.

**A pair that used to work seems permanently stuck as "bad"**
- This shouldn't happen any more — loss is tracked as an EMA, so a pair that
  recovers will see its score improve automatically as fresh successful
  probes/connections come in. If it still looks stuck, check whether it was
  fully evicted; quarantined IPs only get re-tested every `RECYCLE_EVERY`
  cycles (respecting `RECYCLE_MIN_COOLDOWN`), so recovery isn't instant.

**Discovery finds nothing**
- Your network may block outbound probes — try `"DISCOVERY_TIMEOUT": 4.0`.
- Loosen the threshold: `"DISCOVERY_MIN_SUCCESS": 0.34`.

**Want to protect your hand-picked IPs from eviction**
- Set `"QUARANTINE_SCOPE": "dynamic"` — only discovery-found IPs will ever
  be evicted/recycled; your `CONNECT_IPS` list is left untouched.

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
SNISPF-HJ/
├── run.py                        # Entry point (python3 run.py …)
├── config.json                   # Default config
├── pyproject.toml                # Package — exports snispf + snispf-hj
├── README.md / README_FA.md
├── LICENSE
└── sni_spoofing/
    ├── cli.py                    # argparse + main entry point
    ├── forwarder.py              # Async TCP forwarder + pool integration
    ├── pool.py                   # PairStats (EMA, latency, scoring),
    │                             # CombinationExplorer (probing, eviction,
    │                             # quarantine, recycling), ActivePool,
    │                             # ConnectionManager
    ├── ip_discovery.py           # Dynamic Cloudflare IP scanner (TLS probe)
    ├── config_server.py          # ★ Built-in visual Config Builder UI
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
  `ActivePool`, `ConnectionManager`, `IPDiscovery`, EMA-based scoring, drain
  timeout, IP eviction/quarantine/recycling, the visual Config Builder, and
  overall pool integration.
- **[@bia-pain-bache](https://github.com/bia-pain-bache)** and
  **[@Ptechgithub](https://github.com/Ptechgithub)** — Cloudflare IP scanning
  methodology that inspired `ip_discovery.py`.

---

## License

[MIT](LICENSE) © Rainman69, hjfisher
