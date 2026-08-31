"""Holding pen for tests not yet rehomed into their own test_*.py file.

decode_report/exceptions/protocol/device/session/render tests have already
moved to test_protocol.py, test_exceptions.py, test_device.py,
test_session.py, and test_render.py. What's left here (save_json/
save_inkml, cli) moves to test_formats.py and test_cli.py as those
modules are rebuilt - this file is deleted once nothing remains in it.
"""

import sys
from datetime import datetime

import hid
import pytest

from epad_signature_pad_hid_driver import cli as cli_module
from epad_signature_pad_hid_driver.cli import main
from epad_signature_pad_hid_driver.formats import save_inkml, save_json
from tests.helpers import FakePad, raw_report, stroke_samples, touched_samples


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
