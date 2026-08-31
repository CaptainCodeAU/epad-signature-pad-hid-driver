"""Command-line interface for epad_signature_pad_hid_driver."""

from __future__ import annotations

import sys
from pathlib import Path

from epad_signature_pad_hid_driver import (
    EpadError,
    InvalidFormatError,
    PenSample,
    __version__,
    capture,
    run,
    watch,
)
from epad_signature_pad_hid_driver.formats import load_inkml, load_json
from epad_signature_pad_hid_driver.render import render_signature

DEFAULT_OUTPUT_DIR = Path("output")


def _print_sample(sample: PenSample) -> None:
    print(
        f"x={sample.x:5d} y={sample.y:5d} pressure={sample.pressure:3d} "
        f"touch={int(sample.touch)} in_range={int(sample.in_range)} "
        f"btn1={int(sample.button1)} btn2={int(sample.button2)} "
        f"vendor_field={sample.vendor_field} raw={sample.raw.hex()}"
    )


def _print_help() -> None:
    print("epad-signature-pad-hid-driver - CLI tool")
    print(f"Version: {__version__}")
    print("\nUsage: epad-signature-pad-hid-driver [command]")
    print("\nCommands:")
    print("  (none)                    Confirm the pad is connected")
    print(
        "  capture [seconds]         Print decoded pen samples for N seconds (default 15)"
    )
    print(
        "  watch [idle_gap]          Auto-save a signature on every pen session (default 3s idle gap)"
    )
    print(
        "  convert <input> <output>  Render a saved .json/.inkml file (or every one in a"
    )
    print("                            directory) to a .png")
    print("  --version, -v             Show version")
    print("  --help, -h                Show this help message")


def _cmd_capture(argv: list[str]) -> int:
    seconds = float(argv[2]) if len(argv) > 2 else 15.0
    print(f"Capturing for {seconds:.0f}s. Draw on the pad now...")
    count = capture(seconds, _print_sample)
    print(f"Done. Received {count} reports.")
    return 0


def _cmd_watch(argv: list[str]) -> int:
    idle_gap = float(argv[2]) if len(argv) > 2 else 3.0
    DEFAULT_OUTPUT_DIR.mkdir(exist_ok=True)
    print(
        f"Watching for pen touches. A session ends after {idle_gap:.0f}s of no touching."
    )
    print(f"Saving to {DEFAULT_OUTPUT_DIR}/. Press Ctrl+C to stop.")
    try:
        for watch_result in watch(DEFAULT_OUTPUT_DIR, idle_gap_seconds=idle_gap):
            print(
                f"Saved {watch_result.png_path.name} "
                f"(+ .json, .inkml) - {len(watch_result.samples)} samples"
            )
    except KeyboardInterrupt:
        print("\nStopped.")
    return 0


def _load(path: Path) -> list[PenSample]:
    """Load a .json or .inkml file by its extension (case-insensitive)."""
    suffix = path.suffix.lower()
    if suffix == ".json":
        return load_json(path)
    if suffix == ".inkml":
        return load_inkml(path)
    raise InvalidFormatError(
        f"{path}: unrecognized extension {path.suffix!r} (expected .json or .inkml)"
    )


def _convert_dir(input_dir: Path, output_dir: Path) -> int:
    # iterdir() + suffix.lower(), not glob("*.json") - glob is case-sensitive
    # even on a case-insensitive filesystem (macOS), so it would miss a
    # file like "SIG.JSON". Not filtered to is_file() so a broken symlink
    # is reported as a failure instead of silently vanishing from the scan.
    # Sorted and materialized before any output is written, so newly
    # written PNGs can never re-enter this same scan.
    inputs = sorted(
        p for p in input_dir.iterdir() if p.suffix.lower() in (".json", ".inkml")
    )
    if not inputs:
        print(
            f"Error: no .json or .inkml files directly in {input_dir} "
            "(subfolders are not scanned)"
        )
        return 1

    output_dir.mkdir(parents=True, exist_ok=True)
    had_failure = False
    for input_path in inputs:
        # Every watch() session writes a .json and .inkml with the same
        # stem - that's the normal case, not a collision - so the output
        # name keeps the full source name (including its extension)
        # instead of just the stem, and is unique per input by construction.
        output_path = output_dir / f"{input_path.name}.png"
        if output_path.exists():
            print(f"Skipped {input_path.name}: {output_path} already exists")
            had_failure = True
            continue
        try:
            render_signature(_load(input_path), output_path)
        except (EpadError, OSError) as err:
            print(f"Skipped {input_path.name}: {err}")
            had_failure = True
            continue
        print(f"Converted {input_path.name} -> {output_path.name}")
    return 1 if had_failure else 0


def _cmd_convert(argv: list[str]) -> int:
    if len(argv) < 4:
        print("Usage: epad-signature-pad-hid-driver convert <input> <output>")
        return 1
    input_path = Path(argv[2])
    output_path = Path(argv[3])

    if input_path.is_dir():
        return _convert_dir(input_path, output_path)

    try:
        render_signature(_load(input_path), output_path)
    except (EpadError, OSError) as err:
        print(f"Error: {err}", file=sys.stderr)
        return 1
    print(f"Converted {input_path} -> {output_path}")
    return 0


def main() -> int:
    """CLI entry point.

    Returns:
        Exit code (0 for success, non-zero for errors)
    """
    argv = sys.argv
    if len(argv) > 1 and argv[1] in ("--version", "-v"):
        print(f"epad-signature-pad-hid-driver version {__version__}")
        return 0
    if len(argv) > 1 and argv[1] in ("--help", "-h"):
        _print_help()
        return 0

    command = argv[1] if len(argv) > 1 else None
    try:
        if command == "capture":
            return _cmd_capture(argv)
        if command == "watch":
            return _cmd_watch(argv)
        if command == "convert":
            return _cmd_convert(argv)
        print(run())
        return 0
    except EpadError as err:
        print(f"Error: {err}", file=sys.stderr)
        return 1
    except ValueError as err:
        print(f"Error: invalid argument - {err}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
