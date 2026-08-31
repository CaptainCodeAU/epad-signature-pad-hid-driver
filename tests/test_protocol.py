"""Tests for protocol.py: pure decode/encode of the pad's 6-byte HID report.

No hid import, no USB I/O - every test here runs with just bytes in, bytes
or a PenSample out. The byte layout tested against is the one read live off
the pad's own HID report descriptor - see docs/HARDWARE_NOTES.md.
"""

import pytest

from epad_signature_pad_hid_driver.exceptions import InvalidFormatError
from epad_signature_pad_hid_driver.protocol import (
    PenSample,
    decode_report,
    encode_report,
)


def test_decode_report() -> None:
    # status byte: button1=1, button2=0, vendor_field=5, touch=1, in_range=0
    status = 0b1 | (0b0 << 1) | (0b101 << 2) | (0b1 << 5) | (0b0 << 6)
    x, y, pressure = 300, 500, 77
    raw = bytes([status, x & 0xFF, x >> 8, y & 0xFF, y >> 8, pressure])

    sample = decode_report(raw, t=1.5)

    assert sample.button1 is True
    assert sample.button2 is False
    assert sample.vendor_field == 5
    assert sample.touch is True
    assert sample.in_range is False
    assert sample.x == x
    assert sample.y == y
    assert sample.pressure == pressure
    assert sample.raw == raw
    assert sample.t == 1.5


def test_decode_report_all_zero() -> None:
    raw = bytes([0, 0, 0, 0, 0, 0])

    sample = decode_report(raw)

    assert sample.button1 is False
    assert sample.button2 is False
    assert sample.vendor_field == 0
    assert sample.touch is False
    assert sample.in_range is False
    assert sample.x == 0
    assert sample.y == 0
    assert sample.pressure == 0


def test_decode_report_max_values() -> None:
    # status byte 0xFF: both buttons set, vendor_field=7, touch=1, in_range=1,
    # padding bit (bit 7) has no field and must be ignored.
    status = 0xFF
    x, y = 0xFFFF, 0xFFFF
    pressure_byte = 0xFF  # top bit is padding and must be masked off

    raw = bytes([status, x & 0xFF, x >> 8, y & 0xFF, y >> 8, pressure_byte])

    sample = decode_report(raw)

    assert sample.button1 is True
    assert sample.button2 is True
    assert sample.vendor_field == 7
    assert sample.touch is True
    assert sample.in_range is True
    assert sample.x == 0xFFFF
    assert sample.y == 0xFFFF
    assert sample.pressure == 127


def test_decode_report_rejects_short_report() -> None:
    """A short report is a malformed-input problem, not a caller bug -
    InvalidFormatError (an EpadError) so the CLI's error net catches it,
    instead of a plain IndexError escaping as a raw traceback."""
    with pytest.raises(InvalidFormatError, match="report too short"):
        decode_report(bytes([0, 1, 2, 3, 4]))


def test_decode_report_keeps_extra_bytes_in_raw() -> None:
    """decode_report only reads the first 6 bytes, but raw keeps everything
    it was given - so a 7-byte input round-trips as a 7-byte raw."""
    raw = bytes([0, 0, 0, 0, 0, 0, 99])

    sample = decode_report(raw)

    assert sample.raw == raw
    assert len(sample.raw) == 7


def test_encode_report_round_trips_every_field_except_raw_and_t() -> None:
    """encode_report has no time field, and decode_report's raw is the
    literal bytes it was given - re-encoding never reproduces those two."""
    original = decode_report(bytes([0b0110_0101, 44, 1, 88, 2, 0x7F]), t=9.5)

    reencoded = decode_report(encode_report(original))

    assert reencoded.button1 == original.button1
    assert reencoded.button2 == original.button2
    assert reencoded.vendor_field == original.vendor_field
    assert reencoded.touch == original.touch
    assert reencoded.in_range == original.in_range
    assert reencoded.x == original.x
    assert reencoded.y == original.y
    assert reencoded.pressure == original.pressure
    assert reencoded.t == 0.0  # not original.t - encode_report carries no time


def test_encode_report_reproduces_raw_when_padding_bits_clear() -> None:
    raw = bytes([0b0110_0101, 44, 1, 88, 2, 0x7F])  # both padding bits already 0
    sample = decode_report(raw)

    assert encode_report(sample) == raw


def test_encode_report_drops_padding_bits() -> None:
    """decode_report ignores byte 0 bit 7 and byte 5 bit 7 (real HID
    padding bits) - encode_report always writes them back as 0, so a raw
    report with those bits set does not round-trip byte-for-byte."""
    raw = bytes([0xFF, 0, 0, 0, 0, 0xFF])
    sample = decode_report(raw)

    reencoded = encode_report(sample)

    assert reencoded[0] & 0x80 == 0
    assert reencoded[5] & 0x80 == 0
    assert reencoded != raw


def test_encode_report_little_endian_x_y() -> None:
    sample = PenSample(
        button1=False,
        button2=False,
        vendor_field=0,
        touch=False,
        in_range=False,
        x=0x1234,
        y=0x5678,
        pressure=0,
        raw=b"",
    )

    raw = encode_report(sample)

    assert (raw[1], raw[2]) == (0x34, 0x12)
    assert (raw[3], raw[4]) == (0x78, 0x56)


def _sample(**overrides: object) -> PenSample:
    defaults: dict[str, object] = {
        "button1": False,
        "button2": False,
        "vendor_field": 0,
        "touch": False,
        "in_range": False,
        "x": 0,
        "y": 0,
        "pressure": 0,
        "raw": b"",
    }
    defaults.update(overrides)
    return PenSample(**defaults)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    "overrides",
    [
        {"x": -1},
        {"x": 65536},
        {"y": -1},
        {"y": 65536},
        {"pressure": -1},
        {"pressure": 128},
        {"vendor_field": -1},
        {"vendor_field": 8},
    ],
)
def test_encode_report_rejects_out_of_range(overrides: dict[str, object]) -> None:
    with pytest.raises(ValueError, match="out of range"):
        encode_report(_sample(**overrides))
