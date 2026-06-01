"""Multi-IP / Multi-SNI connection pool with adaptive health tracking.

This module ports the core ideas from SNI-Spoofing-HJ (by @hjfisher /
@patterniha) into SNISPF's architecture:

  - PairStats   — tracks probe loss and real-traffic loss for one (IP, SNI) pair
  - CombinationExplorer — gradually discovers and health-checks the full
                          cartesian product of IPs × SNIs
  - ActivePool  — keeps ACTIVE_SLOTS pairs warm; drains weak pairs gracefully
                  without killing live connections
  - ConnectionManager — ties everything together with a background health loop

The pool integrates with SNISPF's existing ``forwarder.py`` via the
``ConnectionManager.pick_pair()`` / ``ConnectionManager.report_failure()``
interface.  The forwarder calls ``pick_pair()`` for each new connection and
``report_failure()`` when the upstream connection drops unexpectedly.
"""

from __future__ import annotations

import logging
import random
import socket
import threading
import time
from typing import Dict, List, Optional, Tuple

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
    """

    # Minimum probe count before we treat the loss rate as meaningful.
    MIN_PROBES: int = 3

    def __init__(self, ip: str, sni: str) -> None:
        self.ip: str = ip
        self.sni: str = sni

        self.probes_sent: int = 0
        self.probes_recv: int = 0
        self.real_packets_sent: int = 0
        self.real_packets_lost: int = 0

        self.active_connections: int = 0
        self.total_connections: int = 0
        self.alive: bool = True
        # Has this pair been probed at least once?
        self.probed: bool = False
        # Is this pair currently in the active pool?
        self.in_active_pool: bool = False

        self.lock = threading.Lock()

    # ------------------------------------------------------------------
    # Computed properties
    # ------------------------------------------------------------------

    @property
    def probe_loss_rate(self) -> float:
        """Fraction of probes that received no response."""
        if self.probes_sent < self.MIN_PROBES:
            return 0.0
        return (self.probes_sent - self.probes_recv) / self.probes_sent

    @property
    def real_loss_rate(self) -> float:
        """Fraction of real forwarded packets that were lost mid-stream."""
        if self.real_packets_sent == 0:
            return 0.0
        return self.real_packets_lost / self.real_packets_sent

    @property
    def combined_loss_rate(self) -> float:
        """Blended loss rate: 70 % real + 30 % probe once real data exist."""
        if self.real_packets_sent > 10:
            return 0.7 * self.real_loss_rate + 0.3 * self.probe_loss_rate
        return self.probe_loss_rate

    @property
    def score(self) -> float:
        """Lower is better.

        - Dead pairs return +inf so they are always ranked last.
        - Unknown (not yet probed) pairs return 0.5 to give them a chance.
        - Otherwise the combined loss rate is returned directly.
        """
        if not self.alive:
            return float("inf")
        if not self.probed:
            return 0.5          # unknown — eligible for first probe
        return self.combined_loss_rate

    @property
    def is_stable(self) -> bool:
        """True when the pair is alive, tested, and below the loss threshold."""
        # The threshold is read from the owning CombinationExplorer at
        # runtime; here we just expose the raw values and let the explorer
        # apply its threshold when querying.
        return self.alive and self.probed

    # ------------------------------------------------------------------
    # Mutation helpers (thread-safe)
    # ------------------------------------------------------------------

    def record_probe(self, success: bool, dead_threshold: float = 0.80) -> None:
        """Update probe counters and flip ``alive`` if needed."""
        with self.lock:
            self.probes_sent += 1
            self.probed = True
            if success:
                self.probes_recv += 1
            if self.probes_sent >= self.MIN_PROBES:
                loss = (self.probes_sent - self.probes_recv) / self.probes_sent
                if loss >= dead_threshold:
                    self.alive = False
                elif self.probes_recv > 0:
                    self.alive = True

    def record_real_packet(self, lost: bool) -> None:
        """Update real-traffic counters for a forwarded connection."""
        with self.lock:
            self.real_packets_sent += 1
            if lost:
                self.real_packets_lost += 1

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

    Instead of probing all N×M combinations at startup (which would be slow
    and noisy), the explorer works in stages:

    1. **Initial batch** — probes a random sample of ``INITIAL_SAMPLE`` pairs
       to populate the pool quickly.
    2. **Periodic cycles** — re-verifies the top ``VERIFY_TOP`` known pairs
       and explores ``EXPLORE_BATCH`` new ones.
    3. **Reshuffle** — when all combinations have been explored at least once,
       the unexplored queue is reshuffled and the cycle restarts.

    Probes are simple TCP connect attempts (no TLS).  A successful TCP
    three-way handshake means the IP is reachable on the target port.
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

        # Build a stats object for every (ip, sni) pair.
        self.stats: Dict[Tuple[str, str], PairStats] = {
            (ip, sni): PairStats(ip, sni)
            for ip, sni in combinations
        }

        # Queue of unexplored pairs, shuffled for randomness.
        self._unexplored: List[Tuple[str, str]] = list(combinations)
        random.shuffle(self._unexplored)
        self._lock = threading.Lock()

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
        """Return pairs that have been probed at least once."""
        return [ps for ps in self.stats.values() if ps.probed]

    def stable_stats(self) -> List[PairStats]:
        """Return pairs that are alive, probed, and below the loss threshold."""
        return [
            ps for ps in self.known_stats()
            if ps.alive and ps.combined_loss_rate < self.loss_threshold
        ]

    # ------------------------------------------------------------------
    # Internal probing helpers
    # ------------------------------------------------------------------

    def _probe_one(self, ps: PairStats) -> None:
        """Run ``probe_count`` TCP connect probes against one pair."""
        # Randomise the count slightly to avoid perfectly synchronised bursts.
        count = max(2, self.probe_count + random.randint(-1, 1))
        for _ in range(count):
            try:
                sock = socket.create_connection(
                    (ps.ip, self.port), timeout=self.timeout
                )
                sock.close()
                ps.record_probe(success=True, dead_threshold=self.dead_threshold)
            except Exception:
                ps.record_probe(success=False, dead_threshold=self.dead_threshold)
            time.sleep(random.uniform(0.05, 0.2))

    def _run_probes_parallel(self, pairs: List[PairStats]) -> None:
        """Probe a list of pairs in parallel threads."""
        random.shuffle(pairs)
        threads = [
            threading.Thread(target=self._probe_one, args=(ps,), daemon=True)
            for ps in pairs
        ]
        for t in threads:
            t.start()
            time.sleep(random.uniform(0, 0.03))  # stagger thread starts
        for t in threads:
            t.join()

    # ------------------------------------------------------------------
    # Exploration lifecycle
    # ------------------------------------------------------------------

    def initial_explore(self) -> None:
        """Probe the initial random sample to bootstrap the pool."""
        with self._lock:
            batch_keys = self._unexplored[: self.INITIAL_SAMPLE]
            self._unexplored = self._unexplored[self.INITIAL_SAMPLE :]
        batch = [self.stats[k] for k in batch_keys]
        logger.info("Initial probe: %d combinations ...", len(batch))
        self._run_probes_parallel(batch)

    def periodic_explore(self) -> None:
        """Re-verify top known pairs and discover a new batch of unknowns."""
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

        if batch_keys:
            batch = [self.stats[k] for k in batch_keys]
            logger.debug(
                "Exploring %d new combinations (%d remaining) ...",
                len(batch), remaining,
            )
            self._run_probes_parallel(batch)
        else:
            # All combinations explored — reshuffle for the next cycle.
            logger.info(
                "All combinations explored — reshuffling for next cycle."
            )
            with self._lock:
                all_keys = list(self.stats.keys())
                random.shuffle(all_keys)
                self._unexplored = all_keys

    # ------------------------------------------------------------------
    # Diagnostics
    # ------------------------------------------------------------------

    def print_summary(self) -> None:
        """Log a ranked summary of known (IP, SNI) pairs."""
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
                "  %s %-20s %-25s  loss=%.1f%%  active=%d",
                marker, ps.ip, ps.sni,
                ps.combined_loss_rate * 100,
                ps.active_connections,
            )


# ---------------------------------------------------------------------------
# ActivePool
# ---------------------------------------------------------------------------

class ActivePool:
    """Maintains ACTIVE_SLOTS stable (IP, SNI) pairs for serving connections.

    Rules:
    - Always tries to keep ``slots`` pairs in the active set.
    - Pairs whose combined_loss_rate exceeds ``loss_threshold`` are moved to
      a *draining* list: existing connections finish normally, but no new
      ones are assigned to them.
    - Replacement pairs are selected with weighted-random sampling (lower
      loss = higher weight) so the best pairs are preferred without being
      deterministically sticky.
    - No live connection is ever forcefully terminated.
    """

    def __init__(
        self,
        explorer: CombinationExplorer,
        slots: int,
        loss_threshold: float = 0.20,
    ) -> None:
        self.explorer = explorer
        self.slots = slots
        self.loss_threshold = loss_threshold
        self._pool: List[PairStats] = []
        self._draining: List[PairStats] = []
        self._lock = threading.Lock()

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def initialize(self) -> None:
        """Populate the initial active set from whatever the explorer knows."""
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
        """Rotate weak pairs out and fill empty slots with the best available."""
        with self._lock:
            # Free drained pairs that have no more active connections.
            still_draining: List[PairStats] = []
            for ps in self._draining:
                if ps.active_connections > 0:
                    still_draining.append(ps)
                else:
                    ps.in_active_pool = False
            self._draining = still_draining

            # Move pairs that are now above the loss threshold to draining.
            weak = [
                ps for ps in self._pool
                if not ps.alive or ps.combined_loss_rate >= self.loss_threshold
            ]
            for ps in weak:
                self._pool.remove(ps)
                self._draining.append(ps)

            # Fill empty slots with the best stable alternatives.
            in_use_ids = {id(ps) for ps in self._pool + self._draining}
            candidates = [
                ps for ps in self.explorer.stable_stats()
                if id(ps) not in in_use_ids
            ]
            if not candidates:
                # Fall back to any alive pair we haven't already assigned.
                candidates = [
                    ps for ps in self.explorer.known_stats()
                    if ps.alive and id(ps) not in in_use_ids
                ]

            needed = self.slots - len(self._pool)
            if needed > 0 and candidates:
                # Weighted-random selection: lower loss → higher weight.
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

        self._log_pool("REFRESH")

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
        """Signal that a real connection on this pair failed mid-stream.

        Records a probe failure so the loss rate rises, then refreshes the
        pool if the pair is now above the threshold.
        """
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
            "[Pool/%s] active=%d  draining=%d",
            reason, len(self._pool), len(self._draining),
        )
        for ps in self._pool:
            logger.info(
                "  * %-18s %-25s  loss=%.1f%%  conns=%d",
                ps.ip, ps.sni,
                ps.combined_loss_rate * 100,
                ps.active_connections,
            )
        for ps in self._draining:
            logger.info(
                "  ~ %-18s  draining ...  conns=%d",
                ps.ip, ps.active_connections,
            )


# ---------------------------------------------------------------------------
# ConnectionManager
# ---------------------------------------------------------------------------

class ConnectionManager:
    """Facade that wires CombinationExplorer and ActivePool together.

    Usage in ``forwarder.py``::

        pair = manager.pick_pair()
        # ... use pair.ip and pair.sni for this connection ...
        with pair.lock:
            pair.active_connections += 1
        try:
            # ... relay data ...
        finally:
            with pair.lock:
                pair.active_connections -= 1
            if connection_failed:
                manager.report_failure(pair)

    The health loop runs in a daemon thread and must be started before the
    first call to ``pick_pair()``.
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
        )

    # ------------------------------------------------------------------
    # Health loop (run in a daemon thread)
    # ------------------------------------------------------------------

    def run_health_loop(self) -> None:
        """Blocking health loop — call from a daemon thread."""
        # Bootstrap: probe an initial sample, then populate the pool.
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
        """Start the health loop in a background daemon thread and return it."""
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
        """Pick the best (IP, SNI) pair for the next outbound connection."""
        return self.pool.pick()

    def report_failure(self, ps: PairStats) -> None:
        """Notify the pool that a connection on ``ps`` failed."""
        self.pool.report_failure(ps)


