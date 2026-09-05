import time

import numpy as np

EPS = 1e-9


class DoubleClapDetector:
    """Detects a deliberate double clap from audio blocks.

    Each ``process_block`` call receives a mono audio block (float in [-1, 1]).
    The detector looks for two short, loud transients separated by a quiet gap:

        clap → quiet → clap

    The quiet-gap requirement is the main false-positive guard: sustained
    loud sound (applause, music, TV) rarely dips below ``quiet_threshold_db``,
    so it does not read as a double clap.
    """

    def __init__(
        self,
        sample_rate: int = 44100,
        block_ms: int = 20,
        clap_threshold_db: float = -14.0,
        quiet_threshold_db: float = -38.0,
        min_gap_ms: int = 80,
        max_interval_ms: int = 400,
        post_trigger_cooldown_ms: int = 8000,
        now: callable = time.monotonic,
    ) -> None:
        self.sample_rate = sample_rate
        self.block_seconds = block_ms / 1000.0
        self.clap_threshold_db = clap_threshold_db
        self.quiet_threshold_db = quiet_threshold_db
        self.min_gap_s = min_gap_ms / 1000.0
        self.max_interval_s = max_interval_ms / 1000.0
        self.post_trigger_cooldown_s = post_trigger_cooldown_ms / 1000.0
        self._now = now

        # State
        self.first_clap_at: float | None = None
        self.quiet_began_at: float | None = None
        self.last_trigger_at: float = -1e9
        self.trigger_count = 0

    @staticmethod
    def peak_db(block: np.ndarray) -> float:
        peak = float(np.max(np.abs(block)))
        return 20.0 * np.log10(peak + EPS)

    def process_block(self, block: np.ndarray, timestamp: float | None = None) -> bool:
        """Feed one audio block; returns True if a double clap fired."""
        t = self._now() if timestamp is None else timestamp
        peak = float(np.max(np.abs(block)))
        peak_db = 20.0 * np.log10(peak + EPS)

        if t - self.last_trigger_at < self.post_trigger_cooldown_s:
            return False

        is_loud = peak_db >= self.clap_threshold_db
        is_quiet = peak_db <= self.quiet_threshold_db

        # Forget a pending first clap once it's too old.
        if self.first_clap_at is not None and t - self.first_clap_at > self.max_interval_s:
            self.first_clap_at = None
            self.quiet_began_at = None

        # Track a quiet stretch that begins after the first clap.
        if self.first_clap_at is not None and is_quiet:
            if self.quiet_began_at is None:
                self.quiet_began_at = t
            return False

        # A loud block that follows a sufficiently long quiet gap is the second clap.
        if (
            self.first_clap_at is not None
            and is_loud
            and self.quiet_began_at is not None
            and t - self.quiet_began_at >= self.min_gap_s
        ):
            self._fire(t)
            return True

        # Loud block with no pending first clap starts a candidate double clap.
        if is_loud and self.first_clap_at is None:
            self.first_clap_at = t
            self.quiet_began_at = None

        return False

    def _fire(self, t: float) -> None:
        self.first_clap_at = None
        self.quiet_began_at = None
        self.last_trigger_at = t
        self.trigger_count += 1


def detector_from_config(cfg) -> DoubleClapDetector:
    return DoubleClapDetector(
        sample_rate=cfg.sample_rate,
        block_ms=cfg.block_ms,
        clap_threshold_db=cfg.clap_threshold_db,
        quiet_threshold_db=cfg.quiet_threshold_db,
        min_gap_ms=cfg.min_gap_ms,
        max_interval_ms=cfg.max_interval_ms,
        post_trigger_cooldown_ms=cfg.post_trigger_cooldown_ms,
    )