"""Tests for formats.py: the JSON/InkML save+load round trip.

The InkML loader is the trickiest part here - a saved .inkml file re-parses
with every element namespaced (proven live before this was written: a
naive `findall("trace")` finds zero elements on our own output), so the
loader must match by local element name, not by literal tag string.
"""

import json
from datetime import datetime

import pytest
from PIL import Image

from epad_signature_pad_hid_driver.exceptions import InvalidFormatError
from epad_signature_pad_hid_driver.formats import (
    load_inkml,
    load_json,
    save_inkml,
    save_json,
)
from epad_signature_pad_hid_driver.protocol import encode_report
from epad_signature_pad_hid_driver.render import render_signature
from tests.helpers import stroke_samples, touched_samples

CAPTURED_AT = datetime(2026, 8, 31, 22, 45, 12)


# ---- save_json / save_inkml (moved from test_main.py) ----


def test_save_json(tmp_path) -> None:
    samples = touched_samples([(1, 2), (3, 4)])
    out_path = tmp_path / "signature.json"

    save_json(samples, out_path, captured_at=CAPTURED_AT)

    document = json.loads(out_path.read_text())
    assert document["sample_count"] == 2
    assert document["captured_at"] == "2026-08-31T22:45:12"
    assert document["truncated"] is False
    assert document["samples"][1]["x"] == 3
    assert document["samples"][1]["y"] == 4
    assert document["samples"][1]["t"] == pytest.approx(0.02)


def test_save_inkml(tmp_path) -> None:
    samples = touched_samples([(1, 2), (3, 4)])
    out_path = tmp_path / "signature.inkml"

    save_inkml(samples, out_path, captured_at=CAPTURED_AT)

    content = out_path.read_text()
    assert "<trace>1 2 64 0 F F, 3 4 64 20 F F</trace>" in content
    assert 'xmlns="http://www.w3.org/2003/InkML"' in content


def test_save_inkml_separates_strokes(tmp_path) -> None:
    samples = stroke_samples([[(1, 2), (3, 4)], [(5, 6), (7, 8)]])
    out_path = tmp_path / "signature.inkml"

    save_inkml(samples, out_path, captured_at=CAPTURED_AT)

    content = out_path.read_text()
    assert content.count("<trace>") == 2
    assert "<trace>1 2 64 0 F F, 3 4 64 20 F F</trace>" in content
    assert "<trace>5 6 64 60 F F, 7 8 64 80 F F</trace>" in content


def test_save_inkml_writes_button_channels(tmp_path) -> None:
    out_path = tmp_path / "signature.inkml"
    save_inkml(touched_samples([(1, 2)]), out_path, captured_at=CAPTURED_AT)

    content = out_path.read_text()
    assert '<channel name="B1" type="boolean" />' in content
    assert '<channel name="B2" type="boolean" />' in content


def test_save_inkml_encodes_buttons_as_T_and_F(tmp_path) -> None:
    from epad_signature_pad_hid_driver.protocol import PenSample

    pressed = PenSample(
        button1=True,
        button2=False,
        vendor_field=0,
        touch=True,
        in_range=False,
        x=1,
        y=2,
        pressure=64,
        raw=b"\x00" * 6,
        t=0.0,
    )
    out_path = tmp_path / "signature.inkml"
    save_inkml([pressed], out_path, captured_at=CAPTURED_AT)

    content = out_path.read_text()
    assert "<trace>1 2 64 0 T F</trace>" in content


# ---- load_json ----


def test_load_json_round_trips_all_fields(tmp_path) -> None:
    samples = touched_samples([(10, 20), (30, 40)])
    path = tmp_path / "s.json"
    save_json(samples, path, captured_at=CAPTURED_AT)

    loaded = load_json(path)

    assert len(loaded) == 2
    for original, restored in zip(samples, loaded, strict=True):
        assert restored.x == original.x
        assert restored.y == original.y
        assert restored.pressure == original.pressure
        assert restored.touch == original.touch
        assert restored.in_range == original.in_range
        assert restored.button1 == original.button1
        assert restored.button2 == original.button2
        assert restored.vendor_field == original.vendor_field
        assert restored.t == pytest.approx(original.t)


