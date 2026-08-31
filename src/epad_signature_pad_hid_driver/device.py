"""Open the ePad over raw USB HID. The only module that imports `hid`.

`open_pad()` returns a PadHandle: a Protocol naming just the handful of
hid.device methods this package actually uses. That keeps hid.device (a C
extension with no type stubs) from leaking into this package's public,
typed surface, without changing anything at runtime - a real hid.device
still satisfies PadHandle structurally.
"""

from __future__ import annotations

from types import TracebackType
from typing import Protocol

import hid

from epad_signature_pad_hid_driver.exceptions import PadNotFoundError
from epad_signature_pad_hid_driver.protocol import PRODUCT_ID, VENDOR_ID


class PadHandle(Protocol):
    """The subset of hid.device this package actually calls."""

    def open(self, vendor_id: int, product_id: int) -> None: ...
    def read(self, length: int, timeout_ms: int = ...) -> list[int]: ...
    def set_nonblocking(self, value: int) -> None: ...
    def get_product_string(self) -> str: ...
    def close(self) -> None: ...


def open_pad(vendor_id: int = VENDOR_ID, product_id: int = PRODUCT_ID) -> PadHandle:
    """Open the ePad (or a compatible model at a different vendor_id/product_id).

    Raises PadNotFoundError if it can't be opened. That can mean either
    "not plugged in" or "already open in another program" - verified live
    that both cases raise the identical underlying OSError, so this
    message deliberately does not claim to know which one it is.

    Prefer PadConnection (below) when you want the handle closed for you
    automatically; open_pad() is the low-level escape hatch for callers
    that need to manage the handle's lifetime themselves.
    """
    # hid.device() has no type stubs and is typed Any; annotate the local so
    # this function's own PadHandle return type is enforced, not silently Any.
    d: PadHandle = hid.device()
    try:
        d.open(vendor_id, product_id)
    except OSError as err:
        raise PadNotFoundError(
            f"Could not open the ePad at vid=0x{vendor_id:04x}, "
            f"pid=0x{product_id:04x}: {err}. Is it plugged in, and not "
            "already open in another program (the web demo, or another "
            "copy of this CLI)?"
        ) from err
    d.set_nonblocking(1)
    return d


class PadConnection:
    """`with PadConnection() as pad:` - closes the pad on the way out.

    hid.device (hidapi 0.15.0) does not implement __enter__/__exit__
    itself - verified live before writing this class - so this wrapper
    exists to give the pad connection `with` support without changing
    open_pad()'s own return type or behaviour.
    """

    def __init__(
        self, vendor_id: int = VENDOR_ID, product_id: int = PRODUCT_ID
    ) -> None:
        self._vendor_id = vendor_id
        self._product_id = product_id
        self._pad: PadHandle | None = None

    def __enter__(self) -> PadHandle:
        self._pad = open_pad(self._vendor_id, self._product_id)
        return self._pad

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        if self._pad is not None:
            self._pad.close()


def run(vendor_id: int = VENDOR_ID, product_id: int = PRODUCT_ID) -> str:
    """CLI default action: identify the pad without reading data."""
    d = open_pad(vendor_id, product_id)
    try:
        product = d.get_product_string()
    finally:
        d.close()
    return f"Connected to: {product} (vid=0x{vendor_id:04x}, pid=0x{product_id:04x})"
