"""epad_signature_pad_hid_driver package.

This package can be used both as a CLI tool and as an importable library.
"""

__version__ = "0.1.0"

from epad_signature_pad_hid_driver.device import PadConnection, open_pad, run
from epad_signature_pad_hid_driver.exceptions import (
    EmptyCaptureError,
    EpadError,
    InvalidFormatError,
    PadNotFoundError,
)
from epad_signature_pad_hid_driver.formats import (
    load_inkml,
    load_json,
    save_inkml,
    save_json,
)
from epad_signature_pad_hid_driver.protocol import (
    PRODUCT_ID,
    VENDOR_ID,
    PenSample,
    decode_report,
    encode_report,
)
from epad_signature_pad_hid_driver.render import render_signature
from epad_signature_pad_hid_driver.session import WatchResult, capture, watch

__all__ = [
    "PRODUCT_ID",
    "VENDOR_ID",
    "EmptyCaptureError",
    "EpadError",
    "InvalidFormatError",
    "PadConnection",
    "PadNotFoundError",
    "PenSample",
    "WatchResult",
    "__version__",
    "capture",
    "decode_report",
    "encode_report",
    "load_inkml",
    "load_json",
    "open_pad",
    "render_signature",
    "run",
    "save_inkml",
    "save_json",
    "watch",
]
