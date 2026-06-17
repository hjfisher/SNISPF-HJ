"""Multi-IP / Multi-SNI connection pool with adaptive health tracking.

This module ports the core ideas from SNI-Spoofing-HJ (by @hjfisher /
@patterniha) into SNISPF's architecture:

  - PairStats          — tracks probe loss and real-traffic loss for one
                         (IP, SNI) pair; carries a force-close event so
                         the forwarder can shut down connections when the
                         drain timeout expires.
  - CombinationExplorer — gradually discovers and health-checks the full
                          cartesian product of IPs × SNIs
  - ActivePool         — keeps ACTIVE_SLOTS pairs warm; drains weak pairs
                         with a hard timeout and a cap on simultaneous
                         draining pairs; periodically evicts the weakest
                         IPs from the entire stats dict so the pool never
                         stagnates.
  - ConnectionManager  — ties everything together with a background health
                         loop.

Key behaviours added vs. the original design
--------------------------------------------
1. **Eviction with quarantine** — every EVICT_EVERY health cycles the
   weakest IP (across *all* pairs, static + dynamic) is moved out of the
   active stats dict into a quarantine list rather than being discarded
   forever. Pairs with higher loss rates are evicted first, giving the
   dynamic discovery thread room to inject fresher IPs.

2. **Recycling** — every RECYCLE_EVERY health cycles, a random sample of
   quarantined IPs is re-probed. An IP that now passes the health check is
   restored to the active stats dict with brand-new PairStats objects (no
   memory of its prior failures), giving it a genuinely fresh chance.

3. **EMA-based loss tracking** — probe loss and real-traffic loss are each
   tracked as an exponential moving average rather than a cumulative
   counter. This means a pair that was unhealthy and has since recovered
   will see its score improve as fresh good results arrive, instead of
   being permanently weighed down by old failures.

4. **Drain timeout** — when a pair enters draining its ``drain_started_at``
   timestamp is recorded. After ``DRAIN_TIMEOUT`` seconds the pair's
   ``force_close_event`` is set. The forwarder watches that event inside
   the relay loop and closes the sockets as soon as it fires.

5. **Drain cap** — at most ``MAX_DRAINING`` pairs can be draining
   simultaneously. If a new pair would exceed the cap the oldest draining
   pair is force-closed immediately.
"""

from __future__ import annotations

import logging
import random
import socket
import threading
import time
from typing import Dict, List, Optional, Set, Tuple

logger = logging.getLogger("snispf.pool")


# ---------------------------------------------------------------------------
# PairStats
# ---------------------------------------------------------------------------