def test_load_json_rebuilds_raw_bytes_not_the_captured_ones(tmp_path) -> None:
    """save_json stores no `raw` field at all - load_json must rebuild it
    with encode_report(), which is not always byte-identical to whatever
    the pad originally sent (the two HID padding bits are lost)."""
    samples = touched_samples([(10, 20)])
    path = tmp_path / "s.json"
    save_json(samples, path, captured_at=CAPTURED_AT)

    loaded = load_json(path)

    assert loaded[0].raw == encode_report(loaded[0])


def test_load_json_empty_sample_list_returns_empty_list(tmp_path) -> None:
    path = tmp_path / "s.json"
    save_json([], path, captured_at=CAPTURED_AT)

    assert load_json(path) == []


def test_load_json_rejects_non_json(tmp_path) -> None:
    path = tmp_path / "s.json"
    path.write_text("not json at all {{{")

    with pytest.raises(InvalidFormatError):
        load_json(path)


def test_load_json_rejects_empty_file(tmp_path) -> None:
    path = tmp_path / "s.json"
    path.write_text("")

    with pytest.raises(InvalidFormatError):
        load_json(path)


def test_load_json_rejects_json_that_is_not_an_object(tmp_path) -> None:
    path = tmp_path / "s.json"
    path.write_text("[]")

    with pytest.raises(InvalidFormatError):
        load_json(path)


def test_load_json_rejects_unknown_format_version(tmp_path) -> None:
    path = tmp_path / "s.json"
    path.write_text(json.dumps({"format": "something-else", "samples": []}))

    with pytest.raises(InvalidFormatError, match="format"):
        load_json(path)


def test_load_json_rejects_missing_field(tmp_path) -> None:
    path = tmp_path / "s.json"
    document = {
        "format": "epad-pen-samples-v1",
        "samples": [{"t": 0, "x": 1, "y": 2}],  # missing pressure/touch/etc.
    }
    path.write_text(json.dumps(document))

    with pytest.raises(InvalidFormatError):
        load_json(path)


def test_load_json_rejects_float_coordinate(tmp_path) -> None:
    path = tmp_path / "s.json"
    document = {
        "format": "epad-pen-samples-v1",
        "samples": [
            {
                "t": 0,
                "x": 3.5,
                "y": 2,
                "pressure": 1,
                "touch": True,
                "in_range": False,
                "button1": False,
                "button2": False,
                "vendor_field": 0,
            }
        ],
    }
    path.write_text(json.dumps(document))

    with pytest.raises(InvalidFormatError):
        load_json(path)


def test_load_json_ignores_wrong_sample_count(tmp_path) -> None:
    """A hand-edited file should still load even if sample_count lies."""
    path = tmp_path / "s.json"
    document = {
        "format": "epad-pen-samples-v1",
        "sample_count": 99,
        "samples": [
            {
                "t": 0,
                "x": 1,
                "y": 2,
                "pressure": 1,
                "touch": True,
                "in_range": False,
                "button1": False,
                "button2": False,
                "vendor_field": 0,
            }
        ],
    }
    path.write_text(json.dumps(document))

    assert len(load_json(path)) == 1


def test_load_json_rejects_samples_that_is_not_a_list(tmp_path) -> None:
    path = tmp_path / "s.json"
    path.write_text(json.dumps({"format": "epad-pen-samples-v1", "samples": "nope"}))

    with pytest.raises(InvalidFormatError):
        load_json(path)


def test_load_json_rejects_sample_entry_that_is_not_an_object(tmp_path) -> None:
    path = tmp_path / "s.json"
    path.write_text(json.dumps({"format": "epad-pen-samples-v1", "samples": [1, 2]}))

    with pytest.raises(InvalidFormatError):
        load_json(path)


def test_load_json_rejects_non_numeric_t(tmp_path) -> None:
    path = tmp_path / "s.json"
    document = {
        "format": "epad-pen-samples-v1",
        "samples": [
            {
                "t": "soon",
                "x": 1,
                "y": 2,
                "pressure": 1,
                "touch": True,
                "in_range": False,
                "button1": False,
                "button2": False,
                "vendor_field": 0,
            }
        ],
    }
    path.write_text(json.dumps(document))

    with pytest.raises(InvalidFormatError):
        load_json(path)


