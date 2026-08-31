"""Stream live decoded ePad readings to a browser page over Server-Sent
Events (SSE) - standard library only, no new dependency.

Usage:
    uv run python examples/web_demo/server.py                       # real pad
    uv run python examples/web_demo/server.py --replay FILE.json    # no pad needed
    uv run python examples/web_demo/server.py --host 0.0.0.0 --port 8080

See README.md in this directory for what the page does and its limits
(in particular: whether a "Save As" dialog appears is the visitor's own
browser setting, not something this page can force).
"""

from __future__ import annotations

import argparse
import json
import queue
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from epad_signature_pad_hid_driver import PadNotFoundError, PenSample
from epad_signature_pad_hid_driver.device import open_pad
from epad_signature_pad_hid_driver.formats import load_json
from epad_signature_pad_hid_driver.protocol import (
    PRODUCT_ID,
    REPORT_LENGTH,
    VENDOR_ID,
    decode_report,
)

INDEX_PATH = Path(__file__).with_name("index.html")
QUEUE_MAXSIZE = 256  # bounds memory if a browser tab stops reading
KEEPALIVE_SECONDS = 15.0
POLL_SECONDS = 1.0  # how often an /events handler re-checks server.stopping


def sample_to_sse_frame(sample: PenSample) -> bytes:
    """One PenSample as a complete SSE frame: a `data:` line, then the
    blank line that terminates an SSE event - both are required."""
    payload = {
        "x": sample.x,
        "y": sample.y,
        "pressure": sample.pressure,
        "touch": sample.touch,
        "t": sample.t,
    }
    return f"data: {json.dumps(payload)}\n\n".encode()


def error_sse_frame(message: str) -> bytes:
    return f"event: error\ndata: {json.dumps({'error': message})}\n\n".encode()


KEEPALIVE_FRAME = b": keepalive\n\n"


class Broadcaster:
    """Fans PenSamples out to any number of subscriber queues.

    One reader (a live pad, or a replay file) calls publish(); each
    /events request subscribes its own bounded queue. publish() never
    blocks: if a subscriber's queue is full (a slow or backgrounded
    browser tab not reading fast enough), the oldest queued frame is
    dropped to make room, rather than stalling every other client - the
    pad streams at roughly 52 samples/second, so an unbounded queue would
    otherwise grow without limit.
    """

    def __init__(self, maxsize: int = QUEUE_MAXSIZE) -> None:
        self._maxsize = maxsize
        self._subscribers: set[queue.Queue[bytes]] = set()
        self._lock = threading.Lock()
        self.disconnected: str | None = None

    def subscribe(self) -> "queue.Queue[bytes]":
        q: "queue.Queue[bytes]" = queue.Queue(maxsize=self._maxsize)
        with self._lock:
            self._subscribers.add(q)
        return q

    def unsubscribe(self, q: "queue.Queue[bytes]") -> None:
        with self._lock:
            self._subscribers.discard(q)

    def subscriber_count(self) -> int:
        with self._lock:
            return len(self._subscribers)

    def publish(self, frame: bytes) -> None:
        with self._lock:
            subscribers = list(self._subscribers)
        for q in subscribers:
            try:
                q.put_nowait(frame)
            except queue.Full:
                try:
                    q.get_nowait()
                except queue.Empty:
                    pass
                try:
                    q.put_nowait(frame)
                except queue.Full:
                    pass  # a second full in a row: give up on this frame

    def mark_disconnected(self, reason: str) -> None:
        self.disconnected = reason
        self.publish(error_sse_frame(reason))


def run_live_reader(
    broadcaster: Broadcaster,
    stop: threading.Event,
    vendor_id: int = VENDOR_ID,
    product_id: int = PRODUCT_ID,
) -> None:
    """Read from the real pad until `stop` fires, publishing every sample.

    The pad is exclusive - verified live that a second open fails, both
    in-process and cross-process, so this and any other pad-holding
    process (the CLI's own `watch`, for instance) can't run at once.

    What exactly d.read() raises if the pad is unplugged mid-stream is
    NOT verified live yet (see HARDWARE_NOTES.md) - caught here as a
    plain OSError, the same broad type this package already uses
    elsewhere for pad failures, rather than guessing a more specific one.
    """
    try:
        d = open_pad(vendor_id, product_id)
    except PadNotFoundError as err:
        broadcaster.mark_disconnected(str(err))
        return
    start = time.monotonic()
    try:
        while not stop.is_set():
            try:
                report = d.read(REPORT_LENGTH, timeout_ms=50)
            except OSError as err:
                broadcaster.mark_disconnected(f"pad disconnected: {err}")
                return
            if report and len(report) >= REPORT_LENGTH:
                sample = decode_report(bytes(report), t=time.monotonic() - start)
                broadcaster.publish(sample_to_sse_frame(sample))
    finally:
        d.close()


