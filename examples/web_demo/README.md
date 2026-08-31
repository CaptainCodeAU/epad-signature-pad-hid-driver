# Live signature web demo

A small local server that streams live decoded pen readings to a browser
page, which draws the signature on a `<canvas>` as it happens, with a
button to save the result as a PNG.

- `server.py` - a standard-library-only Python server (`http.server`, no
  new dependency). Reads the pad and streams each decoded reading to any
  connected browser tab over [Server-Sent Events](https://developer.mozilla.org/en-US/docs/Web/API/Server-sent_events)
  (SSE) - a plain HTTP response the browser keeps open and reads line by
  line, not WebSockets.
- `index.html` - the page. Draws each incoming point on a `<canvas>` live,
  and has a Save button.

## Run it

With a real pad plugged in:

```bash
uv run python examples/web_demo/server.py
```

Then open <http://127.0.0.1:8765/> in a browser and draw on the pad.

Without a pad, replay a saved capture instead - `examples/sample_capture.json`
(a short scribble, not a real signature) or any file `watch`/`capture`
produced:

```bash
uv run python examples/web_demo/server.py --replay examples/sample_capture.json --replay-loop --no-delay
```

`--no-delay` is there because `sample_capture.json` starts about 5 seconds
in (the real gap between starting the capture and actually touching the
pen down) - without it, `--replay-loop` faithfully replays that same
5-second pause before drawing starts on *every* loop pass, which is more
realistic but makes a first look at the demo feel like nothing is
happening. Drop `--no-delay` if you want the real recorded pacing instead.

Other flags: `--host`/`--port` to change where it listens, `--replay-speed 2.0`
to replay twice as fast (ignored when `--no-delay` is also given).

## The pad is exclusive

This server can't run at the same time as the CLI's `watch`/`capture`
commands, or a second copy of itself - the pad can only be opened by one
program at a time (verified live: a second open fails, both from the same
process and a separate one). Use `--replay` if you need the page working
while another program is also using the pad.

## About the Save button

Clicking Save turns the canvas into a PNG and triggers the browser's
normal file-download flow (a real `<a download>` click, not anything
custom). **Whether that actually shows a "Save As" dialog, or just saves
straight into a default downloads folder, depends entirely on the
visitor's own browser settings - this page has no way to force one
behavior or the other.**

## The canvas's coordinate scaling

The pad's raw X/Y values do **not** span the full logical range its HID
descriptor declares (0-2896, 0-1370) - tracing the pad's actual physical
edges only ever produces values up to roughly 38%/41% of that, confirmed
live twice (see `docs/HARDWARE_NOTES.md`). `index.html` scales incoming
samples against that measured reachable range (`USABLE_X_MAX`/
`USABLE_Y_MAX` in its script), not the descriptor's declared max - using
the declared max instead would only ever fill a corner of the canvas.

## What's actually verified here

Verified live, including watching a real signature appear on the
`<canvas>` as it was drawn and downloading it with the Save button:
the pad really is exclusive (second-open fails the same way in-process
and cross-process); the SSE response format used here (`HTTP/1.0`,
`Connection: close`, no `Content-Length`) genuinely streams to a real
`EventSource` client with effectively no added latency; `daemon_threads
= True` is required for the server to shut down cleanly while a browser
tab is connected; unplugging the pad mid-stream makes the reader's read
call raise `OSError("read error")`, which the reader already catches and
reports to the browser as a disconnect; and the coordinate scaling above
makes a stroke that reaches the pad's real edges also reach the canvas's
edges. See `docs/HARDWARE_NOTES.md` for the exact behaviour observed.