def test_load_json_rejects_out_of_range_coordinate(tmp_path) -> None:
    path = tmp_path / "s.json"
    document = {
        "format": "epad-pen-samples-v1",
        "samples": [
            {
                "t": 0,
                "x": 999999,  # a real int, but outside the wire format's range
                "y": 2,
                "pressure": 1,
                "touch": True,
                "in_range": False,
                "button1": False,
                "button2": False,
                "vendor_field": 0,
            }
        ],
    }
    path.write_text(json.dumps(document))

    with pytest.raises(InvalidFormatError):
        load_json(path)


def test_load_json_missing_file_raises_os_error(tmp_path) -> None:
    """A missing file is a filesystem problem, not a malformed-content
    problem - it must raise OSError (FileNotFoundError), not InvalidFormatError."""
    with pytest.raises(OSError):
        load_json(tmp_path / "does-not-exist.json")


def test_save_inkml_truncated_adds_annotation(tmp_path) -> None:
    out_path = tmp_path / "s.inkml"
    save_inkml(
        touched_samples([(1, 2)]), out_path, captured_at=CAPTURED_AT, truncated=True
    )

    content = out_path.read_text()
    assert '<annotation type="truncated">true</annotation>' in content


def test_save_inkml_not_truncated_omits_annotation(tmp_path) -> None:
    out_path = tmp_path / "s.inkml"
    save_inkml(touched_samples([(1, 2)]), out_path, captured_at=CAPTURED_AT)

    assert "truncated" not in out_path.read_text()


# ---- load_inkml ----


def test_load_inkml_round_trips_x_y_pressure_time(tmp_path) -> None:
    samples = touched_samples([(10, 20), (30, 40)])
    path = tmp_path / "s.inkml"
    save_inkml(samples, path, captured_at=CAPTURED_AT)

    loaded = load_inkml(path)

    assert [(s.x, s.y, s.pressure) for s in loaded] == [
        (10, 20, 64),
        (30, 40, 64),
    ]
    assert loaded[1].t == pytest.approx(0.02)


def test_load_inkml_round_trips_buttons(tmp_path) -> None:
    from epad_signature_pad_hid_driver.protocol import PenSample

    pressed = PenSample(
        button1=True,
        button2=True,
        vendor_field=0,
        touch=True,
        in_range=False,
        x=1,
        y=2,
        pressure=64,
        raw=b"\x00" * 6,
        t=0.0,
    )
    path = tmp_path / "s.inkml"
    save_inkml([pressed], path, captured_at=CAPTURED_AT)

    loaded = load_inkml(path)

    assert loaded[0].button1 is True
    assert loaded[0].button2 is True


def test_load_inkml_marks_every_point_as_touched(tmp_path) -> None:
    samples = touched_samples([(1, 2), (3, 4)])
    path = tmp_path / "s.inkml"
    save_inkml(samples, path, captured_at=CAPTURED_AT)

    loaded = load_inkml(path)

    assert all(s.touch for s in loaded)


def test_load_inkml_inserts_break_between_traces_only(tmp_path) -> None:
    samples = stroke_samples([[(1, 2), (3, 4)], [(5, 6), (7, 8)]])
    path = tmp_path / "s.inkml"
    save_inkml(samples, path, captured_at=CAPTURED_AT)

    loaded = load_inkml(path)

    breaks = [i for i, s in enumerate(loaded) if not s.touch]
    assert breaks == [2]  # exactly one break, not first or last sample
    assert len(loaded) == 5  # 2 + break + 2


def test_load_inkml_single_point_trace_no_break(tmp_path) -> None:
    samples = touched_samples([(1, 2)])
    path = tmp_path / "s.inkml"
    save_inkml(samples, path, captured_at=CAPTURED_AT)

    loaded = load_inkml(path)

    assert len(loaded) == 1
    assert loaded[0].touch is True


def test_load_inkml_reads_legacy_four_channel_file(tmp_path) -> None:
    """A file saved before B1/B2 existed has no button channels at all -
    it must still load, with button1/button2 defaulting to False."""
    path = tmp_path / "legacy.inkml"
    path.write_text(
        '<ink xmlns="http://www.w3.org/2003/InkML">'
        "<traceFormat>"
        '<channel name="X" type="integer"/>'
        '<channel name="Y" type="integer"/>'
        '<channel name="F" type="integer"/>'
        '<channel name="T" type="integer" units="ms"/>'
        "</traceFormat>"
        "<trace>1 2 64 0, 3 4 64 20</trace>"
        "</ink>",
        encoding="utf-8",
    )

    loaded = load_inkml(path)

    assert [(s.x, s.y) for s in loaded] == [(1, 2), (3, 4)]
    assert all(s.button1 is False and s.button2 is False for s in loaded)


