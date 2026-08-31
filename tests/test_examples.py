"""Tests for examples/: each script must import cleanly and, for the two
that need no hardware, actually run end-to-end.

examples/ is not a Python package and its filenames start with digits, so
`import examples.01_check_connection` is a SyntaxError - these are loaded
by path instead, with importlib.util.spec_from_file_location. Loading a
module DOES execute its top-level code (verified before writing this),
so every example must keep its pad-touching work inside `main()` behind
`if __name__ == "__main__":`, never at module level - that's what lets
01-04 (which need a real pad) be import-checked here without one attached.
"""

import importlib.util
import subprocess
import sys
from pathlib import Path

import pytest

EXAMPLES_DIR = Path(__file__).parent.parent / "examples"
EXAMPLE_FILES = sorted(EXAMPLES_DIR.glob("*.py"))

# Examples that need no hardware and can be run all the way through.
NO_HARDWARE_NEEDED = ("05_handle_no_device.py", "06_convert_file_to_png.py")


def _load_module(path: Path):
    spec = importlib.util.spec_from_file_location(path.stem, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize("path", EXAMPLE_FILES, ids=lambda p: p.name)
def test_example_imports_and_defines_main(path: Path) -> None:
    module = _load_module(path)
    assert callable(module.main), f"{path.name} must define a callable main()"


def test_at_least_the_six_expected_examples_exist() -> None:
    names = {p.name for p in EXAMPLE_FILES}
    for expected in (
        "01_check_connection.py",
        "02_capture_and_save.py",
        "03_watch_mode.py",
        "04_live_callback.py",
        "05_handle_no_device.py",
        "06_convert_file_to_png.py",
    ):
        assert expected in names


@pytest.mark.parametrize("name", NO_HARDWARE_NEEDED)
def test_no_hardware_example_runs_end_to_end(name: str, tmp_path) -> None:
    result = subprocess.run(
        [sys.executable, str(EXAMPLES_DIR / name)],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stdout + result.stderr
