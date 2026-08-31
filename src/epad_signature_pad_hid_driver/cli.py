"""Command-line interface for epad_signature_pad_hid_driver."""

import sys
from pathlib import Path

from epad_signature_pad_hid_driver import PenSample, __version__, capture, run, watch

DEFAULT_OUTPUT_DIR = Path("output")


def _print_sample(sample: PenSample) -> None:
    print(
        f"x={sample.x:5d} y={sample.y:5d} pressure={sample.pressure:3d} "
        f"touch={int(sample.touch)} in_range={int(sample.in_range)} "
        f"btn1={int(sample.button1)} btn2={int(sample.button2)} "
        f"vendor_field={sample.vendor_field} raw={sample.raw.hex()}"
    )


def main() -> int:
    """CLI entry point.

    Returns:
        Exit code (0 for success, non-zero for errors)
    """
    if len(sys.argv) > 1 and sys.argv[1] in ("--version", "-v"):
        print(f"epad-signature-pad-hid-driver version {__version__}")
        return 0

    if len(sys.argv) > 1 and sys.argv[1] in ("--help", "-h"):
        print("epad-signature-pad-hid-driver - CLI tool")
        print(f"Version: {__version__}")
        print("\nUsage: epad-signature-pad-hid-driver [command]")
        print("\nCommands:")
        print("  (none)             Confirm the pad is connected")
        print(
            "  capture [seconds]  Print decoded pen samples for N seconds (default 15)"
        )
        print(
            "  watch [idle_gap]   Auto-save a signature on every pen session (default 3s idle gap)"
        )
        print("  --version, -v      Show version")
        print("  --help, -h         Show this help message")
        return 0

    if len(sys.argv) > 1 and sys.argv[1] == "capture":
        seconds = float(sys.argv[2]) if len(sys.argv) > 2 else 15.0
        print(f"Capturing for {seconds:.0f}s. Draw on the pad now...")
        count = capture(seconds, _print_sample)
        print(f"Done. Received {count} reports.")
        return 0

    if len(sys.argv) > 1 and sys.argv[1] == "watch":
        idle_gap = float(sys.argv[2]) if len(sys.argv) > 2 else 3.0
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

    print(run())
    return 0


if __name__ == "__main__":
    sys.exit(main())
