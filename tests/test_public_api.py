"""The public API contract test.

This hard-coded list of the 12 names that existed before this reorg is
the actual contract - it must never be edited to make a build pass. If
this test fails, the fix is in __init__.py, not here.
"""

import epad_signature_pad_hid_driver as pkg

LEGACY_NAMES = [
    "PRODUCT_ID",
    "VENDOR_ID",
    "PenSample",
    "WatchResult",
    "capture",
    "decode_report",
    "open_pad",
    "render_signature",
    "run",
    "save_inkml",
    "save_json",
    "watch",
]


def test_every_legacy_name_still_imports() -> None:
    for name in LEGACY_NAMES:
        assert hasattr(pkg, name), f"legacy public name missing: {name}"


def test_legacy_names_are_the_same_objects_as_the_new_modules_export() -> None:
    from epad_signature_pad_hid_driver.device import open_pad, run
    from epad_signature_pad_hid_driver.protocol import (
        PRODUCT_ID,
        VENDOR_ID,
        PenSample,
        decode_report,
    )
    from epad_signature_pad_hid_driver.render import render_signature
    from epad_signature_pad_hid_driver.session import WatchResult, capture, watch

    assert pkg.PRODUCT_ID is PRODUCT_ID
    assert pkg.VENDOR_ID is VENDOR_ID
    assert pkg.PenSample is PenSample
    assert pkg.WatchResult is WatchResult
    assert pkg.capture is capture
    assert pkg.decode_report is decode_report
    assert pkg.open_pad is open_pad
    assert pkg.render_signature is render_signature
    assert pkg.run is run
    assert pkg.watch is watch


def test_all_matches_module_namespace() -> None:
    for name in pkg.__all__:
        assert hasattr(pkg, name), f"__all__ names {name} but it isn't bound"


def test_version() -> None:
    assert pkg.__version__ == "0.1.0"


def test_new_exceptions_are_exported() -> None:
    assert issubclass(pkg.PadNotFoundError, pkg.EpadError)
    assert issubclass(pkg.EmptyCaptureError, pkg.EpadError)
    assert issubclass(pkg.InvalidFormatError, pkg.EpadError)


NEW_NAMES = ["encode_report", "load_json", "load_inkml", "PadConnection"]


def test_every_new_name_still_imports() -> None:
    """The additive names this reorg promised alongside the legacy ones -
    load_json/load_inkml were missed here once already (caught only by
    hand, after the reorg was believed complete), so this is the
    regression test for that specific mistake."""
    for name in NEW_NAMES:
        assert hasattr(pkg, name), f"new public name missing: {name}"
        assert name in pkg.__all__, f"{name} is importable but missing from __all__"


def test_empty_capture_error_is_raised_through_the_public_render_signature() -> None:
    import pytest

    with pytest.raises(pkg.EmptyCaptureError):
        pkg.render_signature([], "/dev/null/unused")  # type: ignore[arg-type]
