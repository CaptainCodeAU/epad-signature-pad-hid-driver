"""Tests for the CLI and core functionality.

decode_report and render_signature are pure functions and are tested
directly with synthetic data - no hardware required. Tests that need a
real pad attached are skipped automatically when one isn't found.
"""

import sys
from datetime import datetime

import hid
import pytest
from PIL import Image

from epad_signature_pad_hid_driver import (
    PRODUCT_ID,
    VENDOR_ID,
    __version__,
    decode_report,
)
from epad_signature_pad_hid_driver.cli import main
from epad_signature_pad_hid_driver.core import PenSample
from epad_signature_pad_hid_driver.formats import save_inkml, save_json
from epad_signature_pad_hid_driver.render import render_signature

requires_pad = pytest.mark.skipif(
    not any(
        d["vendor_id"] == VENDOR_ID and d["product_id"] == PRODUCT_ID
        for d in hid.enumerate()
    ),
    reason="ePad hardware not connected",
)


def test_version() -> None:
    assert __version__ == "0.1.0"


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


def _touched_samples(points: list[tuple[int, int]]) -> list[PenSample]:
    return [
        PenSample(
            button1=False,
            button2=False,
            vendor_field=0,
            touch=True,
            in_range=False,
            x=x,
            y=y,
            pressure=64,
            raw=b"\x00" * 6,
            t=i * 0.02,
        )
        for i, (x, y) in enumerate(points)
    ]


def test_render_signature(tmp_path) -> None:
    samples = _touched_samples([(100, 100), (110, 105), (120, 110)])

    out_path = tmp_path / "signature.png"
    render_signature(samples, out_path)

    assert out_path.exists()
    with Image.open(out_path) as image:
        assert image.size[0] > 0
        assert image.size[1] > 0


def test_render_signature_empty_raises(tmp_path) -> None:
    samples = [
        PenSample(
            button1=False,
            button2=False,
            vendor_field=0,
            touch=False,
            in_range=False,
            x=0,
            y=0,
            pressure=0,
            raw=b"\x00" * 6,
        )
    ]
    with pytest.raises(ValueError, match="No pen-down samples"):
        render_signature(samples, tmp_path / "signature.png")


def test_save_json(tmp_path) -> None:
    samples = _touched_samples([(1, 2), (3, 4)])
    out_path = tmp_path / "signature.json"

    save_json(samples, out_path, captured_at=datetime(2026, 8, 31, 22, 45, 12))

    import json

    document = json.loads(out_path.read_text())
    assert document["sample_count"] == 2
    assert document["captured_at"] == "2026-08-31T22:45:12"
    assert document["samples"][1]["x"] == 3
    assert document["samples"][1]["y"] == 4
    assert document["samples"][1]["t"] == pytest.approx(0.02)


def test_save_inkml(tmp_path) -> None:
    samples = _touched_samples([(1, 2), (3, 4)])
    out_path = tmp_path / "signature.inkml"

    save_inkml(samples, out_path, captured_at=datetime(2026, 8, 31, 22, 45, 12))

    content = out_path.read_text()
    assert "<trace>1 2 64 0, 3 4 64 20</trace>" in content
    assert 'xmlns="http://www.w3.org/2003/InkML"' in content


@requires_pad
def test_run() -> None:
    """Test the core run function against real hardware."""
    from epad_signature_pad_hid_driver import run

    result = run()
    assert isinstance(result, str)
    assert len(result) > 0


def test_cli_version(capsys: pytest.CaptureFixture[str]) -> None:
    sys.argv = ["epad-signature-pad-hid-driver", "--version"]
    exit_code = main()
    captured = capsys.readouterr()
    assert exit_code == 0
    assert "0.1.0" in captured.out


def test_cli_help(capsys: pytest.CaptureFixture[str]) -> None:
    sys.argv = ["epad-signature-pad-hid-driver", "--help"]
    exit_code = main()
    captured = capsys.readouterr()
    assert exit_code == 0
    assert "Usage" in captured.out
