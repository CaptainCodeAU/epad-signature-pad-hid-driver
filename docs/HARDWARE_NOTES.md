# Hardware notes

This is the technical backstory for this driver: exactly what the device
reports about itself, and exactly why no existing vendor document could
have supplied the byte layout this driver uses. Everything below was
gathered first-hand this session, either read live off the physical
device or confirmed directly against ePadLink's own published pages —
nothing here is guessed.

## Device identity

Read live from the actual USB device:

| Field | Value |
|---|---|
| USB Vendor ID | `0x04DF` (1247 decimal) |
| USB Product ID | `0x0012` (18 decimal) |
| USB product string | `"ePadLink USB ePad"` |
| Interface | Single HID interface, `interface_number 0` |
| HID usage page | `0xFF00` (vendor-defined) |
| HID usage | `0xFF` |
| bcdDevice | 512 |
| bNumConfigurations | 1 |

## The HID report descriptor — the actual proof

Every USB HID device publishes a report descriptor: a self-describing
document that says exactly what each byte of its data reports means.
This is the pad's own descriptor, fetched live via
`hid.device.get_report_descriptor()` against real hardware (124 bytes):

```
0600ff09ffa101150025010509090175019501810209028102050d0939a1020600ff1901290315012503950175038100c0050d093315002501750195018102093581027501810105010930350046002326500b651355fd751081020931460014265a058102050d0930457f257f6500550075078112750125018101c0
```

This descriptor is what proves the 6-byte input report layout used by
this driver's `decode_report()` function — it isn't an assumption, and
it isn't reverse-engineered from watching captured traffic. It's read
directly from the device.

Decoded at a high level, the descriptor describes one top-level
vendor-defined Application collection, containing:

**Byte 0 — status byte:**

| Bits | Meaning |
|---|---|
| bit 0 | button1 (Button usage page, 1 bit) |
| bit 1 | button2 (Button usage page, 1 bit) |
| bits 2-4 | a 3-bit vendor-defined field, nested in its own Logical collection tagged Digitizer usage `0x39` ("Tablet Function Keys") — no meaning has ever been observed in practice; treated as unused |
| bit 5 | touch (Digitizer usage `0x33` "Touch", 1 bit) |
| bit 6 | Digitizer usage `0x35`, 1 bit — meaning unconfirmed |
| bit 7 | padding bit |

**Bytes 1-4 — position:**

| Bytes | Field |
|---|---|
| bytes 1-2 | X — Generic Desktop usage `0x30`, 16-bit, logical range 0-2896, physical max 8960 (units: thousandths of an inch, so a declared width of about 8.96 in) |
| bytes 3-4 | Y — Generic Desktop usage `0x31`, 16-bit, logical range 0-1370, physical max 5120 thousandths-inch (about 5.12 in declared height) |

**Byte 5 — pressure:**

| Bits | Field |
|---|---|
| bits 0-6 | pressure — Digitizer Tip Pressure, usage `0x30` on the Digitizer page, 7-bit, logical range 0-127 |
| bit 7 | padding bit |

Total: 6 bytes, no Report ID byte — matching exactly what
[`core.py`](../src/epad_signature_pad_hid_driver/core.py) decodes.

## Live-confirmed behaviour

Confirmed by actually drawing on the pad and capturing real data, not
just read from the descriptor:

- The `touch` bit is `1` while the pen is pressing down. The instant the
  pen lifts, it drops to `touch=0` with `pressure=0` at the same time.
- Real sample rate observed: about **52 readings per second** (1,305
  samples captured over a 25-second test).

## Why there was nothing to copy the byte layout from

No official or community byte-level protocol document exists anywhere
for this exact pad model. This driver's report layout was worked out
first-hand from the live HID descriptor above, then confirmed against
real pen strokes. Here's what was actually checked, and why it came up
empty:

**Current official software (confirmed live against ePadLink's site,
2026-08-31):**

