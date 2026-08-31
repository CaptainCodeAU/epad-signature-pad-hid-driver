"""Serialize captured pen samples to interchange-friendly data formats,
and load them back.

These store the movement itself (position, pressure, and timing of every
reading), not just a picture - so a signature can be re-rendered later, fed
to another tool, or kept in a database that can't hold images.
"""

from __future__ import annotations

import json
import xml.etree.ElementTree as ET
from datetime import datetime
from pathlib import Path
from typing import cast

from epad_signature_pad_hid_driver.exceptions import InvalidFormatError
from epad_signature_pad_hid_driver.protocol import (
    PRODUCT_ID,
    VENDOR_ID,
    PenSample,
    encode_report,
)

JSON_FORMAT_VERSION = "epad-pen-samples-v1"
INKML_NAMESPACE = "http://www.w3.org/2003/InkML"

# InkML channel names this package reads/writes, and how to parse a token
# for each. X/Y/F/T are plain integers; B1/B2 are booleans, encoded per the
# InkML spec as the literal characters "T"/"F" - not 0/1.
_INT_CHANNELS = ("X", "Y", "F", "T")
_BOOL_CHANNELS = ("B1", "B2")
_DEFAULT_CHANNELS = ("X", "Y", "F", "T")  # assumed when a file has no traceFormat

_REQUIRED_JSON_SAMPLE_KEYS = (
    "t",
    "x",
    "y",
    "pressure",
    "touch",
    "in_range",
    "button1",
    "button2",
    "vendor_field",
)


def save_json(
    samples: list[PenSample],
    path: Path,
    captured_at: datetime,
    truncated: bool = False,
) -> None:
    """Save every reading as a simple, self-describing JSON document.

    truncated=True marks a session that was cut short by watch()'s `stop`
    switch before the pad went idle on its own - the samples up to that
    point are real and complete, but the signature itself may not be.
    """
    document = {
        "format": JSON_FORMAT_VERSION,
        "device": {"vendor_id": VENDOR_ID, "product_id": PRODUCT_ID},
        "captured_at": captured_at.isoformat(),
        "truncated": truncated,
        "sample_count": len(samples),
        "samples": [
            {
                "t": round(s.t, 4),
                "x": s.x,
                "y": s.y,
                "pressure": s.pressure,
                "touch": s.touch,
                "in_range": s.in_range,
                "button1": s.button1,
                "button2": s.button2,
                "vendor_field": s.vendor_field,
            }
            for s in samples
        ],
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(document, indent=2), encoding="utf-8")


def load_json(path: Path) -> list[PenSample]:
    """Load a .json file saved by save_json() back into PenSamples.

    Not an exact inverse of save_json(): `t` is only as precise as the 4
    decimal places save_json() rounds to, and `raw` is not stored in JSON
    at all - it is rebuilt with encode_report(), which cannot recover the
    two real HID padding bits (see encode_report's own docstring).

    Raises InvalidFormatError for anything malformed: not valid JSON, not
    a JSON object, an unrecognized/missing "format" value, or a sample
    missing a required field or holding a value the wire format can't
    represent. A missing *file* raises OSError (FileNotFoundError), not
    InvalidFormatError - that's a filesystem problem, not a content one.
    sample_count is not checked against the actual number of samples, so
    a hand-edited file still loads.
    """
    text = path.read_text(encoding="utf-8")
    try:
        document = json.loads(text)
    except json.JSONDecodeError as err:
        raise InvalidFormatError(f"{path}: not valid JSON: {err}") from err

    if not isinstance(document, dict):
        raise InvalidFormatError(f"{path}: JSON root must be an object")
    if document.get("format") != JSON_FORMAT_VERSION:
        raise InvalidFormatError(
            f'{path}: unrecognized or missing "format" '
            f'(expected "{JSON_FORMAT_VERSION}")'
        )
    raw_samples = document.get("samples")
    if not isinstance(raw_samples, list):
        raise InvalidFormatError(f'{path}: "samples" must be a list')

    return [_sample_from_json(path, i, entry) for i, entry in enumerate(raw_samples)]