class PairStats:
    """Per-(IP, SNI) statistics used to rank and health-check upstream pairs.

    Loss rates are blended from two sources:
      - *probe* loss: lightweight TCP connect probes sent by the explorer
      - *real* loss: actual forwarded connections that failed mid-stream

    When enough real-traffic data exist (> 10 packets) the score weights
    real loss at 70 % and probe loss at 30 %.  Before that threshold the
    score is purely probe-based so the pool can bootstrap quickly.

    Drain support
    ~~~~~~~~~~~~~
    ``force_close_event`` is a threading.Event that the ActivePool sets when
    the drain timeout expires.  The forwarder checks this event inside the
    relay loop and closes both sockets when it fires, ending the connection
    cleanly from our side.

    ``drain_started_at`` records the monotonic timestamp at which the pair
    entered the draining state.  ``None`` means it is not draining.
    """

    MIN_PROBES: int = 3
    # Worst-case latency cap for normalisation (ms).
    # Pairs above this are treated as maximally slow (latency_score = 1.0).
    LATENCY_CAP_MS: float = 1500.0

    # EMA smoothing factors. Higher alpha = faster reaction to recent
    # results, lower alpha = longer memory / more stable.
    # Probes arrive on a fixed schedule (~every health cycle) so a
    # moderate alpha keeps the score responsive.  Real-traffic packets can
    # arrive in bursts (many connections at once), so a smaller alpha keeps
    # one bad burst from dominating the score.
    EMA_ALPHA_PROBE: float = 0.25
    EMA_ALPHA_REAL: float = 0.15

    def __init__(self, ip: str, sni: str, origin: str = "static") -> None:
        self.ip: str = ip
        self.sni: str = sni
        # Where this pair's IP came from:
        #   "static"  — listed in CONNECT_IPS in the config file
        #   "dynamic" — found at runtime by the IP discovery scanner
        # Used to scope eviction/quarantine/recycling to one source or both.
        self.origin: str = origin

        self.probes_sent: int = 0
        self.probes_recv: int = 0
        self.real_packets_sent: int = 0
        self.real_packets_lost: int = 0

        # Exponential moving averages of loss (0.0 = perfect, 1.0 = total
        # loss).  Unlike raw cumulative counters these naturally "forget"
        # old results — if a pair was bad and then recovers, its EMA will
        # drift back down as fresh successful probes/packets arrive,
        # instead of being permanently weighed down by old failures.
        self.ema_probe_loss: float = 0.0
        self.ema_real_loss: float = 0.0

        # Latency tracking — rolling average of TLS handshake time (ms).
        # Only successful probes contribute; failed ones are excluded so a
        # 3000 ms timeout doesn't artificially inflate the average.
        self._latency_sum_ms: float = 0.0
        self._latency_count: int = 0

        self.active_connections: int = 0
        self.total_connections: int = 0
        self.alive: bool = True
        self.probed: bool = False
        self.in_active_pool: bool = False

        # Drain support — set by ActivePool, checked by forwarder.
        self.force_close_event: threading.Event = threading.Event()
        self.drain_started_at: Optional[float] = None

        self.lock = threading.Lock()

    # ------------------------------------------------------------------
    # Computed properties
    # ------------------------------------------------------------------

    @property
    def probe_loss_rate(self) -> float:
        """EMA-based probe loss rate.  0.0 until MIN_PROBES is reached."""
        if self.probes_sent < self.MIN_PROBES:
            return 0.0
        return self.ema_probe_loss

    @property
    def real_loss_rate(self) -> float:
        """EMA-based real-traffic loss rate.  0.0 until any packet is recorded."""
        if self.real_packets_sent == 0:
            return 0.0
        return self.ema_real_loss

    @property
    def combined_loss_rate(self) -> float:
        """Blended loss rate: 70 % real + 30 % probe once real data exist.

        Both components are now exponential moving averages, so a pair
        that was bad and has since recovered will see its combined loss
        rate decay back down as fresh successful results arrive — no
        permanent penalty from old failures.
        """
        if self.real_packets_sent > 10:
            return 0.7 * self.real_loss_rate + 0.3 * self.probe_loss_rate
        return self.probe_loss_rate

    @property
    def avg_latency_ms(self) -> float:
        """Average TLS handshake latency across successful probes (ms).

        Returns LATENCY_CAP_MS when no successful probe has been recorded
        yet, so unknown pairs are treated as slow rather than fast — this
        prevents them from jumping to the top of the pool before being tested.
        """
        if self._latency_count == 0:
            return self.LATENCY_CAP_MS
        return self._latency_sum_ms / self._latency_count

    @property
    def latency_score(self) -> float:
        """Normalised latency score in [0, 1].  0 = fastest, 1 = slowest.

        Capped at LATENCY_CAP_MS so extreme outliers don't dominate.
        """
        return min(self.avg_latency_ms, self.LATENCY_CAP_MS) / self.LATENCY_CAP_MS

    @property
    def score(self) -> float:
        """Composite score — lower is better.

        Weights:
          60 % combined loss rate  (main quality signal)
          20 % latency score       (TLS handshake speed)
          20 % probe loss rate     (raw probe health)

        Dead  → +inf  (never selected)
        Unknown (not yet probed) → 0.5  (given a fair chance)
        """
        if not self.alive:
            return float("inf")
        if not self.probed:
            return 0.5
        return (
            0.60 * self.combined_loss_rate
            + 0.20 * self.latency_score
            + 0.20 * self.probe_loss_rate
        )

    @property
    def is_stable(self) -> bool:
        return self.alive and self.probed

    # ------------------------------------------------------------------
    # Mutation helpers (thread-safe)
    # ------------------------------------------------------------------

    def record_probe(
        self,
        success: bool,
        dead_threshold: float = 0.80,
        latency_ms: float = 0.0,
    ) -> None:
        """Update probe EMA and flip ``alive`` if needed.

        Args:
            success:       Whether the TLS handshake succeeded.
            dead_threshold: EMA loss above which the pair is marked dead.
            latency_ms:    TLS handshake duration in milliseconds.
                           Only recorded when success=True.
        """
        with self.lock:
            self.probes_sent += 1
            self.probed = True

            loss_this = 0.0 if success else 1.0
            a = self.EMA_ALPHA_PROBE
            self.ema_probe_loss = a * loss_this + (1 - a) * self.ema_probe_loss

            if success:
                self.probes_recv += 1
                # Rolling average — only successful probes contribute.
                self._latency_sum_ms += latency_ms
                self._latency_count += 1

            if self.probes_sent >= self.MIN_PROBES:
                if self.ema_probe_loss >= dead_threshold:
                    self.alive = False
                elif self.probes_recv > 0:
                    self.alive = True

    def record_real_packet(self, lost: bool) -> None:
        """Update real-traffic loss EMA for a forwarded connection."""
        with self.lock:
            self.real_packets_sent += 1
            if lost:
                self.real_packets_lost += 1
            loss_this = 1.0 if lost else 0.0
            a = self.EMA_ALPHA_REAL
            self.ema_real_loss = a * loss_this + (1 - a) * self.ema_real_loss

    def start_draining(self) -> None:
        """Mark this pair as draining and record the start timestamp."""
        with self.lock:
            if self.drain_started_at is None:
                self.drain_started_at = time.monotonic()

    def force_close(self) -> None:
        """Signal all active connections on this pair to shut down now."""
        with self.lock:
            self.in_active_pool = False
        self.force_close_event.set()
        logger.info(
            "Force-closing pair %s / %s (%d active connection(s))",
            self.ip, self.sni, self.active_connections,
        )

    def drain_age(self) -> float:
        """Seconds since this pair entered draining (0 if not draining)."""
        if self.drain_started_at is None:
            return 0.0
        return time.monotonic() - self.drain_started_at

    def __repr__(self) -> str:
        return (
            f"<PairStats {self.ip} sni={self.sni!r} "
            f"loss={self.combined_loss_rate*100:.1f}% "
            f"alive={self.alive} active={self.active_connections}>"
        )