def test_load_inkml_without_trace_format_assumes_x_y_f_t(tmp_path) -> None:
    path = tmp_path / "no-format.inkml"
    path.write_text(
        '<ink xmlns="http://www.w3.org/2003/InkML"><trace>5 6 10 100</trace></ink>',
        encoding="utf-8",
    )

    loaded = load_inkml(path)

    assert len(loaded) == 1
    assert (loaded[0].x, loaded[0].y, loaded[0].pressure) == (5, 6, 10)
    assert loaded[0].t == pytest.approx(0.1)


def test_load_inkml_no_traces_returns_empty_list(tmp_path) -> None:
    path = tmp_path / "empty.inkml"
    path.write_text(
        '<ink xmlns="http://www.w3.org/2003/InkML"></ink>', encoding="utf-8"
    )

    assert load_inkml(path) == []


def test_load_inkml_rejects_empty_file(tmp_path) -> None:
    path = tmp_path / "s.inkml"
    path.write_text("", encoding="utf-8")

    with pytest.raises(InvalidFormatError):
        load_inkml(path)


def test_load_inkml_rejects_malformed_xml(tmp_path) -> None:
    path = tmp_path / "s.inkml"
    path.write_text("<ink><trace>not closed", encoding="utf-8")

    with pytest.raises(InvalidFormatError):
        load_inkml(path)


def test_load_inkml_rejects_wrong_root_element(tmp_path) -> None:
    path = tmp_path / "s.inkml"
    path.write_text("<notink></notink>", encoding="utf-8")

    with pytest.raises(InvalidFormatError, match="root"):
        load_inkml(path)


def test_load_inkml_rejects_point_with_wrong_value_count(tmp_path) -> None:
    path = tmp_path / "s.inkml"
    path.write_text(
        '<ink xmlns="http://www.w3.org/2003/InkML"><trace>1 2 3</trace></ink>',
        encoding="utf-8",
    )  # only 3 values, default channel set expects 4 (X Y F T)

    with pytest.raises(InvalidFormatError):
        load_inkml(path)


def test_load_inkml_rejects_non_numeric_value(tmp_path) -> None:
    path = tmp_path / "s.inkml"
    path.write_text(
        '<ink xmlns="http://www.w3.org/2003/InkML"><trace>x 2 3 4</trace></ink>',
        encoding="utf-8",
    )

    with pytest.raises(InvalidFormatError):
        load_inkml(path)


def test_load_inkml_handles_namespaced_and_bare_documents(tmp_path) -> None:
    bare = tmp_path / "bare.inkml"
    bare.write_text("<ink><trace>1 2 3 4</trace></ink>", encoding="utf-8")

    loaded = load_inkml(bare)

    assert len(loaded) == 1
    assert (loaded[0].x, loaded[0].y) == (1, 2)


def test_load_inkml_handles_empty_trace_element(tmp_path) -> None:
    path = tmp_path / "s.inkml"
    path.write_text(
        '<ink xmlns="http://www.w3.org/2003/InkML">'
        "<trace></trace>"
        "<trace>1 2 3 4</trace>"
        "</ink>",
        encoding="utf-8",
    )

    loaded = load_inkml(path)

    assert len(loaded) == 1  # empty trace contributes nothing, no crash
    assert loaded[0].x == 1


def test_load_inkml_tolerates_whitespace_and_trailing_comma(tmp_path) -> None:
    path = tmp_path / "s.inkml"
    path.write_text(
        '<ink xmlns="http://www.w3.org/2003/InkML">'
        "<trace>\n    1 2 3 4,\n    5 6 7 8,\n  </trace>"
        "</ink>",
        encoding="utf-8",
    )

    loaded = load_inkml(path)

    assert [(s.x, s.y) for s in loaded] == [(1, 2), (5, 6)]


