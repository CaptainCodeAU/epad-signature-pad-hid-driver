"""Shared test doubles and sample builders, used across the test_*.py files.

This is a plain module, not conftest.py - conftest.py is reserved for
pytest fixtures. Because tests/__init__.py makes `tests` a real package,
these must be imported as `from tests.helpers import ...`, not
`from helpers import ...`.
"""

from __future__ import annotations

import time

import hid
import pytest

from epad_signature_pad_hid_driver.protocol import PRODUCT_ID, VENDOR_ID, PenSample

requires_pad = pytest.mark.skipif(
    not any(
        d["vendor_id"] == VENDOR_ID and d["product_id"] == PRODUCT_ID
        for d in hid.enumerate()
    ),
    reason="ePad hardware not connected",
)


class FakePad:
    """Stands in for hid.device() so capture()/watch() can be tested without real hardware."""

    def __init__(
        self,
        reports: list[bytes],
        raise_when_exhausted: type[BaseException] | None = None,
        raise_after_seconds: float = 0.0,
    ) -> None:
        self._reports = list(reports)
        self._raise_when_exhausted = raise_when_exhausted
        self._raise_after = time.monotonic() + raise_after_seconds
        self.opened_with: tuple[int, int] | None = None
        self.nonblocking_calls: list[int] = []
        self.closed = False

    def open(self, vendor_id: int, product_id: int) -> None:
        self.opened_with = (vendor_id, product_id)

    def set_nonblocking(self, value: int) -> None:
        self.nonblocking_calls.append(value)

    def read(self, length: int, timeout_ms: int = 0) -> list[int]:
        if self._reports:
            return list(self._reports.pop(0))
        if (
            self._raise_when_exhausted is not None
            and time.monotonic() >= self._raise_after
        ):
            raise self._raise_when_exhausted
        return []

    def get_product_string(self) -> str:
        return "ePadLink USB ePad"

    def close(self) -> None:
        self.closed = True


class RaisingPad:
    """Stands in for hid.device() when open() itself should fail."""

    def __init__(self, error: BaseException) -> None:
        self._error = error

    def open(self, vendor_id: int, product_id: int) -> None:
        raise self._error

    def set_nonblocking(self, value: int) -> None:  # pragma: no cover - unreachable
        pass

    def read(self, length: int, timeout_ms: int = 0) -> list[int]:  # pragma: no cover
        return []

    def get_product_string(self) -> str:  # pragma: no cover - unreachable
        return ""

    def close(self) -> None:  # pragma: no cover - unreachable
        pass


def raw_report(x: int, y: int, pressure: int, touch: bool) -> bytes:
    status = (0b1 << 5) if touch else 0
    return bytes([status, x & 0xFF, x >> 8, y & 0xFF, y >> 8, pressure])


def touched_samples(points: list[tuple[int, int]]) -> list[PenSample]:
    return [
        PenSample(
            button1=False,
            button2=False,
            vendor_field=0,
            touch=True,
            in_range=False,
            x=x,
            y=y,
            pressure=64,
            raw=b"\x00" * 6,
            t=i * 0.02,
        )
        for i, (x, y) in enumerate(points)
    ]


def stroke_samples(strokes: list[list[tuple[int, int]]]) -> list[PenSample]:
    """Build samples for multiple pen-down strokes, with a lift between each."""
    samples: list[PenSample] = []
    t = 0.0
    for stroke_index, stroke in enumerate(strokes):
        if stroke_index > 0:
            last = samples[-1]
            samples.append(
                PenSample(
                    button1=False,
                    button2=False,
                    vendor_field=0,
                    touch=False,
                    in_range=False,
                    x=last.x,
                    y=last.y,
                    pressure=0,
                    raw=b"\x00" * 6,
                    t=t,
                )
            )
            t += 0.02
        for x, y in stroke:
            samples.append(
                PenSample(
                    button1=False,
                    button2=False,
                    vendor_field=0,
                    touch=True,
                    in_range=False,
                    x=x,
                    y=y,
                    pressure=64,
                    raw=b"\x00" * 6,
                    t=t,
                )
            )
            t += 0.02
    return samples
