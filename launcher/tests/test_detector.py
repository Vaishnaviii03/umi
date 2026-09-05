import numpy as np

from detector import DoubleClapDetector


def _clap(peak_db, sample_rate=44100, seconds=0.04):
    n = int(sample_rate * seconds)
    amp = 10 ** (float(peak_db) / 20.0)
    t = np.arange(n) / sample_rate
    return (amp * np.sin(2 * np.pi * 220 * t)).astype(np.float32)


def _quiet(amp=0.001, sample_rate=44100, seconds=0.04):
    n = int(sample_rate * seconds)
    return (amp * np.random.uniform(-1, 1, n)).astype(np.float32)


class Time:
    def __init__(self):
        self.t = 0.0

    def __call__(self):
        return self.t

    def advance(self, dt):
        self.t += dt


def make_detector(**kw):
    defaults = dict(
        sample_rate=44100,
        block_ms=20,
        clap_threshold_db=-18.0,
        quiet_threshold_db=-40.0,
        min_gap_ms=80,
        max_interval_ms=400,
        post_trigger_cooldown_ms=8000,
    )
    defaults.update(kw)
    return DoubleClapDetector(**defaults), Time()


def feed_quiet(clock, det, seconds, step=0.02):
    triggered = False
    steps = int(seconds / step)
    for _ in range(steps):
        clock.advance(step)
        triggered = triggered or det.process_block(_quiet(), timestamp=clock())
    return triggered


def test_quiet_blocks_do_not_trigger():
    det, clock = make_detector()
    triggered = feed_quiet(clock, det, 5.0)
    assert not triggered
    assert det.trigger_count == 0


def test_single_clap_does_not_trigger():
    det, clock = make_detector()
    det.process_block(_clap(-10), timestamp=clock())
    feed_quiet(clock, det, 1.0)
    assert det.trigger_count == 0


def test_double_clap_triggers():
    det, clock = make_detector(min_gap_ms=40)
    # first clap at t=0
    out = det.process_block(_clap(-12), timestamp=clock())
    assert not out
    # ~100ms quiet gap
    feed_quiet(clock, det, 0.1)
    # second clap
    out = det.process_block(_clap(-12), timestamp=clock())
    assert out
    assert det.trigger_count == 1


def test_sustained_loud_does_not_trigger():
    det, clock = make_detector()
    triggered = False
    loud = _clap(-12)
    for _ in range(150):
        clock.advance(0.02)
        if det.process_block(loud, timestamp=clock()):
            triggered = True
    assert not triggered


def test_claps_too_quick_do_not_trigger():
    det, clock = make_detector(min_gap_ms=100)
    det.process_block(_clap(-12), timestamp=clock())
    clock.advance(0.02)  # no quiet gap
    out = det.process_block(_clap(-12), timestamp=clock())
    assert not out
    assert det.trigger_count == 0


def test_claps_too_far_apart_do_not_trigger():
    det, clock = make_detector(max_interval_ms=200)
    det.process_block(_clap(-12), timestamp=clock())
    feed_quiet(clock, det, 0.6)  # exceeds max interval -> first clap forgotten
    out = det.process_block(_clap(-12), timestamp=clock())
    assert not out
    assert det.trigger_count == 0