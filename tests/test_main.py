"""Tests for the CLI and core functionality."""

import sys

import pytest

from epad_signature_pad_hid_driver import __version__, run
from epad_signature_pad_hid_driver.cli import main


def test_version() -> None:
    """Test version is defined."""
    assert __version__ == "0.1.0"


def test_run() -> None:
    """Test the core run function."""
    result = run()
    assert isinstance(result, str)
    assert len(result) > 0


def test_cli_version(capsys: pytest.CaptureFixture[str]) -> None:
    """Test CLI version flag."""
    sys.argv = ["epad-signature-pad-hid-driver", "--version"]
    exit_code = main()
    captured = capsys.readouterr()
    assert exit_code == 0
    assert "0.1.0" in captured.out


def test_cli_help(capsys: pytest.CaptureFixture[str]) -> None:
    """Test CLI help flag."""
    sys.argv = ["epad-signature-pad-hid-driver", "--help"]
    exit_code = main()
    captured = capsys.readouterr()
    assert exit_code == 0
    assert "Usage" in captured.out
