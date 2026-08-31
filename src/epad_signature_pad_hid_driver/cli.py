"""Command-line interface for epad_signature_pad_hid_driver."""

import sys

from epad_signature_pad_hid_driver import __version__, run


def main() -> int:
    """CLI entry point.

    Returns:
        Exit code (0 for success, non-zero for errors)
    """
    # Basic CLI structure - expand as needed
    if len(sys.argv) > 1 and sys.argv[1] in ("--version", "-v"):
        print(f"epad-signature-pad-hid-driver version {__version__}")
        return 0

    if len(sys.argv) > 1 and sys.argv[1] in ("--help", "-h"):
        print("epad-signature-pad-hid-driver - CLI tool")
        print(f"Version: {__version__}")
        print("\nUsage: epad-signature-pad-hid-driver [options]")
        print("\nOptions:")
        print("  --version, -v    Show version")
        print("  --help, -h       Show this help message")
        return 0

    # Run the core functionality
    result = run()
    print(result)
    return 0


if __name__ == "__main__":
    sys.exit(main())
