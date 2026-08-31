"""Exceptions for epad_signature_pad_hid_driver.

Each concrete exception has TWO parents: EpadError (so new code can catch
everything this package raises with one clause) and the built-in exception
type this package already raised before this class existed (so old code
doing `except OSError` or `except ValueError` keeps working unchanged).

Always construct these with exactly one string argument. OSError's own
__new__ treats a two-argument call specially (an errno + message pair, and
for a couple of specific errno values it silently returns a *different*
built-in subclass instead of the one you asked for) - PadNotFoundError
inherits that behaviour from OSError, so a second positional argument
would trigger it unintentionally.
"""

from __future__ import annotations


class EpadError(Exception):
    """Base class for every exception this package raises on purpose."""


class PadNotFoundError(EpadError, OSError):
    """The pad could not be opened (not plugged in, or already open elsewhere)."""


class EmptyCaptureError(EpadError, ValueError):
    """render_signature() was given zero pen-down samples to draw."""


class InvalidFormatError(EpadError, ValueError):
    """A .json/.inkml file is malformed, or its extension is unrecognized."""
