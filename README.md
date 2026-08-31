# epad-signature-pad-hid-driver

Unofficial Python driver for the ePadLink "ePad" USB signature pad (VID `0x04DF`,
PID `0x0012`), talking to it directly over raw USB HID.

**No vendor driver, no Windows, no Linux-only install required.** ePadLink's own
software only ships for Windows and Linux. This library reads the pad's own HID
report descriptor to decode X, Y, pressure, and touch state directly — confirmed
working on macOS, and should work anywhere [`hidapi`](https://pypi.org/project/hidapi/)
does (Windows, Linux, macOS).

This is a from-scratch driver based on the device's own published HID descriptor,
not a reverse-engineered guess and not affiliated with ePadLink / Interlink Electronics.

## Install

```bash
uv add epad-signature-pad-hid-driver   # or: pip install epad-signature-pad-hid-driver
```

Or clone and run locally:

```bash
git clone https://github.com/CaptainCodeAU/epad-signature-pad-hid-driver.git
cd epad-signature-pad-hid-driver
uv sync
```

## Usage

**Confirm the pad is connected:**

```bash
uv run epad-signature-pad-hid-driver
```

**Print live decoded pen data for a fixed window (default 15s):**

```bash
uv run epad-signature-pad-hid-driver capture 15
```

**Auto-save a signature image on every pen touch** — starts recording the moment
the pen touches down, records for a fixed window (default 5s), saves a PNG to
`output/`, waits 2s, then listens for the next touch. Runs until Ctrl+C:

```bash
uv run epad-signature-pad-hid-driver watch
```

**As a library** — see [`examples/basic_capture.py`](examples/basic_capture.py):

```python
from epad_signature_pad_hid_driver import capture, render_signature

samples = []
capture(seconds=5.0, on_sample=samples.append)
render_signature(samples, "output/signature.png")
```

## How it works

The pad exposes a standard 6-byte USB HID input report (no Report ID byte):

| Bytes | Field |
|---|---|
| byte 0, bit 0 | button1 |
| byte 0, bit 1 | button2 |
| byte 0, bits 2-4 | vendor-defined 3-bit field (meaning undocumented) |
| byte 0, bit 5 | touch |
| byte 0, bit 6 | in_range |
| bytes 1-2 | X, 16-bit little-endian |
| bytes 3-4 | Y, 16-bit little-endian |
| byte 5, bits 0-6 | pressure (0-127) |

This layout was read directly from the pad's own HID report descriptor
(`hid.device.get_report_descriptor()`), not guessed from captured traffic.
See [`src/epad_signature_pad_hid_driver/core.py`](src/epad_signature_pad_hid_driver/core.py)
for the full decode.

## Development

```bash
uv sync --extra dev        # install with dev dependencies
uv run pytest              # run tests
uv run ruff check .        # lint
uv run ruff format .       # format
uv run mypy src/           # type check
```

## License

MIT
