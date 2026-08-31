"""epad_signature_pad_hid_driver package.

This package can be used both as a CLI tool and as an importable library.
"""

__version__ = "0.1.0"

from epad_signature_pad_hid_driver.core import (
    PRODUCT_ID,
    VENDOR_ID,
    PenSample,
    WatchResult,
    capture,
    decode_report,
    open_pad,
    run,
    watch,
)
from epad_signature_pad_hid_driver.formats import save_inkml, save_json
from epad_signature_pad_hid_driver.render import render_signature

__all__ = [
    "PRODUCT_ID",
    "VENDOR_ID",
    "PenSample",
    "WatchResult",
    "__version__",
    "capture",
    "decode_report",
    "open_pad",
    "render_signature",
    "run",
    "save_inkml",
    "save_json",
    "watch",
]
