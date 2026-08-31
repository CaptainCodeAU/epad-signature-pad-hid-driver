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
    """One decoded reading from the pad."""

    button1: bool
    button2: bool
    vendor_field: int
    touch: bool
    in_range: bool
    x: int
    y: int
    pressure: int
    raw: bytes


def decode_report(data: bytes) -> PenSample:
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
    )


def open_pad() -> hid.device:
    """Open the ePad over raw HID. Raises OSError if it isn't plugged in."""
    d = hid.device()
    d.open(VENDOR_ID, PRODUCT_ID)
    d.set_nonblocking(1)
    return d


def capture(seconds: float, on_sample: "callable[[PenSample], None]") -> int:
    """Read from the pad for the given duration, calling on_sample for each report.

    Returns the number of reports received.
    """
    d = open_pad()
    count = 0
    deadline = time.monotonic() + seconds
    try:
        while time.monotonic() < deadline:
            report = d.read(REPORT_LENGTH, timeout_ms=50)
            if report:
                on_sample(decode_report(bytes(report)))
                count += 1
    finally:
        d.close()
    return count


def run() -> str:
    """CLI default action: identify the pad without reading data."""
    d = open_pad()
    try:
        product = d.get_product_string()
    finally:
        d.close()
    return f"Connected to: {product} (vid=0x{VENDOR_ID:04x}, pid=0x{PRODUCT_ID:04x})"
