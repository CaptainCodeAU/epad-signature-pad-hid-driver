"""Holding pen for tests not yet rehomed into their own test_*.py file.

decode_report/exceptions/protocol/device/session tests have already moved
to test_protocol.py, test_exceptions.py, test_device.py, and
test_session.py. What's left here (render, save_json/save_inkml, cli)
moves to test_render.py, test_formats.py, and test_cli.py as those modules
are rebuilt - this file is deleted once nothing remains in it.
"""

import sys
from datetime import datetime

import hid
import pytest
from PIL import Image

from epad_signature_pad_hid_driver import cli as cli_module
from epad_signature_pad_hid_driver.cli import main
from epad_signature_pad_hid_driver.formats import save_inkml, save_json
from epad_signature_pad_hid_driver.protocol import PenSample
from epad_signature_pad_hid_driver.render import PADDING, render_signature
from tests.helpers import FakePad, raw_report, stroke_samples, touched_samples


def test_render_signature(tmp_path) -> None:
    samples = touched_samples([(100, 100), (110, 105), (120, 110)])

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
    samples = stroke_samples(
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
    samples = touched_samples([(1, 2), (3, 4)])
    out_path = tmp_path / "signature.json"

    save_json(samples, out_path, captured_at=datetime(2026, 8, 31, 22, 45, 12))

    import json

    document = json.loads(out_path.read_text())
    assert document["sample_count"] == 2
    assert document["captured_at"] == "2026-08-31T22:45:12"
    assert document["truncated"] is False
    assert document["samples"][1]["x"] == 3
    assert document["samples"][1]["y"] == 4
    assert document["samples"][1]["t"] == pytest.approx(0.02)


def test_save_inkml(tmp_path) -> None:
    samples = touched_samples([(1, 2), (3, 4)])
    out_path = tmp_path / "signature.inkml"

    save_inkml(samples, out_path, captured_at=datetime(2026, 8, 31, 22, 45, 12))

    content = out_path.read_text()
    assert "<trace>1 2 64 0, 3 4 64 20</trace>" in content
    assert 'xmlns="http://www.w3.org/2003/InkML"' in content


def test_save_inkml_separates_strokes(tmp_path) -> None:
    samples = stroke_samples(
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
        raw_report(x=1, y=2, pressure=10, touch=True),
        raw_report(x=3, y=4, pressure=20, touch=True),
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
    reports = [raw_report(x=1, y=2, pressure=10, touch=True)]
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
