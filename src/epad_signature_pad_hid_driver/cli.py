"""Command-line interface for epad_signature_pad_hid_driver."""

import sys

from epad_signature_pad_hid_driver import __version__, capture, run


def _print_sample(sample) -> None:  # noqa: ANN001
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
        print("  capture [seconds]  Print decoded pen samples for N seconds (default 15)")
        print("  --version, -v      Show version")
        print("  --help, -h         Show this help message")
        return 0

    if len(sys.argv) > 1 and sys.argv[1] == "capture":
        seconds = float(sys.argv[2]) if len(sys.argv) > 2 else 15.0
        print(f"Capturing for {seconds:.0f}s. Draw on the pad now...")
        count = capture(seconds, _print_sample)
        print(f"Done. Received {count} reports.")
        return 0

    result = run()
    print(result)
    return 0


if __name__ == "__main__":
    sys.exit(main())
