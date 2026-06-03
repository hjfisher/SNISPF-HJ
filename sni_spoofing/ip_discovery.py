"""Dynamic Cloudflare IP discovery — feeds fresh IPs into the connection pool.

Inspired by https://github.com/bia-pain-bache/Cloudflare-Clean-IP-Scanner
(and its predecessor CloudflareScanner by Ptechgithub).

How it works
------------
Cloudflare publishes their IP ranges at https://www.cloudflare.com/ips-v4.
All IPs in those subnets are valid Cloudflare edge nodes.  We exploit that
by randomly sampling addresses from the official CIDR blocks, probing them
with a plain TCP connect, and handing the survivors to the connection pool.

This runs in a daemon thread alongside the pool's own health loop.  It does
NOT replace the static CONNECT_IPS list — it *augments* it.  Newly found
IPs are injected into the CombinationExplorer so the ActivePool can start
using them immediately (on the next pool refresh cycle).

Integration
-----------
Call ``start_discovery_loop()`` after creating the ConnectionManager::

    from sni_spoofing.ip_discovery import IPDiscovery
    discovery = IPDiscovery(manager=conn_manager, snis=config["FAKE_SNIS"])
    discovery.start()

or let ``build_connection_manager`` / ``cli.py`` do it automatically when
``DYNAMIC_IP_DISCOVERY`` is set to ``true`` in the config.
"""

from __future__ import annotations

import ipaddress
import logging
import random
import socket
import threading
import time
from typing import List, Optional, Set, TYPE_CHECKING

if TYPE_CHECKING:
    from .pool import ConnectionManager, PairStats

logger = logging.getLogger("snispf.discovery")

# ---------------------------------------------------------------------------
# Official Cloudflare IPv4 CIDR ranges (source: cloudflare.com/ips-v4)
# These rarely change; update when Cloudflare publishes new allocations.
# ---------------------------------------------------------------------------
CLOUDFLARE_CIDRS: List[str] = [
    "103.21.244.0/22",
    "103.22.200.0/22",
    "103.31.4.0/22",
    "104.16.0.0/13",
    "104.24.0.0/14",
    "108.162.192.0/18",
    "131.0.72.0/22",
    "141.101.64.0/18",
    "162.158.0.0/15",
    "172.64.0.0/13",
    "173.245.48.0/20",
    "188.114.96.0/20",
    "190.93.240.0/20",
    "197.234.240.0/22",
    "198.41.128.0/17",
]


# ---------------------------------------------------------------------------
# IP sampler — mirrors the Go logic from CloudflareScanner/task/ip.go
# ---------------------------------------------------------------------------

def _sample_random_ips(cidr: str, count: int) -> List[str]:
    """Return ``count`` random IPs drawn uniformly from a CIDR block.

    For a /22 (1022 hosts) we can draw many unique addresses.
    For a /13 (524286 hosts) the sample is tiny relative to the range —
    that's fine; the scanner sweeps multiple rounds over time.
    """
    try:
        network = ipaddress.IPv4Network(cidr, strict=False)
    except ValueError:
        logger.warning("Invalid CIDR %r — skipping.", cidr)
        return []

    hosts = list(network.hosts())
    if not hosts:
        return []

    k = min(count, len(hosts))
    return [str(ip) for ip in random.sample(hosts, k)]


def sample_cloudflare_ips(total: int, cidrs: Optional[List[str]] = None) -> List[str]:
    """Sample ``total`` random IPs spread across all Cloudflare CIDR ranges.

    IPs are drawn proportionally: subnets with more hosts contribute more
    candidates, which mirrors the distribution of real Cloudflare traffic.

    Args:
        total: How many IPs to sample overall.
        cidrs: Override the built-in CIDR list (useful for testing).

    Returns:
        A shuffled list of IPv4 strings, length ≤ ``total``.
    """
    cidrs = cidrs or CLOUDFLARE_CIDRS
    if not cidrs:
        return []

    # Count total host capacity so we can weight proportionally.
    weights: List[int] = []
    for cidr in cidrs:
        try:
            net = ipaddress.IPv4Network(cidr, strict=False)
            weights.append(net.num_addresses - 2)  # exclude network + broadcast
        except ValueError:
            weights.append(0)

    total_hosts = sum(weights)
    if total_hosts == 0:
        return []

    result: List[str] = []
    for cidr, w in zip(cidrs, weights):
        if w == 0:
            continue
        # Proportional share, at least 1 per CIDR.
        share = max(1, round(total * w / total_hosts))
        result.extend(_sample_random_ips(cidr, share))

    random.shuffle(result)
    # Trim to exactly ``total`` (proportional rounding may overshoot slightly).
    return result[:total]


# ---------------------------------------------------------------------------
# TCP reachability probe (mirrors tcping.go)
# ---------------------------------------------------------------------------