def run_replay_reader(
    broadcaster: Broadcaster,
    stop: threading.Event,
    path: Path,
    loop: bool = False,
    speed: float = 1.0,
) -> None:
    """Replay a saved .json capture through the same publish() path a live
    pad would use - so the demo (and this module's tests) work with no
    pad attached. speed<=0 means "no delay, publish as fast as possible".
    """
    samples = load_json(path)
    if not samples:
        return
    while not stop.is_set():
        last_t = 0.0
        for sample in samples:
            if stop.is_set():
                return
            if speed > 0:
                delay = max(0.0, (sample.t - last_t) / speed)
                if delay:
                    stop.wait(delay)
            broadcaster.publish(sample_to_sse_frame(sample))
            last_t = sample.t
        if not loop:
            return


class DemoServer(ThreadingHTTPServer):
    # Load-bearing, not an aside: measured live that with daemon_threads
    # left False, server_close() never returned while a single /events
    # connection was still open (the request-handling thread blocks
    # reading its queue and is never joined). With this True,
    # ThreadingMixIn.server_close() doesn't wait on handler threads.
    daemon_threads = True
    allow_reuse_address = True

    def __init__(
        self, server_address: tuple[str, int], broadcaster: Broadcaster
    ) -> None:
        super().__init__(server_address, Handler)
        self.broadcaster = broadcaster
        self.stopping = threading.Event()

    def shutdown_cleanly(self) -> None:
        """Signal every open /events handler to stop, then stop accepting."""
        self.stopping.set()
        self.shutdown()


class Handler(BaseHTTPRequestHandler):
    # The stdlib default. Verified live: a `data:`/`\n\n`-framed response
    # with Content-Type: text/event-stream, Cache-Control: no-cache,
    # Connection: close, and no Content-Length streams to a real
    # EventSource client with ~0ms latency per frame under HTTP/1.0 -
    # no chunked encoding needed. StreamRequestHandler.wbufsize is 0
    # (unbuffered), so there's no separate flush() concern either.
    protocol_version = "HTTP/1.0"
    server: DemoServer

    def log_message(self, format: str, *args: object) -> None:  # noqa: A002
        pass  # keep demo/test output quiet; failures still surface via responses

    def do_GET(self) -> None:
        if self.path == "/":
            self._serve_index()
        elif self.path == "/events":
            self._serve_events()
        elif self.path == "/healthz":
            self._serve_healthz()
        else:
            self.send_error(404)

    def _serve_index(self) -> None:
        # Path(__file__).with_name(...) so this works regardless of the
        # process's current working directory.
        body = INDEX_PATH.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _serve_healthz(self) -> None:
        body = json.dumps(
            {"disconnected": self.server.broadcaster.disconnected}
        ).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _serve_events(self) -> None:
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "close")
        self.end_headers()

        q = self.server.broadcaster.subscribe()
        last_activity = time.monotonic()
        try:
            while not self.server.stopping.is_set():
                try:
                    frame = q.get(timeout=POLL_SECONDS)
                except queue.Empty:
                    if time.monotonic() - last_activity >= KEEPALIVE_SECONDS:
                        self.wfile.write(KEEPALIVE_FRAME)
                        last_activity = time.monotonic()
                    continue
                self.wfile.write(frame)
                last_activity = time.monotonic()
        except OSError:
            # The client went away mid-write. Windows and POSIX raise
            # different concrete subclasses here (BrokenPipeError,
            # ConnectionResetError, ConnectionAbortedError, or a bare
            # OSError for a closed handle) - OSError is the parent of
            # all of them, so it's caught here rather than a narrower list.
            pass
        finally:
            self.server.broadcaster.unsubscribe(q)


def _build_server(host: str, port: int, broadcaster: Broadcaster) -> DemoServer:
    return DemoServer((host, port), broadcaster)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Stream live ePad readings to a browser over SSE."
    )
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument(
        "--replay",
        type=Path,
        default=None,
        help="Replay a saved .json capture instead of reading a live pad",
    )
    parser.add_argument(
        "--replay-loop",
        action="store_true",
        help="Loop the replay file instead of stopping after one pass",
    )
    parser.add_argument(
        "--replay-speed",
        type=float,
        default=1.0,
        help="Replay speed multiplier (2.0 = twice as fast; default 1.0)",
    )
    parser.add_argument(
        "--no-delay",
        action="store_true",
        help="Replay every sample immediately, ignoring its recorded timing",
    )
    args = parser.parse_args()

    broadcaster = Broadcaster()
    stop = threading.Event()

    if args.replay is not None:
        reader = threading.Thread(
            target=run_replay_reader,
            args=(broadcaster, stop, args.replay, args.replay_loop),
            kwargs={"speed": 0.0 if args.no_delay else args.replay_speed},
            daemon=True,
        )
        print(f"Replaying {args.replay} (no pad needed).")
    else:
        reader = threading.Thread(
            target=run_live_reader, args=(broadcaster, stop), daemon=True
        )
    reader.start()

    server = _build_server(args.host, args.port, broadcaster)
    print(f"Serving on http://{args.host}:{args.port}/ - press Ctrl+C to stop.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping...")
    finally:
        stop.set()
        server.shutdown_cleanly()
        server.server_close()
        reader.join(timeout=5.0)


if __name__ == "__main__":
    main()
