"""Tests for device.py: the only file that imports `hid`.

open_pad()/PadConnection are tested against FakePad/RaisingPad, so nothing
here needs real hardware except the one @requires_pad test at the bottom,
which is skipped automatically when no pad is attached.
"""

import hid
import pytest

from epad_signature_pad_hid_driver.device import PadConnection, open_pad, run
from epad_signature_pad_hid_driver.exceptions import PadNotFoundError
from epad_signature_pad_hid_driver.protocol import PRODUCT_ID, VENDOR_ID
from tests.helpers import FakePad, RaisingPad, requires_pad


def test_open_pad_uses_default_ids(monkeypatch: pytest.MonkeyPatch) -> None:
    pad = FakePad([])
    monkeypatch.setattr(hid, "device", lambda: pad)

    open_pad()

    assert pad.opened_with == (VENDOR_ID, PRODUCT_ID)


def test_open_pad_accepts_custom_ids(monkeypatch: pytest.MonkeyPatch) -> None:
    pad = FakePad([])
    monkeypatch.setattr(hid, "device", lambda: pad)

    open_pad(vendor_id=0x1111, product_id=0x2222)

    assert pad.opened_with == (0x1111, 0x2222)


def test_open_pad_sets_nonblocking(monkeypatch: pytest.MonkeyPatch) -> None:
    pad = FakePad([])
    monkeypatch.setattr(hid, "device", lambda: pad)

    open_pad()

    assert pad.nonblocking_calls == [1]


def test_open_pad_raises_pad_not_found_on_oserror(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(hid, "device", lambda: RaisingPad(OSError("open failed")))

    with pytest.raises(PadNotFoundError):
        open_pad()


def test_open_pad_keeps_the_original_cause(monkeypatch: pytest.MonkeyPatch) -> None:
    original = OSError("open failed")
    monkeypatch.setattr(hid, "device", lambda: RaisingPad(original))

    with pytest.raises(PadNotFoundError) as excinfo:
        open_pad()

    assert excinfo.value.__cause__ is original


def test_pad_not_found_message_names_the_ids_and_mentions_already_open(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Since a real live check proved "unplugged" and "busy" raise the
    identical OSError, the message must not claim it's only one or the
    other."""
    monkeypatch.setattr(hid, "device", lambda: RaisingPad(OSError("open failed")))

    with pytest.raises(PadNotFoundError, match="already open"):
        open_pad(vendor_id=0x04DF, product_id=0x0012)


def test_pad_connection_closes_on_exit(monkeypatch: pytest.MonkeyPatch) -> None:
    pad = FakePad([])
    monkeypatch.setattr(hid, "device", lambda: pad)

    with PadConnection() as handle:
        assert handle is pad

    assert pad.closed is True


def test_pad_connection_closes_even_when_body_raises(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pad = FakePad([])
    monkeypatch.setattr(hid, "device", lambda: pad)

    with pytest.raises(RuntimeError):
        with PadConnection():
            raise RuntimeError("boom")

    assert pad.closed is True


def test_run_returns_product_string(monkeypatch: pytest.MonkeyPatch) -> None:
    pad = FakePad([])
    monkeypatch.setattr(hid, "device", lambda: pad)

    result = run()

    assert "ePadLink USB ePad" in result


def test_run_reports_custom_ids(monkeypatch: pytest.MonkeyPatch) -> None:
    pad = FakePad([])
    monkeypatch.setattr(hid, "device", lambda: pad)

    result = run(vendor_id=0x1111, product_id=0x2222)

    assert "0x1111" in result
    assert "0x2222" in result


@requires_pad
def test_run() -> None:
    """Test the device run() function against real hardware."""
    from epad_signature_pad_hid_driver.device import run as real_run

    result = real_run()
    assert isinstance(result, str)
    assert len(result) > 0