# ---------------------------------------------------------------------------
# CombinationExplorer
# ---------------------------------------------------------------------------

class CombinationExplorer:
    """Gradually discovers and health-checks (IP, SNI) combinations.

    Exploration stages
    ------------------
    1. **Initial batch** — probes a random sample of INITIAL_SAMPLE pairs
       to populate the pool quickly.
    2. **Periodic cycles** — re-verifies the top VERIFY_TOP known pairs
       and explores EXPLORE_BATCH new ones.
    3. **Reshuffle** — when all combinations have been explored at least
       once the unexplored queue is reshuffled and the cycle restarts.

    Probes are simple TCP connect attempts (no TLS).
    """

    INITIAL_SAMPLE: int = 20
    EXPLORE_BATCH: int = 10
    VERIFY_TOP: int = 15

    def __init__(
        self,
        combinations: List[Tuple[str, str]],
        port: int,
        timeout: float,
        probe_count: int,
        loss_threshold: float = 0.20,
        dead_threshold: float = 0.80,
    ) -> None:
        self.port = port
        self.timeout = timeout
        self.probe_count = probe_count
        self.loss_threshold = loss_threshold
        self.dead_threshold = dead_threshold

        self.stats: Dict[Tuple[str, str], PairStats] = {
            (ip, sni): PairStats(ip, sni, origin="static")
            for ip, sni in combinations
        }

        self._unexplored: List[Tuple[str, str]] = list(combinations)
        random.shuffle(self._unexplored)
        self._lock = threading.Lock()

        # Quarantine: IPs evicted for being weak are kept here (not fully
        # discarded) so they can be randomly re-tested later and brought
        # back into the pool if they have genuinely recovered.
        # Maps ip -> dict with the SNI list it was evicted with, plus
        # timestamps used for cooldown scheduling.
        self._quarantine: Dict[str, dict] = {}
        self._all_snis: List[str] = sorted({sni for _, sni in combinations})

        logger.info(
            "CombinationExplorer initialised: %d IP(s) × SNI(s) = %d pairs",
            len({ip for ip, _ in combinations}),
            len(combinations),
        )

    # ------------------------------------------------------------------
    # Public accessors
    # ------------------------------------------------------------------

    def all_stats(self) -> List[PairStats]:
        return list(self.stats.values())

    def known_stats(self) -> List[PairStats]:
        return [ps for ps in self.stats.values() if ps.probed]

    def stable_stats(self) -> List[PairStats]:
        return [
            ps for ps in self.known_stats()
            if ps.alive and ps.combined_loss_rate < self.loss_threshold
        ]

    # ------------------------------------------------------------------
    # Eviction — removes the weakest IP from the stats dict entirely
    # ------------------------------------------------------------------

    def evict_weakest_ip(
        self,
        protected_ips: Set[str],
        scope: str = "both",
    ) -> Optional[str]:
        """Move the weakest IP's pairs out of active stats into quarantine.

        The weakest IP is the one whose *average* combined_loss_rate across
        all its SNI pairs is highest.  IPs in ``protected_ips`` (those
        currently in the active pool or draining) are skipped so we never
        evict a pair that is serving live connections.

        Args:
            protected_ips: IPs that must never be evicted right now.
            scope: Which IP origin is eligible for eviction:
                   "static"  — only IPs from CONNECT_IPS in the config
                   "dynamic" — only IPs found by the discovery scanner
                   "both"    — either (default)

        Evicted IPs are not discarded forever — they go into a quarantine
        list (see ``recycle_attempt``) so they can be probed again later
        and brought back if they have genuinely recovered.

        Returns the evicted IP string, or None if nothing was evicted.
        """
        # Group known pairs by IP, skip protected ones and out-of-scope origins.
        ip_loss: Dict[str, List[float]] = {}
        for (ip, _sni), ps in self.stats.items():
            if ip in protected_ips:
                continue
            if scope != "both" and ps.origin != scope:
                continue
            if ps.probed:
                ip_loss.setdefault(ip, []).append(ps.combined_loss_rate)

        if not ip_loss:
            return None

        # Pick the IP with the worst average loss.
        worst_ip = max(ip_loss, key=lambda ip: sum(ip_loss[ip]) / len(ip_loss[ip]))
        worst_avg = sum(ip_loss[worst_ip]) / len(ip_loss[worst_ip])

        # Only evict if the IP is genuinely bad (above loss_threshold).
        if worst_avg < self.loss_threshold:
            logger.debug(
                "Eviction skipped — best candidate %s has avg loss %.1f%% < threshold",
                worst_ip, worst_avg * 100,
            )
            return None

        # Remove all pairs for this IP from stats and unexplored queue.
        keys_to_remove = [k for k in self.stats if k[0] == worst_ip]
        snis_for_ip = [k[1] for k in keys_to_remove]
        origin = self.stats[keys_to_remove[0]].origin if keys_to_remove else "static"
        for k in keys_to_remove:
            del self.stats[k]
        with self._lock:
            self._unexplored = [k for k in self._unexplored if k[0] != worst_ip]

            # Move to quarantine instead of discarding entirely.
            self._quarantine[worst_ip] = {
                "snis": snis_for_ip,
                "origin": origin,
                "evicted_at": time.monotonic(),
                "last_attempt": time.monotonic(),
                "attempts": 0,
            }

        logger.info(
            "Evicted IP %s to quarantine (avg loss %.1f%%, %d pair(s) removed)",
            worst_ip, worst_avg * 100, len(keys_to_remove),
        )
        return worst_ip

    # ------------------------------------------------------------------
    # Recycling — randomly re-test quarantined IPs and bring back winners
    # ------------------------------------------------------------------

    def recycle_attempt(
        self,
        batch: int,
        min_cooldown: float,
        max_quarantine: int,
        scope: str = "both",
    ) -> int:
        """Randomly re-probe a few quarantined IPs; recover the healthy ones.

        Args:
            batch:          How many quarantined IPs to test this round.
            min_cooldown:   Minimum seconds since last attempt before an IP
                            is eligible to be re-tested again.
            max_quarantine: Cap on quarantine size — oldest entries are
                            dropped permanently when the cap is exceeded.
            scope: Which quarantined IPs are eligible to be tested:
                   "static"  — only IPs originally from CONNECT_IPS
                   "dynamic" — only IPs originally found by discovery
                   "both"    — either (default)

        Returns:
            Number of IPs successfully recovered back into ``self.stats``.
        """
        with self._lock:
            # Enforce the quarantine size cap — drop the oldest entries
            # for good so memory doesn't grow without bound.
            if len(self._quarantine) > max_quarantine:
                by_age = sorted(
                    self._quarantine.items(), key=lambda kv: kv[1]["evicted_at"]
                )
                overflow = len(self._quarantine) - max_quarantine
                for ip, _ in by_age[:overflow]:
                    del self._quarantine[ip]
                logger.debug(
                    "Quarantine cap (%d) exceeded — dropped %d oldest IP(s) permanently.",
                    max_quarantine, overflow,
                )

            now = time.monotonic()
            eligible = [
                ip for ip, info in self._quarantine.items()
                if now - info["last_attempt"] >= min_cooldown
                and (scope == "both" or info.get("origin", "static") == scope)
            ]
            if not eligible:
                return 0

            random.shuffle(eligible)
            candidates = eligible[:batch]

        recovered = 0
        for ip in candidates:
            if self._try_recycle_one(ip):
                recovered += 1
        return recovered

    def _try_recycle_one(self, ip: str) -> bool:
        """Probe one quarantined IP; if healthy, restore it to active stats.

        Uses a fresh, temporary PairStats (no memory of the old failures)
        so a recovered IP is judged purely on its current behaviour — this
        is the "recycling" equivalent of starting the EMA from scratch.
        """
        with self._lock:
            info = self._quarantine.get(ip)
            if info is None:
                return False
            info["last_attempt"] = time.monotonic()
            info["attempts"] += 1
            snis = info["snis"] or self._all_snis
            origin = info.get("origin", "static")

        # Probe with a throwaway PairStats — one SNI is enough to decide
        # whether the IP itself is reachable again; if it is, all of its
        # original SNI pairs are restored fresh.
        probe_sni = snis[0] if snis else (self._all_snis[0] if self._all_snis else None)
        if probe_sni is None:
            return False

        trial = PairStats(ip, probe_sni, origin=origin)
        self._probe_one(trial)

        # Require a clearly healthy result before trusting the IP again.
        if not trial.alive or trial.combined_loss_rate >= self.loss_threshold:
            logger.debug(
                "Recycle attempt failed for %s (loss=%.1f%%, alive=%s)",
                ip, trial.combined_loss_rate * 100, trial.alive,
            )
            return False

        # Healthy — restore all original (ip, sni) pairs as brand-new
        # PairStats objects (same origin) so no stale EMA history carries over.
        with self._lock:
            del self._quarantine[ip]
            for sni in snis:
                key = (ip, sni)
                if key not in self.stats:
                    self.stats[key] = PairStats(ip, sni, origin=origin)
                    self._unexplored.append(key)

        logger.info(
            "Recycled IP %s back into the pool (probe loss=%.1f%%, %d pair(s) restored)",
            ip, trial.combined_loss_rate * 100, len(snis),
        )
        return True

    # ------------------------------------------------------------------
    # Internal probing helpers
    # ------------------------------------------------------------------

    def _probe_one(self, ps: PairStats) -> None:
        """Probe one (IP, SNI) pair with a real TLS handshake.

        Measures the wall-clock time of the TLS handshake and records it
        as latency so the score reflects both loss rate and connection speed.
        Uses the pair's own SNI so the test reflects exactly what the
        forwarder will send.  Certificate validation is disabled because we
        are testing reachability, not cert validity.
        """
        import ssl
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE

        count = max(2, self.probe_count + random.randint(-1, 1))
        for _ in range(count):
            success = False
            latency_ms = 0.0
            try:
                t0 = time.monotonic()
                with socket.create_connection(
                    (ps.ip, self.port), timeout=self.timeout
                ) as raw:
                    with ctx.wrap_socket(raw, server_hostname=ps.sni):
                        latency_ms = (time.monotonic() - t0) * 1000
                        success = True
            except Exception:
                pass
            ps.record_probe(
                success=success,
                dead_threshold=self.dead_threshold,
                latency_ms=latency_ms,
            )
            time.sleep(random.uniform(0.05, 0.2))

    def _run_probes_parallel(self, pairs: List[PairStats]) -> None:
        random.shuffle(pairs)
        threads = [
            threading.Thread(target=self._probe_one, args=(ps,), daemon=True)
            for ps in pairs
        ]
        for t in threads:
            t.start()
            time.sleep(random.uniform(0, 0.03))
        for t in threads:
            t.join()

    # ------------------------------------------------------------------
    # Exploration lifecycle
    # ------------------------------------------------------------------

    def initial_explore(self) -> None:
        with self._lock:
            batch_keys = self._unexplored[: self.INITIAL_SAMPLE]
            self._unexplored = self._unexplored[self.INITIAL_SAMPLE :]
        batch = [self.stats[k] for k in batch_keys if k in self.stats]
        logger.info("Initial probe: %d combinations ...", len(batch))
        self._run_probes_parallel(batch)

    def periodic_explore(self) -> None:
        # Re-verify the best known pairs to catch degraded upstreams early.
        known = sorted(self.known_stats(), key=lambda ps: ps.score)
        to_verify = known[: self.VERIFY_TOP]
        if to_verify:
            logger.debug("Verifying top %d known pairs ...", len(to_verify))
            self._run_probes_parallel(to_verify)

        # Discover a fresh batch from the unexplored queue.
        with self._lock:
            batch_keys = self._unexplored[: self.EXPLORE_BATCH]
            self._unexplored = self._unexplored[self.EXPLORE_BATCH :]
            remaining = len(self._unexplored)

        # Filter keys that may have been evicted between cycles.
        batch = [self.stats[k] for k in batch_keys if k in self.stats]
        if batch:
            logger.debug(
                "Exploring %d new combinations (%d remaining) ...",
                len(batch), remaining,
            )
            self._run_probes_parallel(batch)
        else:
            logger.info("All combinations explored — reshuffling for next cycle.")
            with self._lock:
                all_keys = list(self.stats.keys())
                random.shuffle(all_keys)
                self._unexplored = all_keys

    # ------------------------------------------------------------------
    # Diagnostics
    # ------------------------------------------------------------------

    def print_summary(self) -> None:
        known = self.known_stats()
        stable = [ps for ps in known if ps.alive and ps.combined_loss_rate < self.loss_threshold]
        weak   = [ps for ps in known if ps.alive and ps.combined_loss_rate >= self.loss_threshold]
        dead   = [ps for ps in known if not ps.alive]
        unknown_count = len(self.stats) - len(known)

        logger.info(
            "Pool summary — known=%d  stable=%d  weak=%d  dead=%d  unexplored=%d",
            len(known), len(stable), len(weak), len(dead), unknown_count,
        )
        for ps in sorted(stable, key=lambda x: x.score)[: 8]:
            marker = "*" if ps.in_active_pool else " "
            logger.info(
                "  %s %-20s %-25s  loss=%.1f%%  latency=%dms  score=%.3f  active=%d",
                marker, ps.ip, ps.sni,
                ps.combined_loss_rate * 100,
                int(ps.avg_latency_ms),
                ps.score,
                ps.active_connections,
            )