# ---------------------------------------------------------------------------
# Factory helper
# ---------------------------------------------------------------------------

def build_connection_manager(config: dict) -> Optional[ConnectionManager]:
    """Build a ConnectionManager from a config dict, or return None.

    Returns ``None`` when the config only specifies a single IP / SNI (i.e.
    the legacy ``CONNECT_IP`` / ``FAKE_SNI`` keys) so the caller can fall
    back to the original single-target code path.

    The config may contain either:
    - ``CONNECT_IPS``  — list of upstream IP strings
    - ``FAKE_SNIS``    — list of fake SNI strings
    (the new multi-target format from SNI-Spoofing-HJ)

    or the legacy single-target keys:
    - ``CONNECT_IP``
    - ``FAKE_SNI``

    If *both* ``CONNECT_IPS`` and ``FAKE_SNIS`` are present the full
    cartesian product is used.
    """
    ips: List[str] = config.get("CONNECT_IPS", [])
    snis: List[str] = config.get("FAKE_SNIS", [])

    # Accept both plural (new) and singular (legacy) keys.
    if not ips and config.get("CONNECT_IP"):
        ips = [config["CONNECT_IP"]]
    if not snis and config.get("FAKE_SNI"):
        snis = [config["FAKE_SNI"]]

    if not ips or not snis:
        logger.warning(
            "No IPs or SNIs found in config — pool disabled."
        )
        return None

    if len(ips) == 1 and len(snis) == 1:
        # Single-pair: pool adds overhead with no benefit.
        logger.info(
            "Single IP+SNI detected — pool disabled (using direct mode)."
        )
        return None

    # Build cartesian product.
    combinations: List[Tuple[str, str]] = [
        (ip, sni) for ip in ips for sni in snis
    ]
    logger.info(
        "Building connection pool: %d IP(s) × %d SNI(s) = %d pairs",
        len(ips), len(snis), len(combinations),
    )

    return ConnectionManager(
        combinations=combinations,
        port=config.get("CONNECT_PORT", 443),
        health_check_interval=config.get("HEALTH_CHECK_INTERVAL", 30),
        health_check_timeout=config.get("HEALTH_CHECK_TIMEOUT", 3),
        probe_count=config.get("PROBE_COUNT", 5),
        active_slots=config.get("ACTIVE_SLOTS", 3),
        loss_threshold=config.get("LOSS_THRESHOLD", 0.20),
        dead_threshold=config.get("DEAD_THRESHOLD", 0.80),
    )
