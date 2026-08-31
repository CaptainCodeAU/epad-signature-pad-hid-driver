"""Core functionality for epad_signature_pad_hid_driver.

Talks directly to an ePadLink "ePad" USB signature pad (VID 0x04DF, PID 0x0012)
over raw USB HID, bypassing ePadLink's own Windows/Linux-only driver stack.

The report layout below was decoded from the pad's own HID report descriptor
(fetched live via hid.device.get_report_descriptor()), not guessed or
reverse-engineered from captured traffic. Every ePad of this exact model
publishes the same descriptor, so this layout should hold across units.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Callable, Iterator

import hid

VENDOR_ID = 0x04DF
PRODUCT_ID = 0x0012

# Input report: 6 bytes, no leading Report ID byte.
#   byte 0, bit 0   -> button1
#   byte 0, bit 1   -> button2
#   byte 0, bits 2-4-> vendor 3-bit field (logical 1-3; meaning undocumented)
#   byte 0, bit 5   -> touch      (Digitizer usage 0x33)
#   byte 0, bit 6   -> in_range   (Digitizer usage 0x35)
#   byte 0, bit 7   -> unused (HID padding bit)
#   bytes 1-2       -> x, 16-bit little-endian, logical range 0-2896
#   bytes 3-4       -> y, 16-bit little-endian, logical range 0-1370
#   byte 5, bits 0-6-> pressure, 7-bit, logical range 0-127
#   byte 5, bit 7   -> unused (HID padding bit)
REPORT_LENGTH = 6


@dataclass
class PenSample:
    """One decoded reading from the pad.

    t is seconds since the first sample of its capture session (always 0.0
    for that first sample) - not wall-clock time. It's what lets recorded
    strokes be replayed at their real speed, not just drawn as a static shape.
    """

    button1: bool
    button2: bool
    vendor_field: int
    touch: bool
    in_range: bool
    x: int
    y: int
    pressure: int
    raw: bytes
    t: float = 0.0


def decode_report(data: bytes, t: float = 0.0) -> PenSample:
    """Decode one raw 6-byte HID input report into a PenSample."""
    status = data[0]
    x = data[1] | (data[2] << 8)
    y = data[3] | (data[4] << 8)
    pressure = data[5] & 0x7F
    return PenSample(
        button1=bool(status & 0x01),
        button2=bool(status & 0x02),
        vendor_field=(status >> 2) & 0x07,
        touch=bool(status & 0x20),
        in_range=bool(status & 0x40),
        x=x,
        y=y,
        pressure=pressure,
        raw=bytes(data),
        t=t,
    )


def open_pad() -> hid.device:
    """Open the ePad over raw HID. Raises OSError if it isn't plugged in."""
    d = hid.device()
    d.open(VENDOR_ID, PRODUCT_ID)
    d.set_nonblocking(1)
    return d


def capture(seconds: float, on_sample: Callable[[PenSample], None]) -> int:
    """Read from the pad for the given duration, calling on_sample for each report.

    Each sample's t is seconds since this call started. Returns the number
    of reports received.
    """
    d = open_pad()
    count = 0
    start = time.monotonic()
    deadline = start + seconds
    try:
        while time.monotonic() < deadline:
            report = d.read(REPORT_LENGTH, timeout_ms=50)
            if report:
                on_sample(decode_report(bytes(report), t=time.monotonic() - start))
                count += 1
    finally:
        d.close()
    return count


def _timestamp_slug(moment: datetime) -> str:
    """A sortable, unique-enough-for-this-use filename fragment, e.g. 20260831T224512_123."""
    return moment.strftime("%Y%m%dT%H%M%S_") + f"{moment.microsecond // 1000:03d}"


@dataclass
class WatchResult:
    """One completed capture from watch(): where it saved, and the raw samples."""

    png_path: Path
    json_path: Path
    inkml_path: Path
    samples: list[PenSample]


def watch(
    output_dir: Path,
    idle_gap_seconds: float = 3.0,
    cooldown_seconds: float = 2.0,
) -> Iterator[WatchResult]:
    """Wait for a pen touch, record until idle_gap_seconds of no touching, save, repeat.

    A pen-down starts a session; it keeps recording through pen lifts (e.g.
    between letters) and only ends once idle_gap_seconds pass with no touch
    at all. The session is then saved as a PNG plus JSON and InkML data
    files, timestamped so runs never collide or run out of numbers, and
    this pauses for cooldown_seconds before listening again. Runs until the
    caller stops iterating (e.g. on KeyboardInterrupt).
    """
    from epad_signature_pad_hid_driver.formats import save_inkml, save_json
    from epad_signature_pad_hid_driver.render import render_signature

    output_dir.mkdir(parents=True, exist_ok=True)
    d = open_pad()
    try:
        while True:
            trigger: PenSample | None = None
            while trigger is None:
                report = d.read(REPORT_LENGTH, timeout_ms=50)
                if report:
                    sample = decode_report(bytes(report))
                    if sample.touch:
                        trigger = sample

            session_start_wall = datetime.now()
            session_start_mono = time.monotonic()
            trigger.t = 0.0
            samples = [trigger]
            last_touch_mono = session_start_mono
            while time.monotonic() - last_touch_mono < idle_gap_seconds:
                report = d.read(REPORT_LENGTH, timeout_ms=50)
                if report:
                    now = time.monotonic()
                    sample = decode_report(bytes(report), t=now - session_start_mono)
                    samples.append(sample)
                    if sample.touch:
                        last_touch_mono = now

            slug = _timestamp_slug(session_start_wall)
            png_path = output_dir / f"signature_{slug}.png"
            json_path = output_dir / f"signature_{slug}.json"
            inkml_path = output_dir / f"signature_{slug}.inkml"
            render_signature(samples, png_path)
            save_json(samples, json_path, captured_at=session_start_wall)
            save_inkml(samples, inkml_path, captured_at=session_start_wall)
            yield WatchResult(
                png_path=png_path,
                json_path=json_path,
                inkml_path=inkml_path,
                samples=samples,
            )

            time.sleep(cooldown_seconds)
    finally:
        d.close()


def run() -> str:
    """CLI default action: identify the pad without reading data."""
    d = open_pad()
    try:
        product = d.get_product_string()
    finally:
        d.close()
    return f"Connected to: {product} (vid=0x{VENDOR_ID:04x}, pid=0x{PRODUCT_ID:04x})"
