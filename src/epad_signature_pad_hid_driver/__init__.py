"""epad_signature_pad_hid_driver package.

This package can be used both as a CLI tool and as an importable library.
"""

__version__ = "0.1.0"

from epad_signature_pad_hid_driver.core import PenSample, capture, decode_report, open_pad, run

__all__ = ["PenSample", "__version__", "capture", "decode_report", "open_pad", "run"]
