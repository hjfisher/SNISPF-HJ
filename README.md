# SNISPF

### Cross-Platform DPI Bypass Tool

```
 ███████╗███╗   ██╗██╗███████╗██████╗ ███████╗
 ██╔════╝████╗  ██║██║██╔════╝██╔══██╗██╔════╝
 ███████╗██╔██╗ ██║██║███████╗██████╔╝█████╗
 ╚════██║██║╚██╗██║██║╚════██║██╔═══╝ ██╔══╝
 ███████║██║ ╚████║██║███████║██║     ██║
 ╚══════╝╚═╝  ╚═══╝╚═╝╚══════╝╚═╝     ╚═╝
```
**[FA README | توضیحات فارسی](https://github.com/Rainman69/SNISPF/blob/main/README_FA.md)**

**SNISPF** is a lightweight command-line tool that helps you get past internet
censorship. It works by reshaping the way your connection introduces itself to
firewalls so that filtered websites slip through undetected. Runs on
**Windows, macOS, and Linux** — no drivers, no admin rights needed for the
default bypass method.

Any idea? → **[SNISPF/discussions](https://github.com/Rainman69/SNISPF/discussions)**

**Maintained by [@Rainman69](https://github.com/Rainman69)**

---

## Table of Contents

- [How Does It Work?](#how-does-it-work)
- [Requirements](#requirements)
- [Installation](#installation)
- [Quick Start](#quick-start)
- [Configuration](#configuration)
- [CLI Flags](#cli-flags)
- [Bypass Methods](#bypass-methods)
- [Fragment Strategies](#fragment-strategies)
- [Domain Checker](#domain-checker)
- [Platform Support](#platform-support)
- [Troubleshooting](#troubleshooting)
- [Project Structure](#project-structure)
- [Running the Tests](#running-the-tests)
- [License](#license)

---

## How Does It Work?

When you visit a website over HTTPS, your device sends a "hello" message (a
**TLS ClientHello**) that contains the website name in plain text. This is the
**SNI** (Server Name Indication). DPI (Deep Packet Inspection) systems read
that name and decide whether to block the connection.

SNISPF sits between your app and the internet. It intercepts the hello message
and either **chops it up** or **sends a decoy** so the censorship system
can't read the real hostname. The destination server still receives the full,
correct request and answers normally.

```
┌──────────┐     ┌─────────┐     ┌─────────┐     ┌──────────────┐
│ Your App ├────>│ SNISPF  ├────>│  DPI /  ├────>│ Real Server  │
│ (browser,│     │ (local  │     │Firewall │     │ (e.g.        │
│  v2ray,  │     │  proxy) │     │         │     │  Cloudflare) │
│  etc.)   │     │         │     │         │     │              │
└──────────┘     └─────────┘     └─────────┘     └──────────────┘
                      │               │
                      │ sends fake /  │ sees fake or
                      │ fragmented    │ incomplete SNI
                      │ hello message │ --> lets it through
```

---

## Requirements

- **Python 3.8** or newer (check with `python3 --version`)
- That's it. No external dependencies, no C compilers, no kernel modules.

---

## Installation

SNISPF is distributed **as source only**. There are no GitHub Releases,
prebuilt binaries, or container images — running it is intentionally just a
small Python project you clone and execute.

### Option 1 — Run from source

```bash
git clone https://github.com/Rainman69/SNISPF.git
cd SNISPF
python3 run.py --info
```

### Option 2 — `pip install` from the repo

```bash
git clone https://github.com/Rainman69/SNISPF.git
cd SNISPF
pip install .
snispf --info
```

Or in one line, without cloning:

```bash
pip install git+https://github.com/Rainman69/SNISPF.git
```

> **Tip:** use a virtual environment (`python3 -m venv .venv && source .venv/bin/activate`) so the install doesn't touch your system Python.

---

## Quick Start

### 1. Start the proxy

```bash
# Using the default config.json bundled with the repo
python3 run.py --config config.json

# Or all-CLI, no config file:
python3 run.py \
    --listen 0.0.0.0:40443 \
    --connect 104.19.230.21:443 \
    --sni www.hcaptcha.com \
    --method fragment
```

You should see a log line like:

```
Listening on 0.0.0.0:40443
Forwarding to 104.19.230.21:443
Fake SNI: www.hcaptcha.com
Bypass strategy: fragment
```

### 2. Point your app at it

SNISPF is a transparent TCP forwarder. In whatever client you use
(`v2ray`, `xray`, browser proxy plugin, raw TCP client, …) configure the
upstream server as **`127.0.0.1:40443`** instead of the original
Cloudflare endpoint. Everything else (TLS, the real SNI for routing on
the CDN, etc.) is unchanged.

---

## Configuration

You can run SNISPF either from a JSON config file or entirely from CLI flags.
Anything passed on the command line overrides the file.

### Generate a default config

```bash
python3 run.py --generate-config my_config.json
```

### Config file reference

```jsonc
{
  "LISTEN_HOST":       "0.0.0.0",          // Address to bind the local proxy on
  "LISTEN_PORT":       40443,              // Local TCP port to listen on
  "CONNECT_IP":        "104.19.230.21",    // Upstream IP (typically a Cloudflare edge)
  "CONNECT_PORT":      443,                // Upstream TCP port
  "FAKE_SNI":          "www.hcaptcha.com", // Hostname to put in the decoy/fragmented SNI
  "BYPASS_METHOD":     "fragment",         // fragment | fake_sni | combined
  "FRAGMENT_STRATEGY": "sni_split",        // sni_split | half | multi | tls_record_frag
  "FRAGMENT_DELAY":    0.1,                // Seconds to wait between fragments
  "USE_TTL_TRICK":     false,              // Inject decoy with low IP TTL (auto on macOS / Android)
  "FAKE_SNI_METHOD":   "prefix_fake"       // prefix_fake | record_layer_split
}
```

---

## CLI Flags

```
--config, -C FILE         Path to JSON config file
--generate-config PATH    Generate a default config file and exit
--listen, -l HOST:PORT    Listen address (default: 0.0.0.0:40443)
--connect, -c IP:PORT     Target server address
--sni,    -s HOSTNAME     Fake SNI hostname
--method, -m METHOD       fragment | fake_sni | combined
--fragment-strategy STR   sni_split | half | multi | tls_record_frag
--fragment-delay  SEC     Delay between fragments
--ttl-trick               Use IP TTL trick for fake packets
--no-raw                  Disable raw socket injection even if available
--check-domains FILE      Bulk-check domains for Cloudflare backing
--check-workers N         Parallel workers for domain checking (default: 50)
--check-timeout SEC       Per-domain timeout (default: 3.0)
--output FILE             Export verified Cloudflare domains
--check-http              Also verify HTTP connectivity during check
--verbose, -v             Debug logging
--quiet,   -q             Warnings only
--version, -V             Print version and exit
--info                    Show platform capabilities and exit
```

---

## Bypass Methods

### `fragment` (default)

Cuts the TLS ClientHello into multiple TCP segments at the SNI boundary.
The DPI middlebox sees only fragments of the hostname and can't make a
matching decision. **Works on every platform, no privileges needed.**

### `fake_sni`

Sends one or more decoy ClientHello packets containing a fake hostname,
followed by the real one. The DPI commits its verdict on the first packet
it sees (the decoy) while the real server still gets the legitimate
hello. Most effective with raw sockets (Linux + root) for the `seq_id`
trick. Without raw sockets, falls back automatically to TTL-trick mode.

### `combined` (strongest)

Both fragmentation and a decoy hello at the same time. Recommended when
the censor's DPI is aggressive.

---

## Fragment Strategies

| Strategy            | What it does                                                           |
|---------------------|------------------------------------------------------------------------|
| `sni_split` (def.)  | Splits the TCP record exactly at the SNI hostname inside the hello     |
| `half`              | Splits into two roughly equal halves                                   |
| `multi`             | Multiple small fragments (5–10 bytes each)                             |
| `tls_record_frag`   | Splits at the TLS record layer instead of the TCP layer                |

---

## Domain Checker

SNISPF ships a bulk checker that takes a list of hostnames and tells you
which ones are actually fronted by Cloudflare, so you can pick a good
**FAKE_SNI** target.

```bash
# domains.txt: one hostname per line
python3 run.py --check-domains domains.txt
python3 run.py --check-domains domains.txt --output verified.txt
python3 run.py --check-domains domains.txt --check-http -v
```

Output is a table with the resolved IP, whether it falls inside a
published Cloudflare range, and (optionally) whether an HTTPS request
returned a Cloudflare response header.

---

## Platform Support

| Platform                | Status      | Notes                                                                       |
|-------------------------|-------------|-----------------------------------------------------------------------------|
| Linux (any distro)      | First-class | Raw socket injection available with `sudo` / `CAP_NET_RAW`                  |
| macOS (Apple Silicon)   | First-class | Auto-uses TTL trick (raw sockets are root-only on Darwin)                   |
| macOS (Intel)           | First-class | Same as above                                                               |
| Windows 10/11           | First-class | Fragmentation methods only — no raw sockets                                 |
| Android via Termux      | Supported   | Works without root using the fragment/combined methods (TTL trick auto-on)  |
| OpenBSD / FreeBSD       | Best-effort | Fragmentation methods work; raw injection untested                          |

Run `python3 run.py --info` to see exactly which capabilities your system
exposes.

---

## Troubleshooting

**Port already in use**
```bash
python3 run.py -l :40444 ...      # pick any free local port
```

**Permission denied on port < 1024**
Use a port ≥ 1024, or run with `sudo` if you really need a privileged port.

**Bypass doesn't work for some sites**
- Try `-m combined --fragment-strategy multi`
- Try a different `FAKE_SNI` (verify it's Cloudflare-backed with
  `--check-domains`).
- Increase `FRAGMENT_DELAY` (e.g. `--fragment-delay 0.25`) — some censors
  re-assemble fragments that arrive too quickly.

**Macros / antivirus complaining**
SNISPF is pure Python and ships no compiled binaries; if your AV is
flagging *something*, it's almost certainly a false positive on a Python
interpreter. You can read every line of source in this repo.

---

## Project Structure

```
SNISPF/
├── run.py                       # Entry point (python3 run.py …)
├── config.json                  # Default configuration
├── pyproject.toml               # Package metadata (snispf console script)
├── README.md / README_FA.md     # Docs (this file + Farsi translation)
├── LICENSE                      # MIT
├── sni_spoofing/
│   ├── __init__.py              # __version__, package init
│   ├── cli.py                   # argparse + main entry point
│   ├── forwarder.py             # async TCP forwarder, bypass orchestration
│   ├── bypass/                  # Fragmentation / fake-SNI / raw-injection strategies
│   ├── tls/                     # ClientHello builder + parser
│   ├── scanner/                 # Bulk Cloudflare-domain checker (only)
│   └── utils/                   # Platform detection, IP/port helpers
└── tests/                       # unittest suite
```

---

## Running the Tests

```bash
cd SNISPF
python3 -m unittest discover -s tests -v
```

The suite covers the TLS ClientHello builder and fragmentation logic.
Network-dependent tests are intentionally not part of the default run.

---

## License

[MIT](./LICENSE) © Rainman69
