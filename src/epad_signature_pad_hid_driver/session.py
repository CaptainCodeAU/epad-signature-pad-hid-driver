"""The capture()/watch() recording loops, built on protocol.py + device.py."""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Callable, Iterator

from epad_signature_pad_hid_driver.device import PadHandle, open_pad
from epad_signature_pad_hid_driver.protocol import (
    PRODUCT_ID,
    REPORT_LENGTH,
    VENDOR_ID,
    PenSample,
    decode_report,
)

# Swappable indirections onto time.monotonic/time.sleep, so tests can
# monkeypatch these two names to a fake clock instead of waiting on real
# wall-clock time. Never call time.monotonic()/time.sleep() directly below
# this line - always go through _now()/_sleep().
_now: Callable[[], float] = time.monotonic
_sleep: Callable[[float], None] = time.sleep


def _stop_requested(stop: threading.Event | Callable[[], bool] | None) -> bool:
    """True if `stop` says to stop. `stop` is a threading.Event, a
    zero-argument callable, or None (never stop). A callable that raises
    is allowed to propagate - callers must not make it raise unless they
    want that to end the watch() loop with that exception."""
    if stop is None:
        return False
    if isinstance(stop, threading.Event):
        return stop.is_set()
    return stop()


def capture(
    seconds: float,
    on_sample: Callable[[PenSample], None],
    *,
    vendor_id: int = VENDOR_ID,
    product_id: int = PRODUCT_ID,
) -> int:
    """Read from the pad for the given duration, calling on_sample for each report.

    Each sample's t is seconds since this call started. Returns the number
    of reports received. A report shorter than REPORT_LENGTH bytes is
    ignored, the same way an empty read already is.
    """
    d = open_pad(vendor_id, product_id)
    count = 0
    start = _now()
    deadline = start + seconds
    try:
        while _now() < deadline:
            report = d.read(REPORT_LENGTH, timeout_ms=50)
            if report and len(report) >= REPORT_LENGTH:
                on_sample(decode_report(bytes(report), t=_now() - start))
                count += 1
    finally:
        d.close()
    return count


def _timestamp_slug(moment: datetime) -> str:
    """A sortable, unique-enough-for-this-use filename fragment, e.g. 20260831T224512_123."""
    return moment.strftime("%Y%m%dT%H%M%S_") + f"{moment.microsecond // 1000:03d}"


@dataclass
class WatchResult:
    """One completed capture from watch(): where it saved, and the raw samples.

    truncated is True when a `stop` request cut the session short before
    idle_gap_seconds of no touching was reached - the saved files are real
    and complete up to that point, but are marked (filename, JSON field,
    and an InkML annotation) so they can never be mistaken for a signature
    that finished naturally.
    """

    png_path: Path
    json_path: Path
    inkml_path: Path
    samples: list[PenSample] = field(default_factory=list)
    truncated: bool = False


def _wait_for_touch(
    d: PadHandle, stop: threading.Event | Callable[[], bool] | None
) -> PenSample | None:
    """Block until a touching sample arrives, or `stop` fires first (None)."""
    while True:
        if _stop_requested(stop):
            return None
        report = d.read(REPORT_LENGTH, timeout_ms=50)
        if report and len(report) >= REPORT_LENGTH:
            sample = decode_report(bytes(report))
            if sample.touch:
                return sample


def _record_session(
    d: PadHandle,
    trigger: PenSample,
    idle_gap_seconds: float,
    stop: threading.Event | Callable[[], bool] | None,
) -> tuple[list[PenSample], bool]:
    """Record until idle_gap_seconds of no touching, or `stop` fires first.

    Returns (samples, truncated). truncated is True only when `stop` cut
    the session short - idle timeout is a normal, non-truncated ending.
    """
    session_start_mono = _now()
    trigger.t = 0.0
    samples = [trigger]
    last_touch_mono = session_start_mono
    while _now() - last_touch_mono < idle_gap_seconds:
        if _stop_requested(stop):
            return samples, True
        report = d.read(REPORT_LENGTH, timeout_ms=50)
        if report and len(report) >= REPORT_LENGTH:
            now = _now()
            sample = decode_report(bytes(report), t=now - session_start_mono)
            samples.append(sample)
            if sample.touch:
                last_touch_mono = now
    return samples, False


def _run_cooldown(
    cooldown_seconds: float, stop: threading.Event | Callable[[], bool] | None
) -> bool:
    """Sleep out cooldown_seconds in short slices. Returns True if `stop`
    fired during the wait (checked every slice, not just once at the end -
    otherwise a long cooldown would swallow a stop request in one sleep)."""
    cooldown_deadline = _now() + cooldown_seconds
    slice_seconds = 0.05
    while _now() < cooldown_deadline:
        if _stop_requested(stop):
            return True
        remaining = cooldown_deadline - _now()
        _sleep(min(slice_seconds, remaining))
    return False


def watch(
    output_dir: Path,
    idle_gap_seconds: float = 3.0,
    cooldown_seconds: float = 2.0,
    *,
    stop: threading.Event | Callable[[], bool] | None = None,
    vendor_id: int = VENDOR_ID,
    product_id: int = PRODUCT_ID,
) -> Iterator[WatchResult]:
    """Wait for a pen touch, record until idle_gap_seconds of no touching, save, repeat.

    A pen-down starts a session; it keeps recording through pen lifts (e.g.
    between letters) and only ends once idle_gap_seconds pass with no touch
    at all. The session is then saved as a PNG plus JSON and InkML data
    files, timestamped so runs never collide or run out of numbers, and
    this pauses for cooldown_seconds before listening again. Runs until the
    caller stops iterating (e.g. on KeyboardInterrupt, which still works
    exactly as before), or until `stop` (a threading.Event, or a
    zero-argument callable checked each loop) says to stop.

    The pad is opened only on the first next() call on the returned
    generator, not when watch() itself is called - so closing an unstarted
    generator opens (and closes) nothing, and a PadNotFoundError can only
    be caught around the first next(), not around the watch() call itself.

    A `stop` firing mid-recording still saves and yields that session (see
    WatchResult.truncated) rather than discarding real pen input, then the
    generator ends - it does not wait for the next touch or run a cooldown
    afterwards.
    """
    from epad_signature_pad_hid_driver.formats import save_inkml, save_json
    from epad_signature_pad_hid_driver.render import render_signature

    output_dir.mkdir(parents=True, exist_ok=True)
    d = open_pad(vendor_id, product_id)
    try:
        while not _stop_requested(stop):
            trigger = _wait_for_touch(d, stop)
            if trigger is None:
                return

            session_start_wall = datetime.now()
            samples, truncated = _record_session(d, trigger, idle_gap_seconds, stop)

            slug = _timestamp_slug(session_start_wall)
            suffix = "_partial" if truncated else ""
            png_path = output_dir / f"signature_{slug}{suffix}.png"
            json_path = output_dir / f"signature_{slug}{suffix}.json"
            inkml_path = output_dir / f"signature_{slug}{suffix}.inkml"
            render_signature(samples, png_path)
            save_json(
                samples, json_path, captured_at=session_start_wall, truncated=truncated
            )
            save_inkml(
                samples, inkml_path, captured_at=session_start_wall, truncated=truncated
            )
            yield WatchResult(
                png_path=png_path,
                json_path=json_path,
                inkml_path=inkml_path,
                samples=samples,
                truncated=truncated,
            )

            if truncated or _run_cooldown(cooldown_seconds, stop):
                return
    finally:
        d.close()