def test_load_inkml_placeholder_fields_are_pinned(tmp_path) -> None:
    """InkML carries no in_range or vendor_field - loaded samples must set
    them to documented placeholders, never invent a value for them."""
    samples = touched_samples([(1, 2)])
    path = tmp_path / "s.inkml"
    save_inkml(samples, path, captured_at=CAPTURED_AT)

    loaded = load_inkml(path)

    assert loaded[0].in_range is False
    assert loaded[0].vendor_field == 0


def test_load_inkml_rejects_unknown_channel(tmp_path) -> None:
    path = tmp_path / "s.inkml"
    path.write_text(
        '<ink xmlns="http://www.w3.org/2003/InkML">'
        "<traceFormat>"
        '<channel name="X" type="integer"/>'
        '<channel name="Y" type="integer"/>'
        '<channel name="F" type="integer"/>'
        '<channel name="T" type="integer"/>'
        '<channel name="Z" type="integer"/>'
        "</traceFormat>"
        "<trace>1 2 3 4 5</trace>"
        "</ink>",
        encoding="utf-8",
    )

    with pytest.raises(InvalidFormatError, match="unknown"):
        load_inkml(path)


def test_load_inkml_rejects_traceformat_missing_required_channel(tmp_path) -> None:
    path = tmp_path / "s.inkml"
    path.write_text(
        '<ink xmlns="http://www.w3.org/2003/InkML">'
        "<traceFormat>"
        '<channel name="X" type="integer"/>'
        '<channel name="Y" type="integer"/>'
        '<channel name="F" type="integer"/>'
        "</traceFormat>"  # no T channel
        "<trace>1 2 3</trace>"
        "</ink>",
        encoding="utf-8",
    )

    with pytest.raises(InvalidFormatError, match="missing"):
        load_inkml(path)


def test_load_inkml_rejects_invalid_boolean_token(tmp_path) -> None:
    path = tmp_path / "s.inkml"
    path.write_text(
        '<ink xmlns="http://www.w3.org/2003/InkML">'
        "<traceFormat>"
        '<channel name="X" type="integer"/>'
        '<channel name="Y" type="integer"/>'
        '<channel name="F" type="integer"/>'
        '<channel name="T" type="integer"/>'
        '<channel name="B1" type="boolean"/>'
        "</traceFormat>"
        "<trace>1 2 3 4 yes</trace>"  # "yes" is not "T" or "F"
        "</ink>",
        encoding="utf-8",
    )

    with pytest.raises(InvalidFormatError):
        load_inkml(path)


def test_load_inkml_rejects_out_of_range_coordinate(tmp_path) -> None:
    path = tmp_path / "s.inkml"
    path.write_text(
        '<ink xmlns="http://www.w3.org/2003/InkML">'
        "<trace>999999 2 3 4</trace>"  # a real int, but out of wire range
        "</ink>",
        encoding="utf-8",
    )

    with pytest.raises(InvalidFormatError):
        load_inkml(path)


def test_load_inkml_missing_file_raises_os_error(tmp_path) -> None:
    with pytest.raises(OSError):
        load_inkml(tmp_path / "does-not-exist.inkml")


# ---- round trip renders identical pixels ----


def test_json_file_round_trip_renders_identical_pixels(tmp_path) -> None:
    samples = touched_samples([(10, 10), (50, 60), (90, 20)])
    json_path = tmp_path / "s.json"
    save_json(samples, json_path, captured_at=CAPTURED_AT)

    original_png = tmp_path / "original.png"
    reloaded_png = tmp_path / "reloaded.png"
    render_signature(samples, original_png)
    render_signature(load_json(json_path), reloaded_png)

    with Image.open(original_png) as a, Image.open(reloaded_png) as b:
        assert a.size == b.size
        assert a.tobytes() == b.tobytes()


def test_inkml_file_round_trip_renders_identical_pixels(tmp_path) -> None:
    samples = touched_samples([(10, 10), (50, 60), (90, 20)])
    inkml_path = tmp_path / "s.inkml"
    save_inkml(samples, inkml_path, captured_at=CAPTURED_AT)

    original_png = tmp_path / "original.png"
    reloaded_png = tmp_path / "reloaded.png"
    render_signature(samples, original_png)
    render_signature(load_inkml(inkml_path), reloaded_png)

    with Image.open(original_png) as a, Image.open(reloaded_png) as b:
        assert a.size == b.size
        assert a.tobytes() == b.tobytes()