# ---------------------------------------------------------------------------
# ActivePool
# ---------------------------------------------------------------------------

class ActivePool:
    """Maintains ACTIVE_SLOTS stable (IP, SNI) pairs for serving connections.

    Eviction
    ~~~~~~~~
    Every ``evict_every`` calls to ``refresh()`` the weakest IP (by average
    loss across all its SNI pairs) is removed from the explorer's stats dict
    entirely.  This prevents the pool from becoming stale over long runs and
    gives the IP discovery thread room to inject fresh candidates.

    Drain timeout
    ~~~~~~~~~~~~~
    When a pair is moved to draining its ``drain_started_at`` timestamp is
    recorded.  On each subsequent ``refresh()`` call, any draining pair whose
    age exceeds ``drain_timeout`` seconds has ``force_close()`` called on it.
    The forwarder watches ``pair.force_close_event`` inside the relay loop
    and closes the sockets when the event fires.

    Drain cap
    ~~~~~~~~~
    At most ``max_draining`` pairs can be in the draining list at once.  If
    adding a new pair would exceed the cap the oldest draining pair (longest
    drain age) is force-closed immediately to make room.
    """

    def __init__(
        self,
        explorer: CombinationExplorer,
        slots: int,
        loss_threshold: float = 0.20,
        drain_timeout: float = 30.0,
        max_draining: int = 5,
        evict_every: int = 3,
        evict_count: int = 2,
        recycle_enabled: bool = True,
        recycle_every: int = 6,
        recycle_batch: int = 2,
        recycle_min_cooldown: float = 180.0,
        recycle_max_quarantine: int = 100,
        quarantine_scope: str = "both",
    ) -> None:
        self.explorer = explorer
        self.slots = slots
        self.loss_threshold = loss_threshold
        self.drain_timeout = drain_timeout
        self.max_draining = max_draining
        self.evict_every = evict_every
        self.evict_count = evict_count
        self.recycle_enabled = recycle_enabled
        self.recycle_every = recycle_every
        self.recycle_batch = recycle_batch
        self.recycle_min_cooldown = recycle_min_cooldown
        self.recycle_max_quarantine = recycle_max_quarantine
        # Which IP origin is eligible for eviction + recycling:
        # "static" (CONNECT_IPS only), "dynamic" (discovery only), or "both".
        self.quarantine_scope = quarantine_scope

        self._pool: List[PairStats] = []
        self._draining: List[PairStats] = []
        self._lock = threading.Lock()
        self._refresh_count: int = 0

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def initialize(self) -> None:
        with self._lock:
            candidates = self.explorer.stable_stats()
            if not candidates:
                candidates = [ps for ps in self.explorer.known_stats() if ps.alive]
            if not candidates:
                candidates = self.explorer.known_stats()
            random.shuffle(candidates)
            self._pool = candidates[: self.slots]
            for ps in self._pool:
                ps.in_active_pool = True
        self._log_pool("INIT")

    def refresh(self) -> None:
        """Rotate weak pairs out, enforce drain timeout/cap, run eviction."""
        with self._lock:
            self._refresh_count += 1
            now = time.monotonic()

            # ── 1. Enforce drain timeout ───────────────────────────────
            # Any draining pair older than drain_timeout gets force-closed.
            for ps in list(self._draining):
                if ps.drain_age() >= self.drain_timeout:
                    ps.force_close()
                    # Leave it in _draining; it will be cleaned up below
                    # once active_connections reaches 0 (which happens
                    # immediately since force_close_event is now set and
                    # the forwarder will close sockets on the next relay
                    # iteration — typically within milliseconds).

            # ── 2. Clean up fully-drained pairs ───────────────────────
            still_draining: List[PairStats] = []
            for ps in self._draining:
                if ps.active_connections > 0 and not ps.force_close_event.is_set():
                    still_draining.append(ps)
                elif ps.active_connections > 0 and ps.force_close_event.is_set():
                    # Force-close has been issued; keep tracking until
                    # the forwarder catches the event and decrements.
                    still_draining.append(ps)
                else:
                    # No active connections — fully drained.
                    ps.in_active_pool = False
            self._draining = still_draining

            # ── 3. Move weak pairs from active pool to draining ────────
            weak = [
                ps for ps in self._pool
                if not ps.alive or ps.combined_loss_rate >= self.loss_threshold
            ]
            for ps in weak:
                self._pool.remove(ps)
                self._start_draining(ps)

            # ── 4. Fill empty slots ────────────────────────────────────
            in_use_ids = {id(ps) for ps in self._pool + self._draining}
            candidates = [
                ps for ps in self.explorer.stable_stats()
                if id(ps) not in in_use_ids
            ]
            if not candidates:
                candidates = [
                    ps for ps in self.explorer.known_stats()
                    if ps.alive and id(ps) not in in_use_ids
                ]

            needed = self.slots - len(self._pool)
            if needed > 0 and candidates:
                weights = [1.0 / (ps.combined_loss_rate + 0.01) for ps in candidates]
                chosen: List[PairStats] = []
                tc, tw = candidates[:], weights[:]
                for _ in range(min(needed, len(tc))):
                    pick = random.choices(tc, weights=tw, k=1)[0]
                    idx = tc.index(pick)
                    chosen.append(pick)
                    tc.pop(idx)
                    tw.pop(idx)
                for ps in chosen:
                    ps.in_active_pool = True
                    self._pool.append(ps)

            # ── 5. Periodic IP eviction ────────────────────────────────
            should_evict = (self._refresh_count % self.evict_every == 0)

        # Eviction runs outside the lock (it takes its own lock internally).
        if should_evict:
            protected = self._protected_ips()
            evicted_count = 0
            for _ in range(self.evict_count):
                evicted = self.explorer.evict_weakest_ip(
                    protected, scope=self.quarantine_scope
                )
                if not evicted:
                    break
                evicted_count += 1
                protected.discard(evicted)  # update so next iteration can evict a different IP
            if evicted_count:
                logger.info(
                    "Eviction cycle %d: removed %d IP(s) (scope=%s)",
                    self._refresh_count, evicted_count, self.quarantine_scope,
                )

        # ── 6. Periodic recycling of quarantined IPs ───────────────────
        # Randomly re-test a few evicted IPs; recovered ones are restored
        # to self.explorer.stats with fresh PairStats (no stale history).
        # This runs independently of eviction so recovery isn't tied to
        # the same cadence as removal.
        if self.recycle_enabled and (self._refresh_count % self.recycle_every == 0):
            recovered = self.explorer.recycle_attempt(
                batch=self.recycle_batch,
                min_cooldown=self.recycle_min_cooldown,
                max_quarantine=self.recycle_max_quarantine,
                scope=self.quarantine_scope,
            )
            if recovered:
                logger.info(
                    "Recycle cycle %d: restored %d IP(s) from quarantine (scope=%s)",
                    self._refresh_count, recovered, self.quarantine_scope,
                )

        self._log_pool("REFRESH")

    def _start_draining(self, ps: PairStats) -> None:
        """Move a pair into draining, enforcing the drain cap.

        Must be called while ``self._lock`` is held.
        """
        ps.start_draining()

        # Enforce drain cap — evict the oldest draining pair if needed.
        if len(self._draining) >= self.max_draining:
            # Sort by drain age descending; oldest is first.
            oldest = max(self._draining, key=lambda p: p.drain_age())
            logger.warning(
                "Drain cap (%d) reached — force-closing oldest pair %s/%s "
                "(age=%.0fs, active=%d)",
                self.max_draining, oldest.ip, oldest.sni,
                oldest.drain_age(), oldest.active_connections,
            )
            oldest.force_close()
            # It stays in _draining so cleanup above handles it.

        self._draining.append(ps)

    def _protected_ips(self) -> Set[str]:
        """Return the set of IPs that must not be evicted right now."""
        with self._lock:
            return {ps.ip for ps in self._pool + self._draining}

    # ------------------------------------------------------------------
    # Per-connection interface
    # ------------------------------------------------------------------

    def pick(self) -> PairStats:
        """Return the best pair for the next connection (weighted-random)."""
        with self._lock:
            pool = self._pool if self._pool else self.explorer.known_stats()
            if not pool:
                pool = self.explorer.all_stats()
            weights = [1.0 / (ps.combined_loss_rate + 0.01) for ps in pool]
            return random.choices(pool, weights=weights, k=1)[0]

    def report_failure(self, ps: PairStats) -> None:
        """Signal that a real connection on this pair failed mid-stream."""
        ps.record_probe(
            success=False,
            dead_threshold=self.explorer.dead_threshold,
        )
        if not ps.alive or ps.combined_loss_rate >= self.loss_threshold:
            self.refresh()

    # ------------------------------------------------------------------
    # Diagnostics
    # ------------------------------------------------------------------

    def _log_pool(self, reason: str) -> None:
        logger.info(
            "[Pool/%s] active=%d  draining=%d  (evict_cycle=%d/%d)",
            reason, len(self._pool), len(self._draining),
            self._refresh_count % self.evict_every, self.evict_every,
        )
        for ps in self._pool:
            logger.info(
                "  * %-18s %-25s  loss=%.1f%%  conns=%d",
                ps.ip, ps.sni,
                ps.combined_loss_rate * 100,
                ps.active_connections,
            )
        for ps in self._draining:
            fc = " FORCE-CLOSE" if ps.force_close_event.is_set() else ""
            logger.info(
                "  ~ %-18s  draining %.0fs/%ds  conns=%d%s",
                ps.ip, ps.drain_age(), self.drain_timeout,
                ps.active_connections, fc,
            )


