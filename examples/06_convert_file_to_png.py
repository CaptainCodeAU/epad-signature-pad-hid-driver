"""Load a saved .json or .inkml file and render it to PNG - as a library
call, not via the `convert` CLI command (see README for that instead).

Needs no hardware. Uses examples/sample_capture.json if present (a real,
short capture off the actual pad - not a real signature, just a scribble
recorded to prove the file format round-trips real hardware data). If that
file isn't there yet, falls back to a tiny synthetic sample so this script
always has something to run against.

Run with:
    uv run python examples/06_convert_file_to_png.py
"""

from datetime import datetime
from pathlib import Path

from epad_signature_pad_hid_driver import PenSample, render_signature, save_json
from epad_signature_pad_hid_driver.formats import load_inkml, load_json

EXAMPLES_DIR = Path(__file__).parent
SAMPLE_CAPTURE = EXAMPLES_DIR / "sample_capture.json"
OUTPUT_DIR = Path("output")


def _synthetic_fallback_samples() -> list[PenSample]:
    """A tiny made-up zigzag, used only if sample_capture.json is missing."""
    points = [(10, 10), (30, 40), (50, 10), (70, 40)]
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


def main() -> None:
    OUTPUT_DIR.mkdir(exist_ok=True)

    if SAMPLE_CAPTURE.exists():
        print(f"Loading real captured data from {SAMPLE_CAPTURE}")
        samples = load_json(SAMPLE_CAPTURE)
    else:
        print(f"{SAMPLE_CAPTURE} not found - using a small synthetic sample instead")
        samples = _synthetic_fallback_samples()
        # So the .inkml loader path below has something real to load too.
        save_json(samples, OUTPUT_DIR / "synthetic.json", captured_at=datetime.now())

    png_path = OUTPUT_DIR / "loaded_from_json.png"
    render_signature(samples, png_path)
    print(f"Rendered {len(samples)} samples to {png_path}")

    # load_inkml works the same way, for a .inkml file:
    inkml_path = EXAMPLES_DIR / "sample_capture.inkml"
    if inkml_path.exists():
        inkml_samples = load_inkml(inkml_path)
        inkml_png = OUTPUT_DIR / "loaded_from_inkml.png"
        render_signature(inkml_samples, inkml_png)
        print(f"Rendered {len(inkml_samples)} samples to {inkml_png}")


if __name__ == "__main__":
    main()