def _tcp_probe(ip: str, port: int, timeout: float, attempts: int) -> float:
    """Return the fraction of successful TCP connects (0.0 – 1.0).

    A result ≥ 0.5 is considered reachable.  We mirror the CloudflareScanner
    approach: multiple short connect attempts, count successes.
    """
    successes = 0
    for _ in range(attempts):
        try:
            with socket.create_connection((ip, port), timeout=timeout):
                successes += 1
        except OSError:
            pass
        # Small gap to avoid overwhelming the host.
        time.sleep(random.uniform(0.02, 0.08))
    return successes / attempts


# ---------------------------------------------------------------------------
# IPDiscovery — the main scanner class
# ---------------------------------------------------------------------------

class IPDiscovery:
    """Continuously discovers fresh Cloudflare IPs and injects them into the pool.

    Lifecycle
    ~~~~~~~~~
    1. ``start()`` — launches a daemon thread that runs ``_loop()`` forever.
    2. Every ``scan_interval`` seconds the scanner:
       a. Samples ``scan_batch`` random IPs from the Cloudflare CIDR list.
       b. Probes each candidate with ``probe_attempts`` TCP connects.
       c. Accepts IPs whose success rate is ≥ ``min_success_rate``.
       d. For each accepted IP that is **new** (not already in the pool),
          injects (IP × all known SNIs) into the CombinationExplorer.
       e. Caps the dynamic pool at ``max_dynamic_ips`` to avoid unbounded
          memory growth — evicts the oldest discoveries when over limit.

    The ConnectionManager's health loop picks up new pairs on its next
    ``periodic_explore()`` cycle (typically within 30 s).
    """

    def __init__(
        self,
        manager: "ConnectionManager",
        snis: List[str],
        scan_batch: int = 100,
        scan_interval: float = 120.0,
        probe_attempts: int = 3,
        probe_timeout: float = 2.0,
        min_success_rate: float = 0.50,
        max_dynamic_ips: int = 200,
        port: int = 443,
        cidrs: Optional[List[str]] = None,
    ) -> None:
        """Create an IPDiscovery instance.

        Args:
            manager:          The active ConnectionManager to inject IPs into.
            snis:             The SNI list to pair with each discovered IP.
            scan_batch:       How many random IPs to sample each round.
            scan_interval:    Seconds between scan rounds.
            probe_attempts:   TCP connect attempts per candidate.
            probe_timeout:    TCP connect timeout (seconds) per attempt.
            min_success_rate: Fraction of probes that must succeed (0–1).
            max_dynamic_ips:  Cap on how many dynamic IPs we keep in memory.
            port:             Target port for TCP probes (usually 443).
            cidrs:            Override the built-in Cloudflare CIDR list.
        """
        self.manager = manager
        self.snis = list(snis)
        self.scan_batch = scan_batch
        self.scan_interval = scan_interval
        self.probe_attempts = probe_attempts
        self.probe_timeout = probe_timeout
        self.min_success_rate = min_success_rate
        self.max_dynamic_ips = max_dynamic_ips
        self.port = port
        self.cidrs = cidrs or CLOUDFLARE_CIDRS

        # Set of IPs already known to the pool (static + dynamic).
        self._known_ips: Set[str] = {
            ip for (ip, _) in manager.explorer.stats.keys()
        }
        # Ordered list of dynamically discovered IPs (oldest first).
        self._dynamic_ips: List[str] = []
        self._lock = threading.Lock()
        self._thread: Optional[threading.Thread] = None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def start(self) -> threading.Thread:
        """Start the discovery loop in a background daemon thread."""
        self._thread = threading.Thread(
            target=self._loop,
            name="snispf-ip-discovery",
            daemon=True,
        )
        self._thread.start()
        logger.info(
            "IP discovery started — batch=%d  interval=%ds  CIDRs=%d",
            self.scan_batch, int(self.scan_interval), len(self.cidrs),
        )
        return self._thread

    @property
    def dynamic_ip_count(self) -> int:
        with self._lock:
            return len(self._dynamic_ips)

    # ------------------------------------------------------------------
    # Internal loop
    # ------------------------------------------------------------------

    def _loop(self) -> None:
        """Main discovery loop — runs forever in a daemon thread."""
        # First scan starts after a short delay so the pool's own initial
        # probe can finish first.
        time.sleep(15 + random.uniform(0, 10))

        while True:
            try:
                self._scan_round()
            except Exception:
                import traceback
                logger.debug("Discovery error:\n%s", traceback.format_exc())

            jitter = random.uniform(-15, 15)
            sleep_for = max(30, self.scan_interval + jitter)
            logger.debug("Next IP discovery scan in %.0f s", sleep_for)
            time.sleep(sleep_for)

    def _scan_round(self) -> None:
        """Run one full scan round: sample → probe → inject."""
        candidates = sample_cloudflare_ips(self.scan_batch, self.cidrs)

        # Filter out IPs already in the pool.
        with self._lock:
            known = set(self._known_ips)
        candidates = [ip for ip in candidates if ip not in known]

        if not candidates:
            logger.debug("Discovery: all sampled IPs already known — skipping.")
            return

        logger.info(
            "IP discovery: probing %d candidates (batch=%d, %d new) ...",
            len(candidates), self.scan_batch, len(candidates),
        )

        # Probe in parallel threads.
        accepted: List[str] = []
        lock = threading.Lock()

        def _probe_one(ip: str) -> None:
            rate = _tcp_probe(
                ip, self.port, self.probe_timeout, self.probe_attempts
            )
            if rate >= self.min_success_rate:
                with lock:
                    accepted.append(ip)

        threads = [
            threading.Thread(target=_probe_one, args=(ip,), daemon=True)
            for ip in candidates
        ]
        # Stagger thread starts to avoid a SYN flood.
        for t in threads:
            t.start()
            time.sleep(random.uniform(0, 0.02))
        for t in threads:
            t.join()

        logger.info(
            "IP discovery: %d / %d candidates accepted (≥%.0f%% success)",
            len(accepted), len(candidates), self.min_success_rate * 100,
        )

        if not accepted:
            return

        # Inject new IPs into the pool.
        injected = 0
        for ip in accepted:
            injected += self._inject_ip(ip)

        logger.info(
            "IP discovery: injected %d new (IP, SNI) pairs into the pool.",
            injected,
        )

        # Trigger an immediate pool refresh so the best new pairs can enter
        # the active set without waiting for the next scheduled health cycle.
        if injected > 0:
            self.manager.pool.refresh()

    def _inject_ip(self, ip: str) -> int:
        """Add one new IP × all SNIs into the explorer.  Returns pairs added."""
        with self._lock:
            if ip in self._known_ips:
                return 0

            # Enforce the cap: evict the oldest dynamic IP if over limit.
            if len(self._dynamic_ips) >= self.max_dynamic_ips:
                evicted_ip = self._dynamic_ips.pop(0)
                self._known_ips.discard(evicted_ip)
                # Remove evicted pairs from the explorer stats dict.
                # (They won't be in the active pool since they're old/weak.)
                for sni in self.snis:
                    self.manager.explorer.stats.pop((evicted_ip, sni), None)
                logger.debug("Discovery: evicted old IP %s from pool.", evicted_ip)

            self._known_ips.add(ip)
            self._dynamic_ips.append(ip)

        # Add PairStats entries for ip × all snis.
        from .pool import PairStats  # local import to avoid circular

        added = 0
        for sni in self.snis:
            key = (ip, sni)
            if key not in self.manager.explorer.stats:
                ps = PairStats(ip, sni)
                self.manager.explorer.stats[key] = ps
                # Also add to the unexplored queue so it gets probed soon.
                with self.manager.explorer._lock:
                    self.manager.explorer._unexplored.append(key)
                added += 1

        return added

    # ------------------------------------------------------------------
    # Diagnostics
    # ------------------------------------------------------------------

    def log_status(self) -> None:
        with self._lock:
            dynamic = len(self._dynamic_ips)
            known = len(self._known_ips)
        logger.info(
            "IP discovery status — dynamic IPs: %d / %d  total known: %d",
            dynamic, self.max_dynamic_ips, known,
        )


