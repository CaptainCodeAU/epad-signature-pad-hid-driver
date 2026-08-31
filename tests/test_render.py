"""Tests for render.py: turning captured samples into a PNG."""

import pytest
from PIL import Image

from epad_signature_pad_hid_driver.exceptions import EmptyCaptureError
from epad_signature_pad_hid_driver.protocol import PenSample
from epad_signature_pad_hid_driver.render import PADDING, render_signature
from tests.helpers import stroke_samples, touched_samples


def test_render_signature(tmp_path) -> None:
    samples = touched_samples([(100, 100), (110, 105), (120, 110)])

    out_path = tmp_path / "signature.png"
    render_signature(samples, out_path)

    assert out_path.exists()
    with Image.open(out_path) as image:
        assert image.size[0] > 0
        assert image.size[1] > 0


def test_render_signature_empty_raises_empty_capture_error(tmp_path) -> None:
    samples = [
        PenSample(
            button1=False,
            button2=False,
            vendor_field=0,
            touch=False,
            in_range=False,
            x=0,
            y=0,
            pressure=0,
            raw=b"\x00" * 6,
        )
    ]
    with pytest.raises(EmptyCaptureError, match="No pen-down samples"):
        render_signature(samples, tmp_path / "signature.png")


def test_render_signature_empty_still_catchable_as_value_error(tmp_path) -> None:
    """Back-compat guard: code written against the old plain ValueError
    must keep working unchanged."""
    samples: list[PenSample] = []
    with pytest.raises(ValueError, match="No pen-down samples"):
        render_signature(samples, tmp_path / "signature.png")


def test_render_signature_separates_strokes(tmp_path) -> None:
    # Two short vertical strokes, far apart, with a pen lift between them.
    samples = stroke_samples(
        [
            [(10, 10), (10, 50)],
            [(200, 10), (200, 50)],
        ]
    )
    out_path = tmp_path / "signature.png"

    render_signature(samples, out_path)

    with Image.open(out_path) as image:
        pixels = image.load()
        min_x, max_x = 10, 200
        min_y = 10
        stroke1_x = min_x - min_x + PADDING
        stroke2_x = max_x - min_x + PADDING
        mid_y = (10 - min_y + PADDING + 50 - min_y + PADDING) // 2
        bridge_x = (stroke1_x + stroke2_x) // 2

        assert pixels[stroke1_x, mid_y] == (0, 0, 0)
        assert pixels[stroke2_x, mid_y] == (0, 0, 0)
        assert pixels[bridge_x, mid_y] == (255, 255, 255)


def test_render_signature_single_point_writes_a_valid_png(tmp_path) -> None:
    """A single touched sample draws no line (nothing to connect it to),
    but must still produce a real, non-empty PNG - verified this only
    holds because PADDING > 0: width/height are (max-min) + PADDING*2, so
    a single point gives PADDING*2 on each side, never zero. At PADDING=0
    this would crash PIL with "cannot write empty image"."""
    samples = touched_samples([(50, 50)])
    out_path = tmp_path / "signature.png"

    render_signature(samples, out_path)

    with Image.open(out_path) as image:
        assert image.size == (PADDING * 2, PADDING * 2)
        assert all(
            image.getpixel((x, y)) == (255, 255, 255)
            for x in range(image.size[0])
            for y in range(image.size[1])
        )
