# Examples

Read these roughly in order - each one builds on the idea before it.

| # | Script | Shows | Needs a pad? |
|---|---|---|---|
| 01 | [`01_check_connection.py`](01_check_connection.py) | Confirm the pad is connected, catch `PadNotFoundError` | yes |
| 02 | [`02_capture_and_save.py`](02_capture_and_save.py) | Capture one stroke and save it as PNG + JSON + InkML | yes |
| 03 | [`03_watch_mode.py`](03_watch_mode.py) | Auto-save on every pen touch, with a graceful `stop` switch | yes |
| 04 | [`04_live_callback.py`](04_live_callback.py) | Stream samples live via `on_sample`, not just after the fact | yes |
| 05 | [`05_handle_no_device.py`](05_handle_no_device.py) | Catch `PadNotFoundError` on purpose, using a bogus device ID | no |
| 06 | [`06_convert_file_to_png.py`](06_convert_file_to_png.py) | Load a saved `.json`/`.inkml` file and render it, as a library call | no |

Run any of them with:

```bash
uv run python examples/<script>.py
```

For a live browser demo instead of a script, see [`web_demo/`](web_demo/).

## Which ones need the real pad?

01-04 talk to real hardware and won't do much without an ePad plugged in.
05 and 06 are deliberately hardware-free, so they always run - 05 by using
a device ID that can never exist, 06 by loading a saved file instead of
capturing live.