# ---------------------------------------------------------------------------
# Factory helper
# ---------------------------------------------------------------------------

def build_ip_discovery(
    manager: "ConnectionManager",
    config: dict,
) -> Optional["IPDiscovery"]:
    """Build an IPDiscovery from config, or return None if disabled.

    Reads the following config keys (all optional):

    ``DYNAMIC_IP_DISCOVERY``   bool   Enable dynamic discovery (default: false)
    ``DISCOVERY_BATCH``        int    IPs sampled per round (default: 100)
    ``DISCOVERY_INTERVAL``     float  Seconds between rounds (default: 120)
    ``DISCOVERY_PROBE_TRIES``  int    TCP probes per candidate (default: 3)
    ``DISCOVERY_TIMEOUT``      float  TCP connect timeout (default: 2.0)
    ``DISCOVERY_MIN_SUCCESS``  float  Min success rate 0–1 (default: 0.50)
    ``DISCOVERY_MAX_IPS``      int    Cap on dynamic IPs (default: 200)
    """
    if not config.get("DYNAMIC_IP_DISCOVERY", False):
        return None

    snis: List[str] = config.get("FAKE_SNIS", [])
    if not snis and config.get("FAKE_SNI"):
        snis = [config["FAKE_SNI"]]
    if not snis:
        logger.warning("IP discovery enabled but no FAKE_SNIS — disabled.")
        return None

    return IPDiscovery(
        manager=manager,
        snis=snis,
        scan_batch=config.get("DISCOVERY_BATCH", 100),
        scan_interval=config.get("DISCOVERY_INTERVAL", 120.0),
        probe_attempts=config.get("DISCOVERY_PROBE_TRIES", 3),
        probe_timeout=config.get("DISCOVERY_TIMEOUT", 2.0),
        min_success_rate=config.get("DISCOVERY_MIN_SUCCESS", 0.50),
        max_dynamic_ips=config.get("DISCOVERY_MAX_IPS", 200),
        port=config.get("CONNECT_PORT", 443),
    )