def _sample_from_json(path: Path, index: int, entry: object) -> PenSample:
    if not isinstance(entry, dict):
        raise InvalidFormatError(f"{path}: samples[{index}] must be an object")
    missing = [k for k in _REQUIRED_JSON_SAMPLE_KEYS if k not in entry]
    if missing:
        raise InvalidFormatError(
            f"{path}: samples[{index}] missing field(s): {missing}"
        )

    for key in ("x", "y", "pressure", "vendor_field"):
        value = entry[key]
        if type(value) is not int:  # deliberately excludes bool (isinstance would not)
            raise InvalidFormatError(
                f"{path}: samples[{index}].{key} must be an integer, got {value!r}"
            )
    t = entry["t"]
    if not isinstance(t, (int, float)) or isinstance(t, bool):
        raise InvalidFormatError(
            f"{path}: samples[{index}].t must be a number, got {t!r}"
        )

    sample = PenSample(
        button1=bool(entry["button1"]),
        button2=bool(entry["button2"]),
        vendor_field=entry["vendor_field"],
        touch=bool(entry["touch"]),
        in_range=bool(entry["in_range"]),
        x=entry["x"],
        y=entry["y"],
        pressure=entry["pressure"],
        raw=b"",
        t=float(t),
    )
    try:
        sample.raw = encode_report(sample)
    except ValueError as err:
        raise InvalidFormatError(f"{path}: samples[{index}]: {err}") from err
    return sample


def _strokes(samples: list[PenSample]) -> list[list[PenSample]]:
    """Split samples into contiguous touch=True runs (one per pen-down stroke)."""
    strokes: list[list[PenSample]] = []
    current: list[PenSample] = []
    for sample in samples:
        if sample.touch:
            current.append(sample)
        elif current:
            strokes.append(current)
            current = []
    if current:
        strokes.append(current)
    return strokes


def _point_token(sample: PenSample, channel: str) -> str:
    if channel == "X":
        return str(sample.x)
    if channel == "Y":
        return str(sample.y)
    if channel == "F":
        return str(sample.pressure)
    if channel == "T":
        return str(round(sample.t * 1000))
    if channel == "B1":
        return "T" if sample.button1 else "F"
    if channel == "B2":
        return "T" if sample.button2 else "F"
    raise AssertionError(
        f"unreachable: unknown channel {channel!r}"
    )  # pragma: no cover


_WRITE_CHANNELS = ("X", "Y", "F", "T", "B1", "B2")


def save_inkml(
    samples: list[PenSample],
    path: Path,
    captured_at: datetime,
    truncated: bool = False,
) -> None:
    """Save every stroke as a W3C InkML document.

    Channels, in order: X, Y, F (pressure), T (time, ms), B1, B2 (buttons -
    encoded as the InkML spec's own boolean literals "T"/"F", not 0/1).
    touch/in_range/vendor_field have no channel: touch is implied by trace
    membership, and in_range/vendor_field are not part of this package's
    public, documented byte layout in the same way - see HARDWARE_NOTES.md.

    truncated=True adds a <annotation type="truncated">true</annotation> -
    omitted entirely when False, so a normally-completed session's InkML
    is unchanged from before this parameter existed.
    """
    ink = ET.Element("ink", xmlns=INKML_NAMESPACE)
    ET.SubElement(ink, "annotation", type="captured_at").text = captured_at.isoformat()
    ET.SubElement(
        ink,
        "annotation",
        type="device",
    ).text = f"ePadLink ePad (vid=0x{VENDOR_ID:04x}, pid=0x{PRODUCT_ID:04x})"
    if truncated:
        ET.SubElement(ink, "annotation", type="truncated").text = "true"

    trace_format = ET.SubElement(ink, "traceFormat")
    ET.SubElement(trace_format, "channel", name="X", type="integer")
    ET.SubElement(trace_format, "channel", name="Y", type="integer")
    ET.SubElement(trace_format, "channel", name="F", type="integer")
    ET.SubElement(trace_format, "channel", name="T", type="integer", units="ms")
    ET.SubElement(trace_format, "channel", name="B1", type="boolean")
    ET.SubElement(trace_format, "channel", name="B2", type="boolean")

    for stroke in _strokes(samples):
        points = ", ".join(
            " ".join(_point_token(s, ch) for ch in _WRITE_CHANNELS) for s in stroke
        )
        ET.SubElement(ink, "trace").text = points

    path.parent.mkdir(parents=True, exist_ok=True)
    ET.indent(ink)
    # encoding="unicode" (the previous value here) writes text through the
    # OS default encoding, which is cp1252 on a default Windows box -
    # explicit "utf-8" writes real UTF-8 bytes instead; verified this
    # produces byte-identical content on this platform and still suppresses
    # the XML declaration (xml_declaration=False).
    ET.ElementTree(ink).write(path, encoding="utf-8", xml_declaration=False)


def _local_name(tag: str) -> str:
    """Strip a `{namespace}` prefix, if any, from an ElementTree tag.

    Required because ET.Element("ink", xmlns=...) writes xmlns as a real
    default-namespace declaration, so re-parsing our own output namespaces
    every element tag (e.g. "trace" becomes "{http://.../InkML}trace") -
    verified live before this was written; a plain `findall("trace")`
    against our own saved file finds zero elements. Attributes are never
    namespaced this way, so channel/type attributes are read bare.
    """
    return tag.rpartition("}")[2]


