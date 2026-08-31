"""Show catching PadNotFoundError - runs fine with no pad attached.

Uses a deliberately bogus vendor/product ID, so this always exercises the
"pad not found" path - even with a real ePad plugged in. This is what
open_pad()'s overridable vendor_id/product_id parameter is for.

Needs no hardware at all.

Run with:
    uv run python examples/05_handle_no_device.py
"""

from epad_signature_pad_hid_driver import PadNotFoundError, run

BOGUS_VENDOR_ID = 0xFFFF
BOGUS_PRODUCT_ID = 0xFFFF


def main() -> None:
    try:
        print(run(vendor_id=BOGUS_VENDOR_ID, product_id=BOGUS_PRODUCT_ID))
    except PadNotFoundError as err:
        print("Caught PadNotFoundError, as expected for a device that doesn't exist:")
        print(f"  {err}")


if __name__ == "__main__":
    main()
