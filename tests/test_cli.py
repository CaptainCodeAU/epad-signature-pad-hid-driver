"""Tests for cli.py: the command-line interface, including `convert`."""

import sys
from datetime import datetime

import hid
import pytest
from PIL import Image

from epad_signature_pad_hid_driver import cli as cli_module
from epad_signature_pad_hid_driver.cli import main
from epad_signature_pad_hid_driver.formats import save_inkml, save_json
from tests.helpers import FakePad, raw_report, touched_samples

# ---- moved from test_main.py ----


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
    assert "convert" in captured.out


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


def test_cli_default_command_prints_connection(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(hid, "device", lambda: FakePad([]))
    sys.argv = ["epad-signature-pad-hid-driver"]

    exit_code = main()

    captured = capsys.readouterr()
    assert exit_code == 0
    assert "Connected to" in captured.out


# ---- convert: single file ----


def _make_json(tmp_path, name="sig.json"):
    path = tmp_path / name
    save_json(touched_samples([(1, 2), (3, 4)]), path, captured_at=datetime(2026, 1, 1))
    return path


def _make_inkml(tmp_path, name="sig.inkml"):
    path = tmp_path / name
    save_inkml(
        touched_samples([(1, 2), (3, 4)]), path, captured_at=datetime(2026, 1, 1)
    )
    return path


def test_convert_json_file_to_png(tmp_path, capsys: pytest.CaptureFixture[str]) -> None:
    input_path = _make_json(tmp_path)
    output_path = tmp_path / "out.png"
    sys.argv = [
        "epad-signature-pad-hid-driver",
        "convert",
        str(input_path),
        str(output_path),
    ]

    exit_code = main()

    assert exit_code == 0
    assert output_path.exists()
    with Image.open(output_path) as image:
        assert image.size[0] > 0


def test_convert_inkml_file_to_png(tmp_path) -> None:
    input_path = _make_inkml(tmp_path)
    output_path = tmp_path / "out.png"
    sys.argv = [
        "epad-signature-pad-hid-driver",
        "convert",
        str(input_path),
        str(output_path),
    ]

    exit_code = main()

    assert exit_code == 0
    assert output_path.exists()


def test_convert_uppercase_extension(tmp_path) -> None:
    input_path = _make_json(tmp_path, name="sig.JSON")
    output_path = tmp_path / "out.png"
    sys.argv = [
        "epad-signature-pad-hid-driver",
        "convert",
        str(input_path),
        str(output_path),
    ]

    exit_code = main()

    assert exit_code == 0
    assert output_path.exists()


def test_convert_unknown_extension_errors(
    tmp_path, capsys: pytest.CaptureFixture[str]
) -> None:
    input_path = tmp_path / "sig.txt"
    input_path.write_text("nope")
    sys.argv = [
        "epad-signature-pad-hid-driver",
        "convert",
        str(input_path),
        str(tmp_path / "out.png"),
    ]

    exit_code = main()

    captured = capsys.readouterr()
    assert exit_code == 1
    assert "Error" in captured.err
    assert "Traceback" not in captured.err


def test_convert_missing_input_file_errors(
    tmp_path, capsys: pytest.CaptureFixture[str]
) -> None:
    sys.argv = [
        "epad-signature-pad-hid-driver",
        "convert",
        str(tmp_path / "missing.json"),
        str(tmp_path / "out.png"),
    ]

    exit_code = main()

    captured = capsys.readouterr()
    assert exit_code == 1
    assert "Error" in captured.err


def test_convert_malformed_file_errors(
    tmp_path, capsys: pytest.CaptureFixture[str]
) -> None:
    input_path = tmp_path / "bad.json"
    input_path.write_text("not json {{{")
    sys.argv = [
        "epad-signature-pad-hid-driver",
        "convert",
        str(input_path),
        str(tmp_path / "out.png"),
    ]

    exit_code = main()

    captured = capsys.readouterr()
    assert exit_code == 1
    assert "Error" in captured.err
    assert "Traceback" not in captured.err


def test_convert_empty_ink_reports_empty_capture(
    tmp_path, capsys: pytest.CaptureFixture[str]
) -> None:
    input_path = tmp_path / "empty.json"
    save_json([], input_path, captured_at=datetime(2026, 1, 1))
    sys.argv = [
        "epad-signature-pad-hid-driver",
        "convert",
        str(input_path),
        str(tmp_path / "out.png"),
    ]

    exit_code = main()

    captured = capsys.readouterr()
    assert exit_code == 1
    assert "No pen-down samples" in captured.err


def test_convert_missing_arguments_shows_usage(
    capsys: pytest.CaptureFixture[str],
) -> None:
    sys.argv = ["epad-signature-pad-hid-driver", "convert"]

    exit_code = main()

    captured = capsys.readouterr()
    assert exit_code == 1
    assert "Usage" in captured.out or "Usage" in captured.err


def test_convert_creates_output_directory(tmp_path) -> None:
    input_path = _make_json(tmp_path)
    output_path = tmp_path / "nested" / "dir" / "out.png"
    sys.argv = [
        "epad-signature-pad-hid-driver",
        "convert",
        str(input_path),
        str(output_path),
    ]

    exit_code = main()

    assert exit_code == 0
    assert output_path.exists()


# ---- convert: directory batch ----


def test_convert_directory_batch(tmp_path, capsys: pytest.CaptureFixture[str]) -> None:
    in_dir = tmp_path / "in"
    in_dir.mkdir()
    out_dir = tmp_path / "out"
    _make_json(in_dir, name="a.json")
    _make_inkml(in_dir, name="b.inkml")
    sys.argv = ["epad-signature-pad-hid-driver", "convert", str(in_dir), str(out_dir)]

    exit_code = main()

    assert exit_code == 0
    assert (out_dir / "a.json.png").exists()
    assert (out_dir / "b.inkml.png").exists()


def test_convert_directory_converts_both_formats_of_one_stem(tmp_path) -> None:
    """Since watch() always writes a .json and .inkml with the same stem,
    that must not be treated as a collision - both get their own PNG."""
    in_dir = tmp_path / "in"
    in_dir.mkdir()
    out_dir = tmp_path / "out"
    _make_json(in_dir, name="signature_x.json")
    _make_inkml(in_dir, name="signature_x.inkml")
    sys.argv = ["epad-signature-pad-hid-driver", "convert", str(in_dir), str(out_dir)]

    exit_code = main()

    assert exit_code == 0
    assert (out_dir / "signature_x.json.png").exists()
    assert (out_dir / "signature_x.inkml.png").exists()


def test_convert_directory_finds_uppercase_extensions(tmp_path) -> None:
    in_dir = tmp_path / "in"
    in_dir.mkdir()
    out_dir = tmp_path / "out"
    _make_json(in_dir, name="a.JSON")
    sys.argv = ["epad-signature-pad-hid-driver", "convert", str(in_dir), str(out_dir)]

    exit_code = main()

    assert exit_code == 0
    assert (out_dir / "a.JSON.png").exists()


def test_convert_directory_skips_other_extensions(tmp_path) -> None:
    in_dir = tmp_path / "in"
    in_dir.mkdir()
    out_dir = tmp_path / "out"
    _make_json(in_dir, name="a.json")
    (in_dir / "readme.txt").write_text("ignore me")
    sys.argv = ["epad-signature-pad-hid-driver", "convert", str(in_dir), str(out_dir)]

    exit_code = main()

    assert exit_code == 0
    assert list(out_dir.iterdir()) == [out_dir / "a.json.png"]


def test_convert_directory_refuses_to_overwrite_existing_png(
    tmp_path, capsys: pytest.CaptureFixture[str]
) -> None:
    in_dir = tmp_path / "in"
    in_dir.mkdir()
    out_dir = tmp_path / "out"
    out_dir.mkdir()
    _make_json(in_dir, name="a.json")
    existing = out_dir / "a.json.png"
    existing.write_bytes(b"already here")
    sys.argv = ["epad-signature-pad-hid-driver", "convert", str(in_dir), str(out_dir)]

    exit_code = main()

    assert exit_code == 1
    assert existing.read_bytes() == b"already here"  # not clobbered


def test_convert_directory_reports_broken_symlink(
    tmp_path, capsys: pytest.CaptureFixture[str]
) -> None:
    in_dir = tmp_path / "in"
    in_dir.mkdir()
    out_dir = tmp_path / "out"
    _make_json(in_dir, name="good.json")
    broken = in_dir / "broken.json"
    broken.symlink_to(in_dir / "does-not-exist.json")
    sys.argv = ["epad-signature-pad-hid-driver", "convert", str(in_dir), str(out_dir)]

    exit_code = main()

    captured = capsys.readouterr()
    assert exit_code == 1  # one file failed
    assert (out_dir / "good.json.png").exists()  # the good one still converted
    assert "broken.json" in captured.out


def test_convert_directory_continues_after_one_bad_file(tmp_path) -> None:
    in_dir = tmp_path / "in"
    in_dir.mkdir()
    out_dir = tmp_path / "out"
    _make_json(in_dir, name="good.json")
    (in_dir / "bad.json").write_text("not json {{{")
    sys.argv = ["epad-signature-pad-hid-driver", "convert", str(in_dir), str(out_dir)]

    exit_code = main()

    assert exit_code == 1
    assert (out_dir / "good.json.png").exists()


def test_convert_empty_directory_errors(
    tmp_path, capsys: pytest.CaptureFixture[str]
) -> None:
    in_dir = tmp_path / "in"
    in_dir.mkdir()
    sys.argv = [
        "epad-signature-pad-hid-driver",
        "convert",
        str(in_dir),
        str(tmp_path / "out"),
    ]

    exit_code = main()

    captured = capsys.readouterr()
    assert exit_code == 1
    assert "no .json or .inkml files" in (captured.out + captured.err)


# ---- friendly errors elsewhere ----


def test_cli_reports_pad_not_found_without_traceback(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    from tests.helpers import RaisingPad

    monkeypatch.setattr(hid, "device", lambda: RaisingPad(OSError("open failed")))
    sys.argv = ["epad-signature-pad-hid-driver"]

    exit_code = main()

    captured = capsys.readouterr()
    assert exit_code == 1
    assert "Error" in captured.err
    assert "Traceback" not in captured.err


def test_cli_bad_capture_seconds_argument(
    capsys: pytest.CaptureFixture[str],
) -> None:
    sys.argv = ["epad-signature-pad-hid-driver", "capture", "not-a-number"]

    exit_code = main()

    captured = capsys.readouterr()
    assert exit_code == 1
    assert "Error" in captured.err
    assert "Traceback" not in captured.err
