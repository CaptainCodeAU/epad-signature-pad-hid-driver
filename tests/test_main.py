"""Tests for the CLI and core functionality.

decode_report, render_signature, save_json, and save_inkml are pure
functions and are tested directly with synthetic data - no hardware
required. capture() and watch() are tested against a FakePad standing in
for the real hid.device(), so the auto-trigger recording loop is covered
without a physical pad attached. Tests that need a real pad attached are
skipped automatically when one isn't found.
"""

import sys
import time
from datetime import datetime

import hid
import pytest
from PIL import Image

from epad_signature_pad_hid_driver import (
    PRODUCT_ID,
    VENDOR_ID,
    __version__,
    capture,
    cli as cli_module,
    decode_report,
    watch,
)
from epad_signature_pad_hid_driver.cli import main
from epad_signature_pad_hid_driver.core import PenSample
from epad_signature_pad_hid_driver.formats import save_inkml, save_json
from epad_signature_pad_hid_driver.render import PADDING, render_signature

requires_pad = pytest.mark.skipif(
    not any(
        d["vendor_id"] == VENDOR_ID and d["product_id"] == PRODUCT_ID
        for d in hid.enumerate()
    ),
    reason="ePad hardware not connected",
)


class FakePad:
    """Stands in for hid.device() so capture()/watch() can be tested without real hardware."""

    def __init__(
        self,
        reports: list[bytes],
        raise_when_exhausted: type[BaseException] | None = None,
        raise_after_seconds: float = 0.0,
    ) -> None:
        self._reports = list(reports)
        self._raise_when_exhausted = raise_when_exhausted
        self._raise_after = time.monotonic() + raise_after_seconds

    def open(self, vendor_id: int, product_id: int) -> None:
        pass

    def set_nonblocking(self, value: int) -> None:
        pass

    def read(self, length: int, timeout_ms: int = 0) -> list[int]:
        if self._reports:
            return list(self._reports.pop(0))
        if (
            self._raise_when_exhausted is not None
            and time.monotonic() >= self._raise_after
        ):
            raise self._raise_when_exhausted
        return []

    def get_product_string(self) -> str:
        return "ePadLink USB ePad"

    def close(self) -> None:
        pass


def _raw_report(x: int, y: int, pressure: int, touch: bool) -> bytes:
    status = (0b1 << 5) if touch else 0
    return bytes([status, x & 0xFF, x >> 8, y & 0xFF, y >> 8, pressure])


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


def _stroke_samples(strokes: list[list[tuple[int, int]]]) -> list[PenSample]:
    """Build samples for multiple pen-down strokes, with a lift between each."""
    samples: list[PenSample] = []
    t = 0.0
    for stroke_index, stroke in enumerate(strokes):
        if stroke_index > 0:
            last = samples[-1]
            samples.append(
                PenSample(
                    button1=False,
                    button2=False,
                    vendor_field=0,
                    touch=False,
                    in_range=False,
                    x=last.x,
                    y=last.y,
                    pressure=0,
                    raw=b"\x00" * 6,
                    t=t,
                )
            )
            t += 0.02
        for x, y in stroke:
            samples.append(
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
                    t=t,
                )
            )
            t += 0.02
    return samples


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


def test_render_signature_separates_strokes(tmp_path) -> None:
    # Two short vertical strokes, far apart, with a pen lift between them.
    samples = _stroke_samples(
        [
            [(10, 10), (10, 50)],
            [(200, 10), (200, 50)],
        ]
    )
    out_path = tmp_path / "signature.png"

    render_signature(samples, out_path)

    with Image.open(out_path) as image:
        pixels = image.load()
        min_x, max_x = 10, 200
        min_y = 10
        stroke1_x = min_x - min_x + PADDING
        stroke2_x = max_x - min_x + PADDING
        mid_y = (10 - min_y + PADDING + 50 - min_y + PADDING) // 2
        bridge_x = (stroke1_x + stroke2_x) // 2

        assert pixels[stroke1_x, mid_y] == (0, 0, 0)
        assert pixels[stroke2_x, mid_y] == (0, 0, 0)
        assert pixels[bridge_x, mid_y] == (255, 255, 255)


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


def test_save_inkml_separates_strokes(tmp_path) -> None:
    samples = _stroke_samples(
        [
            [(1, 2), (3, 4)],
            [(5, 6), (7, 8)],
        ]
    )
    out_path = tmp_path / "signature.inkml"

    save_inkml(samples, out_path, captured_at=datetime(2026, 8, 31, 22, 45, 12))

    content = out_path.read_text()
    assert content.count("<trace>") == 2
    assert "<trace>1 2 64 0, 3 4 64 20</trace>" in content
    assert "<trace>5 6 64 60, 7 8 64 80</trace>" in content


def test_capture_reads_reports_from_pad(monkeypatch: pytest.MonkeyPatch) -> None:
    reports = [
        _raw_report(x=10, y=20, pressure=50, touch=True),
        _raw_report(x=15, y=25, pressure=60, touch=True),
        _raw_report(x=20, y=30, pressure=70, touch=True),
    ]
    monkeypatch.setattr(hid, "device", lambda: FakePad(reports))

    samples: list[PenSample] = []
    count = capture(0.05, samples.append)

    assert count == 3
    assert [s.x for s in samples] == [10, 15, 20]
    assert [s.y for s in samples] == [20, 25, 30]
    assert all(s.touch for s in samples)


def test_watch_keeps_recording_through_pen_lifts(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    reports = [
        _raw_report(x=10, y=10, pressure=50, touch=True),
        _raw_report(x=12, y=12, pressure=50, touch=True),
        _raw_report(x=12, y=12, pressure=0, touch=False),  # pen lifts mid-signature
        _raw_report(x=20, y=20, pressure=50, touch=True),  # pen touches down again
    ]
    monkeypatch.setattr(hid, "device", lambda: FakePad(reports))

    watch_gen = watch(tmp_path, idle_gap_seconds=0.05, cooldown_seconds=0.01)
    result = next(watch_gen)

    assert len(result.samples) == 4
    assert result.samples[2].touch is False
    assert result.samples[3].touch is True
    assert result.png_path.exists()
    assert result.json_path.exists()
    assert result.inkml_path.exists()


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


def test_cli_capture_command(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    reports = [
        _raw_report(x=1, y=2, pressure=10, touch=True),
        _raw_report(x=3, y=4, pressure=20, touch=True),
    ]
    monkeypatch.setattr(hid, "device", lambda: FakePad(reports))
    sys.argv = ["epad-signature-pad-hid-driver", "capture", "0.05"]

    exit_code = main()

    captured = capsys.readouterr()
    assert exit_code == 0
    assert "Capturing for" in captured.out
    assert "Done. Received 2 reports." in captured.out


def test_cli_watch_command(
    tmp_path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    reports = [_raw_report(x=1, y=2, pressure=10, touch=True)]
    monkeypatch.setattr(
        hid,
        "device",
        lambda: FakePad(
            reports, raise_when_exhausted=KeyboardInterrupt, raise_after_seconds=0.1
        ),
    )
    monkeypatch.setattr(cli_module, "DEFAULT_OUTPUT_DIR", tmp_path)
    sys.argv = ["epad-signature-pad-hid-driver", "watch", "0.02"]

    exit_code = main()

    captured = capsys.readouterr()
    assert exit_code == 0
    assert "Saved signature_" in captured.out
    assert "Stopped." in captured.out