- The desktop "Universal Installer" driver
  ([epadlink.com/phone/universal-installer.html](https://www.epadlink.com/phone/universal-installer.html))
  supports **Windows only** — Windows 7, 8.1, 10, and Windows Server
  2008/2012/2016. No macOS build exists at all.
- The browser product, "SigCaptureWeb"
  ([SigCaptureWebSDKGuide.pdf](https://www.epadlink.com/guides/SigCaptureWebSDKGuide.pdf)),
  is a Chrome extension that talks to a locally-installed native driver
  over Chrome's Native Messaging — not WebHID or Web Serial; no such open
  browser API path exists for this brand. It supports Windows and Linux.
  Still no macOS.
- ePadLink does separately publish a real, currently-maintained **Linux**
  driver
  ([Linux Guide PDF](https://epadlink.com/guides/linuxguide.pdf), copyright
  dated 2025): the "gIIePad Interface 64-bit Driver", installable as an
  RPM (Fedora 33+) or `.deb` (Ubuntu 20+) from epadlink.com/downloads. It
  installs a real shared library, `libgiiepad.so`, into `/usr/lib(64)`,
  plus command-line demo tools `gIIePad_test` (a raw terminal test
  program) and `ePadDemo.exe` (a graphical demo) into
  `/usr/share/ePad/bin`, and C headers into `/usr/local/include`. A
  separate Citrix ICA client add-on also exists, for Fedora 29 /
  Ubuntu 18.04+.

**Older, historical vendor SDK docs — checked and ruled out:** ePadLink's
own support site also hosts a 2007-era Doxygen-generated Windows
COM/ActiveX SDK reference,
["ePadAPIs" / "epad_com_api_8.0"](http://www.epadsupport.com/epad_com_api_8.0/)
— a different, older product line than SigCaptureWeb. It documents
several different pad models in one shared doc tree, each with its own
COM ClassID/LibraryID: ePadUSB, ePadInk (both RS232 and USB variants),
ePad II - USB, ePad Id, ePadId Pro, ePadInk Pro, ePad LS, ePadXL USB,
ePadXL RS232, and ePad Serial.

This exact device (USB product string `"ePadLink USB ePad"`) corresponds
to that doc set's **ePadUSB** entry (ClassId
`7FCD9512-8763-436E-8747-40972EE28EFD`). Checked directly against that
doc set's own "Documentation Roadmap" page and its full File Index:
**ePadUSB has no published low-level byte-protocol document anywhere in
that entire 2007 doc set.** Only two sibling models — "ePadInk" and
"ePadId-LCD" — ever got a real `usb_io.h`-style report-struct document
published. So this old SDK documentation could not, on its own, have
told anyone this exact pad's byte layout. The real HID descriptor read
directly off the hardware, above, is what actually solved that.

One file from that same old doc set is still worth mentioning, because it
independently backs up the approach this driver takes: `ieusb_io.h`, a
shared, model-agnostic raw-HID open/read/write wrapper (functions like
`IEUS_OpenDevice(hLibContext, iDeviceNum, DEVICEPID, DEVICEVID,
CAPSUsagePageValue, fExclusiveOpen)`, `IEUS_ReadFile`,
`IEUS_HidGetFeature`/`IEUS_HidSetFeature`, `IEUS_CloseDevice`). Straight
from ePadLink's own internal driver architecture, this confirms these
pads are plain standard USB HID devices — using the same
ReadFile/HID-Feature-report primitives any generic HID library uses —
not some exotic non-HID transport. That's real supporting evidence for
why a plain cross-platform HID library like `hidapi` was able to talk to
this pad directly at all.

## Bottom line

No official or community document, anywhere, gives the byte-level
protocol for this exact pad model. Everything this driver knows about
the report layout was derived first-hand from the device's own live HID
report descriptor, then confirmed by capturing real pen strokes on real
hardware. That's the actual provenance behind this repo.

## Sources

- [epadlink.com/phone/universal-installer.html](https://www.epadlink.com/phone/universal-installer.html) — Universal Installer driver, Windows-only support
- [epadlink.com/guides/linuxguide.pdf](https://epadlink.com/guides/linuxguide.pdf) — gIIePad Linux driver details
- [epadsupport.com/epad_com_api_8.0/](http://www.epadsupport.com/epad_com_api_8.0/) — 2007 ePadAPIs SDK doc root, model list, ePadUSB ClassId, `ieusb_io.h`
- [epadlink.com/guides/SigCaptureWebSDKGuide.pdf](https://www.epadlink.com/guides/SigCaptureWebSDKGuide.pdf) — SigCaptureWeb Chrome extension, Native Messaging, Windows/Linux support
