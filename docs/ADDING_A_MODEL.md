# Adding support for a different pad model

This driver only knows the byte layout of one device: the ePadLink "ePad"
(VID `0x04DF`, PID `0x0012`) documented in
[`HARDWARE_NOTES.md`](HARDWARE_NOTES.md). ePadLink sells other models too -
some with real buttons, some with a screen (see the ClassID table in
`HARDWARE_NOTES.md` for the model list this vendor has shipped in the
past). Adding support for one of those, or any other HID signature pad,
means learning its byte layout the same way this one was learned: by
reading it, not by guessing. Follow these steps, in order.

## 1. Read the new model's live HID descriptor off real hardware first

This is the hard rule, and it comes before everything else: **do not write
any decode logic until you have read the new device's own HID report
descriptor from a real, physical unit of that model.** A different model
is not guaranteed to share this pad's byte layout, bit positions, or even
report length - it might have extra bytes for buttons, a screen, or
anything else. The vendor's own product line documents multiple pad
models with meaningfully different hardware (see the ClassID table in
`HARDWARE_NOTES.md`), so "it's probably the same" is not a safe
assumption.

```python
import hid

d = hid.device()
d.open(NEW_VENDOR_ID, NEW_PRODUCT_ID)
print(d.get_report_descriptor().hex())
```

Decode that descriptor by hand (or with a HID descriptor parser) before
writing a single line of `decode_report()`-equivalent code for the new
model. Record the raw descriptor bytes in your new hardware-notes doc
(step 5) exactly the way `HARDWARE_NOTES.md` records this pad's - that's
the actual proof the byte layout is real, not assumed.

## 2. Confirm behavior live - don't trust the descriptor alone

A HID report descriptor tells you the *shape* of the data (which bytes,
which bits, what usage each one claims), but not necessarily what the
device *actually does* in practice. This project's own touch/pressure
decode was not trusted from the descriptor alone either - it was confirmed
by capturing real pen strokes and watching the touch bit and pressure
value change in real time (see "Live-confirmed behaviour" in
`HARDWARE_NOTES.md`).

For a new model, do the equivalent:

- If it has real buttons, press each one individually and confirm exactly
  which bit changes, and only that bit.
- If it has a screen, check whether writing to it uses the same report
  path as reading position data, or a separate one (`R_OPTIONS`,
  `R_BITMAP`, or similar - see the `usb_io.h` discussion in
  `HARDWARE_NOTES.md` for what that can look like on this vendor's other
  models).
- Draw on it and confirm X/Y/pressure move the way the descriptor's
  logical ranges suggest they should - not just that some bytes change.
- Note the real observed sample rate, the same way this pad's ~52
  readings/second was measured, not assumed.

## 3. Write one new protocol module, kept separate

Create `protocol_<model>.py` (e.g. `protocol_premium.py`), shaped like
[`protocol.py`](../src/epad_signature_pad_hid_driver/protocol.py): its own
`VENDOR_ID`/`PRODUCT_ID` constants, its own `PenSample`-equivalent
dataclass (or a shared one, if the fields genuinely line up - see below),
its own `decode_report()`/`encode_report()` pair, no `hid` import.

**Never merge two different models' decode logic into one "clever" shared
function.** Two pads that happen to share a report length are not
guaranteed to share a byte layout, and a function that branches internally
on model to decode different layouts is exactly the kind of shared code
that turns into unreadable, easy-to-break state once a third model shows
up. A second protocol module that duplicates a few lines of the first is
far cheaper than one shared function silently mis-decoding a byte because
someone assumed too much in common. If two models' `PenSample` really are
identical in meaning (not just in field count), it's fine to reuse
`protocol.PenSample` itself for both - but keep `decode_report()`/
`encode_report()` separate per model regardless.

## 4. Wire the new model's IDs into device.py

`open_pad()` already takes overridable `vendor_id`/`product_id`
parameters for exactly this purpose:

```python
from epad_signature_pad_hid_driver.device import open_pad

pad = open_pad(vendor_id=NEW_VENDOR_ID, product_id=NEW_PRODUCT_ID)
```

No change to `device.py` itself is needed for a model that speaks the same
raw-HID-over-`hidapi` transport this one does (which is likely - see the
`ieusb_io.h` note in `HARDWARE_NOTES.md` on why these pads are all plain
HID devices under the hood). `session.py`'s `capture()`/`watch()` already
accept the same overridable IDs and pass them straight through to
`open_pad()`.

## 5. Write a hardware-notes doc for it

Copy the shape of `HARDWARE_NOTES.md`: device identity (VID/PID/product
string), the actual descriptor bytes and how they were read, a byte-by-bit
table of the new report layout, the live-confirmed behaviour section, and
what (if anything) was checked in the vendor's own old SDK docs for that
specific model. Name it something like `HARDWARE_NOTES_<MODEL>.md`.

## 6. Add tests, in the existing style

Follow `tests/test_protocol.py`'s pattern for the new protocol module:
pure decode/encode tests against synthetic byte strings, no real hardware
needed to run them. If the new model needs its own `device.py`/`session.py`
behaviour (not just different IDs), mirror `tests/test_device.py` and
`tests/test_session.py` the same way, using `tests/helpers.py`'s
`FakePad` (or a variant of it, if the new model's wire behaviour differs
enough to need one).

## 7. Mark anything unconfirmed as "unconfirmed"

This pad's own docs already do this: `HARDWARE_NOTES.md` calls out byte
0's 3-bit vendor field and bit 6 as observed in the descriptor but never
confirmed to mean anything in practice. Do the same for the new model -
if a bit's *presence* is proven by the descriptor but its *meaning* was
never confirmed by a live test, say so explicitly in the new
hardware-notes doc, rather than guessing a plausible-sounding name for it.
An honestly-labeled "unconfirmed, treated as unused" bit is worth more
than a confident-sounding guess that turns out to be wrong.