# ---------------------------------------------------------------------------
# ConnectionManager
# ---------------------------------------------------------------------------

class ConnectionManager:
    """Facade that wires CombinationExplorer and ActivePool together.

    Usage in ``forwarder.py``::

        pair = manager.pick_pair()
        with pair.lock:
            pair.active_connections += 1
            pair.total_connections += 1
        try:
            # relay loop — also watch pair.force_close_event
            ...
        finally:
            with pair.lock:
                pair.active_connections = max(0, pair.active_connections - 1)
            if failed:
                manager.report_failure(pair)
    """

    def __init__(
        self,
        combinations: List[Tuple[str, str]],
        port: int,
        health_check_interval: float = 30.0,
        health_check_timeout: float = 3.0,
        probe_count: int = 5,
        active_slots: int = 3,
        loss_threshold: float = 0.20,
        dead_threshold: float = 0.80,
        drain_timeout: float = 30.0,
        max_draining: int = 5,
        evict_every: int = 3,
        evict_count: int = 2,
        recycle_enabled: bool = True,
        recycle_every: int = 6,
        recycle_batch: int = 2,
        recycle_min_cooldown: float = 180.0,
        recycle_max_quarantine: int = 100,
        quarantine_scope: str = "both",
    ) -> None:
        self.interval = health_check_interval

        self.explorer = CombinationExplorer(
            combinations=combinations,
            port=port,
            timeout=health_check_timeout,
            probe_count=probe_count,
            loss_threshold=loss_threshold,
            dead_threshold=dead_threshold,
        )
        self.pool = ActivePool(
            explorer=self.explorer,
            slots=active_slots,
            loss_threshold=loss_threshold,
            drain_timeout=drain_timeout,
            max_draining=max_draining,
            evict_every=evict_every,
            evict_count=evict_count,
            recycle_enabled=recycle_enabled,
            recycle_every=recycle_every,
            recycle_batch=recycle_batch,
            recycle_min_cooldown=recycle_min_cooldown,
            recycle_max_quarantine=recycle_max_quarantine,
            quarantine_scope=quarantine_scope,
        )

    # ------------------------------------------------------------------
    # Health loop
    # ------------------------------------------------------------------

    def run_health_loop(self) -> None:
        """Blocking health loop — call from a daemon thread."""
        self.explorer.initial_explore()
        self.pool.initialize()
        self.explorer.print_summary()

        while True:
            jitter = random.uniform(-5, 5)
            time.sleep(max(10, self.interval + jitter))

            self.explorer.periodic_explore()
            self.pool.refresh()
            self.explorer.print_summary()

    def start_health_loop(self) -> threading.Thread:
        t = threading.Thread(
            target=self.run_health_loop,
            name="snispf-health-loop",
            daemon=True,
        )
        t.start()
        logger.info("Connection manager health loop started.")
        return t

    # ------------------------------------------------------------------
    # Per-connection interface
    # ------------------------------------------------------------------

    def pick_pair(self) -> PairStats:
        return self.pool.pick()

    def report_failure(self, ps: PairStats) -> None:
        self.pool.report_failure(ps)


