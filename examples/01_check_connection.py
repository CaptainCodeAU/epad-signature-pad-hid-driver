"""Confirm the pad is connected, and handle it if it isn't.

Needs a real pad plugged in - for the no-pad-attached case, see
05_handle_no_device.py instead.

Run with:
    uv run python examples/01_check_connection.py
"""

from epad_signature_pad_hid_driver import PadNotFoundError, run


def main() -> None:
    try:
        print(run())
    except PadNotFoundError as err:
        print(f"Could not connect: {err}")


if __name__ == "__main__":
    main()
