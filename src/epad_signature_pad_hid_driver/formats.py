"""Serialize captured pen samples to interchange-friendly data formats.

These store the movement itself (position, pressure, and timing of every
reading), not just a picture - so a signature can be re-rendered later, fed
to another tool, or kept in a database that can't hold images.
"""

from __future__ import annotations

import json
import xml.etree.ElementTree as ET
from datetime import datetime
from pathlib import Path

from epad_signature_pad_hid_driver.protocol import PRODUCT_ID, VENDOR_ID, PenSample

JSON_FORMAT_VERSION = "epad-pen-samples-v1"
INKML_NAMESPACE = "http://www.w3.org/2003/InkML"


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


def save_inkml(
    samples: list[PenSample],
    path: Path,
    captured_at: datetime,
    truncated: bool = False,
) -> None:
    """Save every stroke as a W3C InkML document (x, y, pressure, time-ms channels).

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

    for stroke in _strokes(samples):
        points = ", ".join(
            f"{s.x} {s.y} {s.pressure} {round(s.t * 1000)}" for s in stroke
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
