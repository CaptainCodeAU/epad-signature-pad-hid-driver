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

These are the descriptor's own *declared* numbers. The pen's real reachable
values are noticeably smaller than the declared logical range — see
["The declared logical range is not the same as the reachable range"](#the-declared-logical-range-is-not-the-same-as-the-reachable-range)
below.

**Byte 5 — pressure:**

| Bits | Field |
|---|---|
| bits 0-6 | pressure — Digitizer Tip Pressure, usage `0x30` on the Digitizer page, 7-bit, logical range 0-127 |
| bit 7 | padding bit |

Total: 6 bytes, no Report ID byte — matching exactly what
[`protocol.py`](../src/epad_signature_pad_hid_driver/protocol.py) decodes.

## Live-confirmed behaviour

Confirmed by actually drawing on the pad and capturing real data, not
just read from the descriptor:

- The `touch` bit is `1` while the pen is pressing down. The instant the
  pen lifts, it drops to `touch=0` with `pressure=0` at the same time.
- Real sample rate observed: about **52 readings per second** (1,305
  samples captured over a 25-second test).

## The declared logical range is not the same as the reachable range

Confirmed live, 2026-09-01, while building the web demo's `<canvas>`: the
X/Y **logical range** the descriptor declares (0-2896, 0-1370 — see the
table above) is *not* how far the pen's raw X/Y values actually go when
tracing the pad's real physical edges corner to corner.

- Two separate live captures, tracing the pad's actual physical border,
  both measured the pen's real reachable range at only **roughly 38% of
  the declared X max and 41% of the declared Y max** — concretely, X
  topped out around 1098 (of a declared 2896) and Y around 569 (of a
  declared 1370).
- This does **not** contradict the descriptor's separately-declared
  *physical* size (8.96in × 5.12in, in the table above) — that's a
  different field, and hasn't itself been checked against the real
  device with a ruler. What's confirmed here is only that the pen's own
  raw coordinate *output* stays well inside the logical range the
  descriptor says it's capable of reporting.
- Practical effect: anything that assumes a raw sample's X/Y already
  spans the full declared 0-2896 / 0-1370 range (for example, scaling it
  directly onto a fixed-size canvas) will only ever fill a fraction of
  that space. `examples/web_demo/index.html` scales against this
  live-measured reachable range instead, not the declared logical max.
- Not yet independently re-verified beyond these two captures, and not
  checked against a second physical unit of this same pad model.

## The pad is exclusive — and "unplugged" looks identical to "busy"

Confirmed live on macOS, 2026-09-01, while building this driver's web demo
(which needs to know whether it can safely share the pad with the CLI):

- Opening the pad a second time **fails**, both from the *same* Python
  process (`hid.device().open(...)` called twice) and from **two separate
  processes** (one process holding the pad open, a second process trying
  to open it). Both cases raise the byte-identical `OSError("open failed")`.
- Closing the first handle and reopening afterward succeeds normally — the
  failure is specific to a second concurrent open, not a stuck state.
- Because both cases raise the exact same error with the exact same
  message, this driver's `PadNotFoundError` message deliberately does
  **not** claim to know whether the pad is unplugged or just already open
  elsewhere — see `device.py`'s `open_pad()`.

**Scope of this finding: verified on macOS only.** Whether the same
exclusivity and identical-error behaviour holds on Windows or Linux has
not been checked.

## What happens if the pad is unplugged mid-capture

Confirmed live on macOS, 2026-09-01: physically unplugging the pad while
`d.read()` is being called in a loop makes it raise `OSError("read error")`
on the very next read attempt — a different message from the `"open
failed"` seen when opening a not-present or already-open pad (see above),
so the two situations *can* in principle be told apart by message text,
though this driver doesn't currently do so anywhere.

- Every subsequent `d.read()` call on that same, now-broken handle keeps
  raising the identical `OSError("read error")` — it does not recover on
  its own once the pad is plugged back in.
- `d.close()` on that broken handle still succeeds without raising.
- Plugging the pad back in and opening a **brand-new** handle (a fresh
  `open_pad()`/`hid.device().open(...)` call) works normally right away —
  recovery requires reopening the device, not continuing to use the old
  handle.

This matches what `session.py`'s `capture()`/`watch()` and the web demo's
live-pad reader (`examples/web_demo/server.py`) already do: both catch the
general `OSError` class around each read (which `OSError("read error")` is
an instance of) rather than a narrower type, so this confirmed behaviour
required no code change — only this documentation update.

**Scope of this finding: verified on macOS only,** the same as the
exclusivity finding above.

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
ePadXL RS232, and ePad Serial. The full table, straight from that doc
set's own "Determining Pad type via Class Id" page:

| Model | ClassId | LibraryId |
|---|---|---|
| ePadUSB | `7FCD9512-8763-436E-8747-40972EE28EFD` | `8E84F11B-E8E8-49BA-A04A-D860FC9B8CD8` |
| ePadInk - RS232 | `6675E0C0-77AD-4405-B292-B0059CFF01D6` | `047ED132-B2F7-43f7-86E9-D5669174E949` |
| ePadInk - USB | `98C174D3-6D2A-4509-96DB-D5B34FA7A561` | `05E11380-9964-4626-8876-2B6236F90BAF` |
| ePad II - USB | `C1AF33B2-529E-4D2D-B885-DAF2780009EE` | `C71AAAEE-03B6-49E3-938A-EF516CAB10E1` |
| ePad Id | `C55C5D54-8A92-48AD-A32F-1FC58092A581` | `CA04097D-92C5-43CF-911C-759C9C595C87` |
| ePadId Pro | `5C7092FE-FE62-4184-8A64-AC2AAEC1FDE4` | `E0954A32-DA76-4304-B291-00090877BC50` |
| ePadInk Pro | `BFD8B56A-3E13-40da-99D8-5597FD3F97D1` | `B1C890F7-CE3D-42fa-98EB-BB1E94B68F35` |
| ePad LS | `4576EFF9-705A-4d07-9567-3FDD4EF21D73` | `8558B024-8743-4682-8DB0-9B870A6E3F09` |
| ePadXL USB | `D4939098-222F-47D6-927C-EDDB5DEBC4E7` | `51CC300C-10B0-4100-ACE0-04CB43A01C9B` |
| ePadXL RS232 | `5201BB11-6A1F-4e70-8610-7F298E78BCFE` | `2F11352B-BBAD-48d7-AD62-76D381D072F8` |
| ePad Serial | `1DD4EC72-4C89-43AE-A5F0-2344766E626F` | `9E2B8AB2-EBF3-488E-A8F7-E6C65E080EBC` |

This exact device (USB product string `"ePadLink USB ePad"`) corresponds
to that doc set's **ePadUSB** row above. Checked directly against that
doc set's own "Documentation Roadmap" page and its full File Index:
**ePadUSB has no published low-level byte-protocol document anywhere in
that entire 2007 doc set, and isn't even given its own section in the
Roadmap** — every other model here (ePadInk, ePadId, ePad II, ePadId
Pro, ePadInk Pro, ePad LS) gets a dedicated walkthrough section; "ePadUSB"
doesn't, despite having its own `ePadUSB.idl` interface file and its own
row in the ClassID table above. And in the File Index's complete file
list, only two `usb_io.h` files exist anywhere in the whole doc set —
`ePadInk/inc/usb_io.h` and `ePadId-LCD/inc/usb_io.h` — confirming only
those two sibling models ever got a real byte-level report-struct
document published. So this old SDK documentation could not, on its own,
have told anyone this exact pad's byte layout. The real HID descriptor
read directly off the hardware, above, is what actually solved that.

One of those two `usb_io.h` documents is itself worth a look, because it
shows exactly what a byte-level doc from this vendor looks like, and why
it doesn't cover this pad. It defines `WEDGE_VID 0x04df` — the same USB
vendor ID as this pad — but `WEDGE_PID 0x0030`, a different product ID
than this pad's `0x0012`. Its report structures (`DATA_REPORT`, and
`REPORT_ID` values like `R_DATA`, `R_OPTIONS`, `R_BITMAP`) are built
around an on-pad LCD screen (`LCD_WIDTH 320`, `LCD_HEIGHT 240`,
backlight control, bitmap layers) that this plain signature pad doesn't
have. So even the one real byte-protocol document that exists anywhere
under this vendor's own site is for a different physical product, not
this one.

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
- [epadsupport.com/epad_com_api_8.0/](http://www.epadsupport.com/epad_com_api_8.0/) — 2007 ePadAPIs SDK doc root: model list, full ClassId/LibraryId table, Documentation Roadmap, File Index, `usb_io.h`, `ieusb_io.h`
- [epadlink.com/guides/SigCaptureWebSDKGuide.pdf](https://www.epadlink.com/guides/SigCaptureWebSDKGuide.pdf) — SigCaptureWeb Chrome extension, Native Messaging, Windows/Linux support
