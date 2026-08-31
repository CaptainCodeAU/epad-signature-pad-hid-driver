"""Auto-save a signature on every pen touch, with a graceful stop switch.

This is the same loop the `watch` CLI command runs, used directly as a
library. Here it stops itself after 30 seconds via a threading.Event,
instead of relying on Ctrl+C (which still works too, for a script you run
and stop yourself).

Needs a real pad plugged in.

Run with:
    uv run python examples/03_watch_mode.py
"""

import threading
from pathlib import Path

from epad_signature_pad_hid_driver import watch

OUTPUT_DIR = Path("output")
RUN_FOR_SECONDS = 30.0


def main() -> None:
    stop = threading.Event()
    timer = threading.Timer(RUN_FOR_SECONDS, stop.set)
    timer.start()

    print(f"Watching for pen touches for {RUN_FOR_SECONDS:.0f}s. Draw on the pad...")
    try:
        for result in watch(OUTPUT_DIR, stop=stop):
            note = " (stopped early - marked truncated)" if result.truncated else ""
            print(f"Saved {result.png_path.name} - {len(result.samples)} samples{note}")
    finally:
        timer.cancel()
    print("Done.")


if __name__ == "__main__":
    main()