def _read_channels(root: ET.Element) -> list[str]:
    trace_format = next(
        (el for el in root.iter() if _local_name(el.tag) == "traceFormat"), None
    )
    if trace_format is None:
        return list(_DEFAULT_CHANNELS)

    channels = [
        el.get("name", "") for el in trace_format if _local_name(el.tag) == "channel"
    ]
    unknown = [c for c in channels if c not in (*_INT_CHANNELS, *_BOOL_CHANNELS)]
    if unknown:
        raise InvalidFormatError(f"unknown InkML channel(s): {unknown}")
    if not set(_DEFAULT_CHANNELS) <= set(channels):
        raise InvalidFormatError(
            f"traceFormat is missing required channel(s): "
            f"{sorted(set(_DEFAULT_CHANNELS) - set(channels))}"
        )
    return channels


def _parse_point(
    path: Path, channels: list[str], token_group: str
) -> dict[str, object]:
    tokens = token_group.split()
    if len(tokens) != len(channels):
        raise InvalidFormatError(
            f"{path}: trace point has {len(tokens)} value(s), "
            f"expected {len(channels)} for channels {channels}"
        )
    values: dict[str, object] = {}
    for channel, token in zip(channels, tokens, strict=True):
        if channel in _BOOL_CHANNELS:
            if token not in ("T", "F"):
                raise InvalidFormatError(
                    f'{path}: channel {channel} must be "T" or "F", got {token!r}'
                )
            values[channel] = token == "T"
        else:
            try:
                values[channel] = int(token)
            except ValueError as err:
                raise InvalidFormatError(
                    f"{path}: channel {channel} value {token!r} is not an integer"
                ) from err
    return values


def _parse_trace(path: Path, channels: list[str], trace_text: str) -> list[PenSample]:
    samples: list[PenSample] = []
    for group in trace_text.split(","):
        group = group.strip()
        if not group:
            continue  # tolerates a trailing comma or extra blank lines
        values = _parse_point(path, channels, group)
        x = cast(int, values["X"])
        y = cast(int, values["Y"])
        pressure = cast(int, values["F"])
        t_ms = cast(int, values["T"])
        button1 = bool(values.get("B1", False))
        button2 = bool(values.get("B2", False))

        sample = PenSample(
            button1=button1,
            button2=button2,
            vendor_field=0,
            touch=True,
            in_range=False,
            x=x,
            y=y,
            pressure=pressure,
            raw=b"",
            t=t_ms / 1000.0,
        )
        try:
            sample.raw = encode_report(sample)
        except ValueError as err:
            raise InvalidFormatError(f"{path}: {err}") from err
        samples.append(sample)
    return samples


def load_inkml(path: Path) -> list[PenSample]:
    """Load a .inkml file saved by save_inkml() (or a compatible one) back
    into PenSamples.

    InkML only ever stores touch=True points, grouped into traces - so
    every loaded sample has touch=True, and a single touch=False "break"
    sample is inserted between (not before or after) each pair of traces,
    so render_signature() keeps strokes visually separate the same way it
    would for a live capture.

    InkML carries no in_range, no vendor_field, and no raw HID bytes:
    loaded samples set in_range=False, vendor_field=0, and a raw rebuilt
    by encode_report() - these are placeholders, not measurements, and
    must never be read as anything the pad actually reported. button1/
    button2 are real recorded values when the file has B1/B2 channels
    (this package always writes them); a legacy file without them loads
    with both defaulting to False.

    Raises InvalidFormatError for anything malformed: not valid XML, a
    root element that isn't (an, possibly namespaced) <ink>, an unknown
    channel name, or a point whose value count or types don't match the
    channel list. A file with zero traces is valid and loads as []. A
    missing *file* raises OSError (FileNotFoundError), not
    InvalidFormatError.
    """
    try:
        tree = ET.parse(path)
    except ET.ParseError as err:
        raise InvalidFormatError(f"{path}: not valid XML: {err}") from err

    root = tree.getroot()
    if _local_name(root.tag) != "ink":
        raise InvalidFormatError(
            f"{path}: root element is not <ink> (got {root.tag!r})"
        )

    channels = _read_channels(root)
    traces = [el for el in root.iter() if _local_name(el.tag) == "trace"]

    trace_samples = [_parse_trace(path, channels, trace.text or "") for trace in traces]
    trace_samples = [group for group in trace_samples if group]  # drop empty traces

    combined: list[PenSample] = []
    for i, group in enumerate(trace_samples):
        if i > 0:
            last = combined[-1]
            combined.append(
                PenSample(
                    button1=False,
                    button2=False,
                    vendor_field=0,
                    touch=False,
                    in_range=False,
                    x=last.x,
                    y=last.y,
                    pressure=0,
                    raw=b"\x00" * 6,
                    t=last.t,
                )
            )
        combined.extend(group)
    return combined