# ---------------------------------------------------------------------------
# Factory helper
# ---------------------------------------------------------------------------

def build_connection_manager(config: dict) -> Optional[ConnectionManager]:
    """Build a ConnectionManager from a config dict, or return None.

    Returns None when only a single IP/SNI is configured so the caller
    can fall back to the original direct-target code path.

    New config keys (all optional):
      DRAIN_TIMEOUT     float  Seconds before a draining pair is force-closed
                               (default: 30)
      MAX_DRAINING      int    Max simultaneous draining pairs (default: 5)
      EVICT_EVERY       int    Evict weakest IP every N health cycles (default: 3)
      QUARANTINE_SCOPE  str    Which IPs are eligible for eviction +
                               recycling: "static" (CONNECT_IPS only),
                               "dynamic" (discovery only), or "both"
                               (default: "both")
    """
    ips: List[str] = config.get("CONNECT_IPS", [])
    snis: List[str] = config.get("FAKE_SNIS", [])

    if not ips and config.get("CONNECT_IP"):
        ips = [config["CONNECT_IP"]]
    if not snis and config.get("FAKE_SNI"):
        snis = [config["FAKE_SNI"]]

    if not ips or not snis:
        logger.warning("No IPs or SNIs found in config — pool disabled.")
        return None

    if len(ips) == 1 and len(snis) == 1:
        logger.info("Single IP+SNI detected — pool disabled (using direct mode).")
        return None

    combinations: List[Tuple[str, str]] = [
        (ip, sni) for ip in ips for sni in snis
    ]
    logger.info(
        "Building connection pool: %d IP(s) × %d SNI(s) = %d pairs",
        len(ips), len(snis), len(combinations),
    )

    quarantine_scope = config.get("QUARANTINE_SCOPE", "both")
    if quarantine_scope not in ("static", "dynamic", "both"):
        logger.warning(
            "Invalid QUARANTINE_SCOPE %r — falling back to 'both'.",
            quarantine_scope,
        )
        quarantine_scope = "both"

    return ConnectionManager(
        combinations=combinations,
        port=config.get("CONNECT_PORT", 443),
        health_check_interval=config.get("HEALTH_CHECK_INTERVAL", 30),
        health_check_timeout=config.get("HEALTH_CHECK_TIMEOUT", 3),
        probe_count=config.get("PROBE_COUNT", 5),
        active_slots=config.get("ACTIVE_SLOTS", 3),
        loss_threshold=config.get("LOSS_THRESHOLD", 0.20),
        dead_threshold=config.get("DEAD_THRESHOLD", 0.80),
        drain_timeout=config.get("DRAIN_TIMEOUT", 30.0),
        max_draining=config.get("MAX_DRAINING", 5),
        evict_every=config.get("EVICT_EVERY", 3),
        evict_count=config.get("EVICT_COUNT", 2),
        recycle_enabled=config.get("RECYCLE_ENABLED", True),
        recycle_every=config.get("RECYCLE_EVERY", 6),
        recycle_batch=config.get("RECYCLE_BATCH", 2),
        recycle_min_cooldown=config.get("RECYCLE_MIN_COOLDOWN", 180.0),
        recycle_max_quarantine=config.get("RECYCLE_MAX_QUARANTINE", 100),
        quarantine_scope=quarantine_scope,
    )
