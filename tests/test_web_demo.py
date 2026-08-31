"""Tests for examples/web_demo/server.py.

Live pen-on-glass drawing through a real browser is NOT covered by this
automated suite - that's inherently manual (a real pad, a real browser,
a real hand). It HAS been verified by hand, once, against real hardware:
see the "What's actually verified here" section of
examples/web_demo/README.md. These tests instead prove the plumbing: SSE
frame formatting, fan-out and backpressure, replay playback, and exactly
one real-socket test of the HTTP/SSE surface (index page, health
endpoint, a bounded read of live frames, and that a disconnected client's
queue is cleaned up) - deliberately just one, to keep this suite from
hanging or flaking on socket timing.

server.py lives outside the installed package (examples/ is not on
sys.path and isn't a Python package), so it's loaded here by file path,
the same way test_examples.py loads the numbered example scripts.
server.py is therefore not covered by this project's --cov=
(epad_signature_pad_hid_driver) coverage number - stated here plainly,
not left implicit.
"""

import importlib.util
import json
import threading
import time
import urllib.request
from datetime import datetime
from pathlib import Path
from types import ModuleType

import pytest

from epad_signature_pad_hid_driver.formats import save_json
from epad_signature_pad_hid_driver.protocol import PenSample
from tests.helpers import touched_samples

WEB_DEMO_DIR = Path(__file__).parent.parent / "examples" / "web_demo"


def _load_server_module() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "web_demo_server", WEB_DEMO_DIR / "server.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def server_module() -> ModuleType:
    return _load_server_module()


def _make_capture(tmp_path: Path, points: list[tuple[int, int]]) -> Path:
    path = tmp_path / "capture.json"
    save_json(touched_samples(points), path, captured_at=datetime(2026, 1, 1))
    return path


# ---- frame formatting (no sockets) ----


def test_sample_to_sse_frame_format(server_module: ModuleType) -> None:
    sample = PenSample(
        button1=False,
        button2=False,
        vendor_field=0,
        touch=True,
        in_range=False,
        x=10,
        y=20,
        pressure=64,
        raw=b"\x00" * 6,
        t=1.5,
    )

    frame = server_module.sample_to_sse_frame(sample)

    text = frame.decode()
    lines = text.split("\n")
    assert lines[0].startswith("data: ")
    assert lines[1] == ""  # the blank line an SSE frame ends with
    payload = json.loads(lines[0][len("data: ") :])
    assert payload == {"x": 10, "y": 20, "pressure": 64, "touch": True, "t": 1.5}


def test_error_sse_frame_names_the_error_event(server_module: ModuleType) -> None:
    frame = server_module.error_sse_frame("pad disconnected")

    text = frame.decode()
    assert text.startswith("event: error\n")
    assert "pad disconnected" in text


def test_keepalive_frame_is_an_sse_comment(server_module: ModuleType) -> None:
    assert server_module.KEEPALIVE_FRAME.startswith(b":")


# ---- Broadcaster (no sockets) ----


def test_broadcaster_fanout(server_module: ModuleType) -> None:
    b = server_module.Broadcaster()
    q1 = b.subscribe()
    q2 = b.subscribe()

    b.publish(b"data: x\n\n")

    assert q1.get_nowait() == b"data: x\n\n"
    assert q2.get_nowait() == b"data: x\n\n"


def test_broadcaster_unsubscribe_stops_receiving(server_module: ModuleType) -> None:
    b = server_module.Broadcaster()
    q = b.subscribe()
    b.unsubscribe(q)

    b.publish(b"data: x\n\n")

    assert q.empty()
    assert b.subscriber_count() == 0


def test_broadcaster_drops_oldest_on_full(server_module: ModuleType) -> None:
    b = server_module.Broadcaster(maxsize=2)
    q = b.subscribe()

    b.publish(b"1")
    b.publish(b"2")
    b.publish(b"3")  # full at 2 - the oldest queued frame (b"1") is dropped

    assert q.get_nowait() == b"2"
    assert q.get_nowait() == b"3"
    assert q.empty()


def test_broadcaster_mark_disconnected_sets_state_and_publishes(
    server_module: ModuleType,
) -> None:
    b = server_module.Broadcaster()
    q = b.subscribe()

    b.mark_disconnected("pad unplugged")

    assert b.disconnected == "pad unplugged"
    assert b"pad unplugged" in q.get_nowait()


# ---- replay reader (no sockets) ----


