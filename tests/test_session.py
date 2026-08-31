"""Tests for session.py: capture() and watch().

Timing (idle_gap_seconds, cooldown_seconds) is driven by a FakeClock rather
than real wall-clock time, so these tests are deterministic - measured that
the equivalent real-time tests can flake under a single slow tick.
"""

import json
import threading
from datetime import datetime

import hid
import pytest

import epad_signature_pad_hid_driver.session as session_module
from epad_signature_pad_hid_driver.exceptions import PadNotFoundError
from epad_signature_pad_hid_driver.protocol import PenSample
from epad_signature_pad_hid_driver.session import WatchResult, capture, watch
from tests.helpers import FakeClock, FakePad, RaisingPad, raw_report


def _install_clock(monkeypatch: pytest.MonkeyPatch, clock: FakeClock) -> None:
    monkeypatch.setattr(session_module, "_now", clock.now)
    monkeypatch.setattr(session_module, "_sleep", clock.sleep)


# ---- capture() ----


def test_capture_reads_reports_from_pad(monkeypatch: pytest.MonkeyPatch) -> None:
    clock = FakeClock()
    _install_clock(monkeypatch, clock)
    reports = [
        raw_report(x=10, y=20, pressure=50, touch=True),
        raw_report(x=15, y=25, pressure=60, touch=True),
        raw_report(x=20, y=30, pressure=70, touch=True),
    ]
    monkeypatch.setattr(hid, "device", lambda: FakePad(reports, clock=clock))

    samples: list[PenSample] = []
    count = capture(0.05, samples.append)

    assert count == 3
    assert [s.x for s in samples] == [10, 15, 20]
    assert [s.y for s in samples] == [20, 25, 30]
    assert all(s.touch for s in samples)


def test_capture_returns_zero_when_no_reports(monkeypatch: pytest.MonkeyPatch) -> None:
    clock = FakeClock()
    _install_clock(monkeypatch, clock)
    monkeypatch.setattr(hid, "device", lambda: FakePad([], clock=clock))

    count = capture(0.03, lambda s: None)

    assert count == 0


def test_capture_closes_pad_even_on_error(monkeypatch: pytest.MonkeyPatch) -> None:
    clock = FakeClock()
    _install_clock(monkeypatch, clock)
    pad = FakePad(
        [raw_report(x=1, y=2, pressure=3, touch=True)],
        raise_when_exhausted=RuntimeError,
        clock=clock,
    )
    monkeypatch.setattr(hid, "device", lambda: pad)

    with pytest.raises(RuntimeError):
        capture(1.0, lambda s: None)

    assert pad.closed is True


def test_capture_passes_custom_ids_through(monkeypatch: pytest.MonkeyPatch) -> None:
    clock = FakeClock()
    _install_clock(monkeypatch, clock)
    pad = FakePad([], clock=clock)
    monkeypatch.setattr(hid, "device", lambda: pad)

    capture(0.01, lambda s: None, vendor_id=0x1111, product_id=0x2222)

    assert pad.opened_with == (0x1111, 0x2222)


def test_capture_ignores_short_reads(monkeypatch: pytest.MonkeyPatch) -> None:
    """A short read used to crash mid-capture with IndexError; it must now
    just be skipped, the same way an empty read already is."""
    clock = FakeClock()
    _install_clock(monkeypatch, clock)
    reports = [
        bytes([0, 1, 2]),  # short - must be ignored, not crash
        raw_report(x=5, y=6, pressure=7, touch=True),
    ]
    monkeypatch.setattr(hid, "device", lambda: FakePad(reports, clock=clock))

    samples: list[PenSample] = []
    count = capture(0.05, samples.append)

    assert count == 1
    assert samples[0].x == 5


def test_capture_raises_pad_not_found_when_pad_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(hid, "device", lambda: RaisingPad(OSError("open failed")))

    with pytest.raises(PadNotFoundError):
        capture(1.0, lambda s: None)


# ---- watch() ----


