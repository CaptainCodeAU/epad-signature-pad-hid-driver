"""Render captured pen samples into a signature image."""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw

from epad_signature_pad_hid_driver.core import PenSample

PADDING = 20
BACKGROUND = "white"
INK_COLOR = "black"
MIN_STROKE_WIDTH = 1
MAX_STROKE_WIDTH = 4
MAX_PRESSURE = 127


def render_signature(samples: list[PenSample], path: Path) -> None:
    """Render pen-down strokes in samples to a PNG at path.

    Separate strokes (pen lifted and touched down again) are drawn as
    separate lines, never connected. Raises ValueError if nothing was
    touched during the capture.
    """
    touched = [s for s in samples if s.touch]
    if not touched:
        raise ValueError("No pen-down samples to render")

    min_x = min(s.x for s in touched)
    max_x = max(s.x for s in touched)
    min_y = min(s.y for s in touched)
    max_y = max(s.y for s in touched)
    width = (max_x - min_x) + PADDING * 2
    height = (max_y - min_y) + PADDING * 2

    image = Image.new("RGB", (width, height), BACKGROUND)
    draw = ImageDraw.Draw(image)

    def to_point(sample: PenSample) -> tuple[int, int]:
        return (sample.x - min_x + PADDING, sample.y - min_y + PADDING)

    prev: PenSample | None = None
    for sample in samples:
        if not sample.touch:
            prev = None
            continue
        if prev is not None:
            stroke_width = MIN_STROKE_WIDTH + round(
                (sample.pressure / MAX_PRESSURE) * (MAX_STROKE_WIDTH - MIN_STROKE_WIDTH)
            )
            draw.line(
                [to_point(prev), to_point(sample)], fill=INK_COLOR, width=stroke_width
            )
        prev = sample

    path.parent.mkdir(parents=True, exist_ok=True)
    image.save(path)