def test_run_replay_reader_reads_a_json_capture(
    tmp_path: Path, server_module: ModuleType
) -> None:
    path = _make_capture(tmp_path, [(1, 2), (3, 4), (5, 6)])
    b = server_module.Broadcaster()
    q = b.subscribe()

    server_module.run_replay_reader(b, threading.Event(), path, loop=False, speed=0.0)

    frames = []
    while not q.empty():
        frames.append(q.get_nowait())
    assert len(frames) == 3
    payload = json.loads(frames[0].decode().split("\n")[0][len("data: ") :])
    assert payload["x"] == 1


def test_run_replay_reader_empty_file_publishes_nothing(
    tmp_path: Path, server_module: ModuleType
) -> None:
    path = _make_capture(tmp_path, [])
    b = server_module.Broadcaster()
    q = b.subscribe()

    server_module.run_replay_reader(b, threading.Event(), path, loop=False, speed=0.0)

    assert q.empty()


def test_run_replay_reader_loop_repeats_until_stopped(
    tmp_path: Path, server_module: ModuleType
) -> None:
    path = _make_capture(tmp_path, [(1, 2)])
    b = server_module.Broadcaster()
    q = b.subscribe()
    stop = threading.Event()

    stopper = threading.Timer(0.05, stop.set)
    stopper.start()
    server_module.run_replay_reader(b, stop, path, loop=True, speed=0.0)
    stopper.cancel()

    count = 0
    while not q.empty():
        q.get_nowait()
        count += 1
    assert count > 1  # proves it looped rather than replaying once


def test_run_replay_reader_honors_stop_set_before_starting(
    tmp_path: Path, server_module: ModuleType
) -> None:
    path = _make_capture(tmp_path, [(1, 2), (3, 4)])
    b = server_module.Broadcaster()
    stop = threading.Event()
    stop.set()

    server_module.run_replay_reader(
        b, stop, path, loop=True, speed=0.0
    )  # must return promptly


# ---- server class shape (no sockets) ----


def test_daemon_threads_is_true(server_module: ModuleType) -> None:
    """Load-bearing: without this, server_close() never returns while a
    single /events connection is still open - measured live before this
    was written (server_close() did not return within a 4s bound with
    daemon_threads left False and one open SSE stream)."""
    assert server_module.DemoServer.daemon_threads is True


# ---- exactly one real-socket test ----


def test_server_end_to_end(tmp_path: Path, server_module: ModuleType) -> None:
    """One pass over the real HTTP/SSE surface: index page, health
    endpoint, a bounded read of live frames, and that a disconnected
    client's queue is actually cleaned up - fed by a fast, looping replay
    so this needs no pad attached and can't hang waiting on one."""
    capture_path = _make_capture(tmp_path, [(1, 2), (3, 4), (5, 6)])

    broadcaster = server_module.Broadcaster()
    stop = threading.Event()
    reader = threading.Thread(
        target=server_module.run_replay_reader,
        args=(broadcaster, stop, capture_path),
        kwargs={"loop": True, "speed": 0.0},
        daemon=True,
    )
    reader.start()

    server = server_module._build_server("127.0.0.1", 0, broadcaster)
    server_thread = threading.Thread(target=server.serve_forever, daemon=True)
    server_thread.start()
    port = server.server_address[1]

    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/", timeout=5) as resp:
            assert resp.status == 200
            assert b"<canvas" in resp.read()

        with urllib.request.urlopen(
            f"http://127.0.0.1:{port}/healthz", timeout=5
        ) as resp:
            assert resp.status == 200
            assert "disconnected" in json.loads(resp.read())

        deadline = time.monotonic() + 5.0
        data_lines = 0
        events_resp = urllib.request.urlopen(
            f"http://127.0.0.1:{port}/events", timeout=5
        )
        try:
            while data_lines < 3 and time.monotonic() < deadline:
                line = events_resp.readline()
                if line.startswith(b"data: "):
                    payload = json.loads(line[len(b"data: ") :])
                    assert "x" in payload
                    assert "touch" in payload
                    data_lines += 1
        finally:
            events_resp.close()  # client disconnects - server should notice
        assert data_lines == 3, "did not receive enough SSE frames before the deadline"

        # The replay keeps publishing after the close above; the next
        # write(s) into that handler's queue should fail and the handler
        # should unsubscribe. Poll for it rather than sleeping a fixed
        # amount - the exact number of writes needed to notice a closed
        # socket is platform-dependent (measured 2 successful writes
        # before a failure on macOS).
        deadline = time.monotonic() + 5.0
        while broadcaster.subscriber_count() > 0 and time.monotonic() < deadline:
            time.sleep(0.05)
        assert broadcaster.subscriber_count() == 0
    finally:
        stop.set()
        server.shutdown_cleanly()
        server_thread.join(timeout=5.0)
        server.server_close()
        reader.join(timeout=5.0)
