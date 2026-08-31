"""Minimal library usage: capture one 5-second stroke and save it three ways.

- signature.png    a picture of what was drawn
- signature.json   every reading (time, x, y, pressure) - re-render it, or
                    store it in a database that can't hold images
- signature.inkml   the same data in the W3C InkML standard, for other tools

Needs a real pad plugged in.

Run with:
    uv run python examples/02_capture_and_save.py
"""

from datetime import datetime
from pathlib import Path

from epad_signature_pad_hid_driver import (
    PenSample,
    capture,
    render_signature,
    save_inkml,
    save_json,
)

OUTPUT_DIR = Path("output")


def main() -> None:
    print("Draw on the pad now - capturing for 5 seconds...")
    captured_at = datetime.now()
    samples: list[PenSample] = []
    capture(seconds=5.0, on_sample=samples.append)

    OUTPUT_DIR.mkdir(exist_ok=True)
    render_signature(samples, OUTPUT_DIR / "example_signature.png")
    save_json(samples, OUTPUT_DIR / "example_signature.json", captured_at=captured_at)
    save_inkml(samples, OUTPUT_DIR / "example_signature.inkml", captured_at=captured_at)

    print(
        f"Saved {len(samples)} samples to {OUTPUT_DIR}/example_signature.{{png,json,inkml}}"
    )


if __name__ == "__main__":
    main()
