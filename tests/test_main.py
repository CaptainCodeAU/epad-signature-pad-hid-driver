"""Holding pen for tests not yet rehomed into their own test_*.py file.

Everything except the CLI tests has now moved to its own test_*.py file.
What's left here moves to test_cli.py as that module is rebuilt with the
convert command - this file is deleted once nothing remains in it.
"""

import sys

import hid
import pytest

from epad_signature_pad_hid_driver import cli as cli_module
from epad_signature_pad_hid_driver.cli import main
from tests.helpers import FakePad, raw_report


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
