"""Stream samples live as they happen, instead of only seeing them after
the capture ends.

capture()'s on_sample callback runs once per reading, in real time - so
this prints each point of the stroke as the pen moves, not a summary
printed afterwards (compare to 02_capture_and_save.py, which just
collects samples into a list).

Needs a real pad plugged in.

Run with:
    uv run python examples/04_live_callback.py
"""

from epad_signature_pad_hid_driver import PenSample, capture

CAPTURE_SECONDS = 8.0


def on_sample(sample: PenSample) -> None:
    if sample.touch:
        print(
            f"t={sample.t:6.3f}s  x={sample.x:5d}  y={sample.y:5d}  pressure={sample.pressure:3d}"
        )
    else:
        print("(pen up)")


def main() -> None:
    print(f"Draw on the pad now - streaming live for {CAPTURE_SECONDS:.0f} seconds...")
    count = capture(seconds=CAPTURE_SECONDS, on_sample=on_sample)
    print(f"Done. Streamed {count} readings live.")


if __name__ == "__main__":
    main()
