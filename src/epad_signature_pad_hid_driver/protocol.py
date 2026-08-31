"""The ePad's own 6-byte HID report layout: pure decode/encode, no I/O.

Talks about an ePadLink "ePad" USB signature pad (VID 0x04DF, PID 0x0012).
This module never imports `hid` - it only knows how to turn raw bytes into
a PenSample and back. Opening the device lives in device.py.

The report layout below was decoded from the pad's own HID report descriptor
(fetched live via hid.device.get_report_descriptor()), not guessed or
reverse-engineered from captured traffic. Every ePad of this exact model
publishes the same descriptor, so this layout should hold across units.
See docs/HARDWARE_NOTES.md for the full descriptor and how it was read.
"""

from __future__ import annotations

from dataclasses import dataclass

from epad_signature_pad_hid_driver.exceptions import InvalidFormatError

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
    """Decode one raw HID input report into a PenSample.

    Raises InvalidFormatError if data is shorter than REPORT_LENGTH bytes.
    Extra bytes beyond REPORT_LENGTH are ignored for decoding but kept in
    raw, exactly as given.
    """
    if len(data) < REPORT_LENGTH:
        raise InvalidFormatError(
            f"report too short: got {len(data)} bytes, need at least {REPORT_LENGTH}"
        )
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


def encode_report(sample: PenSample) -> bytes:
    """Build the 6 raw bytes decode_report() would turn back into `sample`.

    This is the reverse of decode_report() for every *wire* field, but not
    a perfect inverse of the whole PenSample:

    - `t` has no wire representation, so decode_report(encode_report(s)).t
      is always 0.0, never s.t.
    - The two real HID padding bits (byte 0 bit 7, byte 5 bit 7) are always
      written as 0 here, so re-encoding a sample whose original raw had
      either bit set does not reproduce that raw byte-for-byte.

    Raises ValueError if x, y, pressure, or vendor_field is out of the
    range the wire format can represent - that is a caller bug, not a
    malformed file (callers loading untrusted files should catch this and
    re-raise it as InvalidFormatError; see formats.py).
    """
    if not 0 <= sample.x <= 0xFFFF:
        raise ValueError(f"x out of range 0-65535: {sample.x}")
    if not 0 <= sample.y <= 0xFFFF:
        raise ValueError(f"y out of range 0-65535: {sample.y}")
    if not 0 <= sample.pressure <= 0x7F:
        raise ValueError(f"pressure out of range 0-127: {sample.pressure}")
    if not 0 <= sample.vendor_field <= 0x7:
        raise ValueError(f"vendor_field out of range 0-7: {sample.vendor_field}")

    status = (
        (0x01 if sample.button1 else 0)
        | (0x02 if sample.button2 else 0)
        | ((sample.vendor_field & 0x07) << 2)
        | (0x20 if sample.touch else 0)
        | (0x40 if sample.in_range else 0)
    )
    return bytes(
        [
            status,
            sample.x & 0xFF,
            (sample.x >> 8) & 0xFF,
            sample.y & 0xFF,
            (sample.y >> 8) & 0xFF,
            sample.pressure & 0x7F,
        ]
    )