def test_watch_keeps_recording_through_pen_lifts(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    clock = FakeClock()
    _install_clock(monkeypatch, clock)
    reports = [
        raw_report(x=10, y=10, pressure=50, touch=True),
        raw_report(x=12, y=12, pressure=50, touch=True),
        raw_report(x=12, y=12, pressure=0, touch=False),  # pen lifts mid-signature
        raw_report(x=20, y=20, pressure=50, touch=True),  # pen touches down again
    ]
    monkeypatch.setattr(hid, "device", lambda: FakePad(reports, clock=clock))

    watch_gen = watch(tmp_path, idle_gap_seconds=0.05, cooldown_seconds=0.01)
    result = next(watch_gen)
    watch_gen.close()

    assert len(result.samples) == 4
    assert result.samples[2].touch is False
    assert result.samples[3].touch is True
    assert result.truncated is False


def test_watch_writes_all_three_files(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    clock = FakeClock()
    _install_clock(monkeypatch, clock)
    reports = [raw_report(x=1, y=2, pressure=10, touch=True)]
    monkeypatch.setattr(hid, "device", lambda: FakePad(reports, clock=clock))

    watch_gen = watch(tmp_path, idle_gap_seconds=0.03, cooldown_seconds=0.01)
    result = next(watch_gen)
    watch_gen.close()

    assert result.png_path.exists()
    assert result.json_path.exists()
    assert result.inkml_path.exists()


def test_watch_stop_via_event(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    clock = FakeClock()
    _install_clock(monkeypatch, clock)
    monkeypatch.setattr(hid, "device", lambda: FakePad([], clock=clock))
    stop = threading.Event()
    stop.set()

    results = list(watch(tmp_path, stop=stop))

    assert results == []


def test_watch_stop_via_callable(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    clock = FakeClock()
    _install_clock(monkeypatch, clock)
    monkeypatch.setattr(hid, "device", lambda: FakePad([], clock=clock))

    results = list(watch(tmp_path, stop=lambda: True))

    assert results == []


def test_watch_stop_before_first_touch_saves_nothing(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    clock = FakeClock()
    _install_clock(monkeypatch, clock)
    monkeypatch.setattr(hid, "device", lambda: FakePad([], clock=clock))
    calls = {"n": 0}

    def stop_after_a_few_polls() -> bool:
        calls["n"] += 1
        return calls["n"] > 3

    results = list(watch(tmp_path, stop=stop_after_a_few_polls))

    assert results == []
    assert list(tmp_path.iterdir()) == []


def test_watch_stop_mid_session_saves_and_marks_truncated(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    clock = FakeClock()
    _install_clock(monkeypatch, clock)
    reports = [
        raw_report(x=1, y=1, pressure=10, touch=True),
        raw_report(x=2, y=2, pressure=10, touch=True),
    ]
    monkeypatch.setattr(hid, "device", lambda: FakePad(reports, clock=clock))
    calls = {"n": 0}

    def stop_after_two_reads() -> bool:
        calls["n"] += 1
        return calls["n"] > 3  # lets the trigger + one more read through first

    results = list(watch(tmp_path, idle_gap_seconds=10.0, stop=stop_after_two_reads))

    assert len(results) == 1
    result = results[0]
    assert result.truncated is True
    assert "_partial" in result.png_path.name
    document = json.loads(result.json_path.read_text())
    assert document["truncated"] is True


def test_watch_stop_checked_during_cooldown(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A long cooldown must not swallow a stop request in one big sleep -
    checked by making cooldown deliberately huge (100s) and confirming the
    generator ends well before that much fake time has passed."""
    clock = FakeClock()
    _install_clock(monkeypatch, clock)
    reports = [raw_report(x=1, y=1, pressure=10, touch=True)]
    monkeypatch.setattr(hid, "device", lambda: FakePad(reports, clock=clock))
    stop = threading.Event()

    watch_gen = watch(
        tmp_path, idle_gap_seconds=0.02, cooldown_seconds=100.0, stop=stop
    )
    first = next(watch_gen)
    stop.set()

    with pytest.raises(StopIteration):
        next(watch_gen)

    assert first.truncated is False
    assert clock.time < 100.0


def test_watch_stop_callable_that_raises_propagates(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    clock = FakeClock()
    _install_clock(monkeypatch, clock)
    pad = FakePad([], clock=clock)
    monkeypatch.setattr(hid, "device", lambda: pad)

    def bad_stop() -> bool:
        raise RuntimeError("stop callable blew up")

    with pytest.raises(RuntimeError, match="blew up"):
        list(watch(tmp_path, stop=bad_stop))

    assert pad.closed is True


def test_watch_closes_pad_when_started_generator_is_closed(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    clock = FakeClock()
    _install_clock(monkeypatch, clock)
    reports = [raw_report(x=1, y=1, pressure=10, touch=True)]
    pad = FakePad(reports, clock=clock)
    monkeypatch.setattr(hid, "device", lambda: pad)

    watch_gen = watch(tmp_path, idle_gap_seconds=0.02, cooldown_seconds=100.0)
    next(watch_gen)
    watch_gen.close()

    assert pad.closed is True


def test_watch_unstarted_generator_opens_nothing(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Closing a generator before its first next() runs nothing - not even
    `finally` - since the function body has not started executing yet."""
    opened = {"count": 0}

    def make_pad() -> FakePad:
        opened["count"] += 1
        return FakePad([])

    monkeypatch.setattr(hid, "device", make_pad)

    watch_gen = watch(tmp_path)
    watch_gen.close()

    assert opened["count"] == 0


def test_timestamp_slug_format() -> None:
    from epad_signature_pad_hid_driver.session import _timestamp_slug

    slug = _timestamp_slug(datetime(2026, 8, 31, 22, 45, 12, 123000))

    assert slug == "20260831T224512_123"


def test_timestamp_slug_is_sortable_by_time() -> None:
    from epad_signature_pad_hid_driver.session import _timestamp_slug

    earlier = _timestamp_slug(datetime(2026, 8, 31, 22, 45, 12, 0))
    later = _timestamp_slug(datetime(2026, 8, 31, 22, 45, 13, 0))

    assert earlier < later


@pytest.mark.parametrize("dummy", [WatchResult])
def test_watch_result_is_importable(dummy: object) -> None:
    assert dummy is WatchResult
