"""Tests for the exceptions module.

The two-parent design (e.g. PadNotFoundError(EpadError, OSError)) exists so
that code already catching plain OSError/ValueError today keeps working
unchanged after this reorg - verified live against Python 3.13 before this
was written (MRO, pickling, errno remapping, `raise ... from err`).
"""

import pickle

import pytest

from epad_signature_pad_hid_driver.exceptions import (
    EmptyCaptureError,
    EpadError,
    InvalidFormatError,
    PadNotFoundError,
)


def test_all_inherit_epad_error() -> None:
    assert issubclass(PadNotFoundError, EpadError)
    assert issubclass(EmptyCaptureError, EpadError)
    assert issubclass(InvalidFormatError, EpadError)


def test_pad_not_found_is_also_oserror() -> None:
    """A caller doing `except OSError` today must still catch this."""
    assert issubclass(PadNotFoundError, OSError)
    with pytest.raises(OSError):
        raise PadNotFoundError("no pad")


def test_empty_capture_is_also_value_error() -> None:
    """A caller doing `except ValueError` today must still catch this."""
    assert issubclass(EmptyCaptureError, ValueError)
    with pytest.raises(ValueError):
        raise EmptyCaptureError("empty")


def test_invalid_format_is_also_value_error() -> None:
    assert issubclass(InvalidFormatError, ValueError)
    with pytest.raises(ValueError):
        raise InvalidFormatError("bad format")


def test_pad_not_found_keeps_original_cause() -> None:
    original = OSError("open failed")
    try:
        try:
            raise original
        except OSError as err:
            raise PadNotFoundError("friendly message") from err
    except PadNotFoundError as caught:
        assert caught.__cause__ is original


def test_exceptions_are_picklable() -> None:
    """Multiple-inheritance exceptions can trip up pickle; confirm they don't."""
    restored = pickle.loads(pickle.dumps(PadNotFoundError("no pad")))
    assert isinstance(restored, PadNotFoundError)
    assert str(restored) == "no pad"
