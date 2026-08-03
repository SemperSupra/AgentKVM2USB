# Input Path Recovery and Compatibility Strategy

This document is the implementation plan for issue #8. It defines how
AgentKVM2USB should evolve from an Epiphan-specific HID prototype into a
capability-driven input subsystem that works predictably across the device's
supported keyboard and pointer modes.

## Scope

The input path includes:

- discovering and grouping the HID collections belonging to one physical KVM;
- encoding keyboard reports;
- encoding relative mouse reports;
- encoding absolute pen and touch reports;
- tracking pressed-key, button, and contact state;
- selecting the correct input mode for the target environment;
- recovering safely from cancellation, disconnect, reconnect, and exceptions;
- supporting multiple attached KVM units without mixing their interfaces.

This work must not add firmware writes, FPGA writes, EDID writes, flash writes,
or undocumented persistent changes to the device.

## Current State

`EpiphanKVM_SDK` currently:

- hard-codes VID `0x2B77` and PID `0x3661`;
- enumerates four HID collections using only the HID usage value;
- assigns usage `0x101` to keyboard, `0x102` to relative mouse, `0x103` to
  absolute pointer, and `0x104` to status/system;
- sends keyboard reports through the keyboard collection;
- sends absolute coordinates through the absolute-pointer collection;
- opens the relative-mouse collection but does not use it;
- suppresses most device-open and report-write errors;
- does not group interfaces by physical-device serial or stable path;
- does not model key-down, key-up, button-down, button-up, drag, wheel, contact,
  reconnect, or release-all state explicitly.

The present tests prove basic macro dispatch and absolute-coordinate clamping,
but they do not prove that targets receive correct keyboard, mouse, pen, or
touch events.

## Design Principles

1. **Semantic actions are separate from report bytes.**
   Higher layers request key presses or pointer actions. Device-profile codecs
   translate those actions into verified reports.
2. **A physical device is the unit of selection.**
   Keyboard, mouse, pointer, status, and video interfaces must never be combined
   across different KVM units.
3. **Descriptors and measured behavior define codecs.**
   HID usage values alone are insufficient to define byte layouts.
4. **Relative and absolute pointer modes remain distinct.**
   Absolute positioning must fail clearly when the active profile only supports
   relative movement.
5. **Input state is explicit and always releasable.**
   Shutdown, cancellation, exceptions, and disconnects must not leave keys,
   buttons, or contacts logically active.
6. **Shared development USB identities require explicit opt-in.**
   Production discovery must not trust a shared test VID/PID alone.
7. **Successful writes are not proof of target delivery.**
   Tests must observe the target-side event or visible effect.

## Target Architecture

### Device identity and profiles

Introduce versioned profiles similar to:

```python
DeviceProfile(
    profile_id="epiphan-kvm2usb3",
    identities=[UsbIdentity(vid=0x2B77, pid=0x3661)],
    collections={
        "keyboard": HidCollectionProfile(...),
        "relative_pointer": HidCollectionProfile(...),
        "absolute_pointer": HidCollectionProfile(...),
        "system": HidCollectionProfile(...),
    },
)
```

Each HID collection profile should include:

- usage page and usage;
- interface number when available;
- report ID;
- input, output, and feature report lengths;
- optional report-descriptor fingerprint;
- capability flags;
- codec name;
- supported protocol or firmware versions;
- documented quirks;
- whether a report-ID prefix is required by the host HID library.

Initial profiles:

- `epiphan-kvm2usb3`;
- `openkvm2usb-lab-shared`, disabled unless development mode is explicit;
- future OpenKVM2USB normal and recovery identities;
- simulator and trace-replay fixtures.

### Discovery and physical-device grouping

Discovery should collect, for every matching HID path:

- VID and PID;
- manufacturer and product strings;
- serial number;
- release number;
- HID path;
- interface number;
- usage page and usage;
- report descriptor or a descriptor fingerprint;
- open status and structured error information.

Collections must then be grouped into a `PhysicalKvmDevice` with a stable ID.
When multiple devices match, callers must select a serial number or stable path.
Missing, duplicate, inaccessible, and unexpected collections must be reported.

### Semantic input API

Keyboard:

```text
key_down(key)
key_up(key)
press(key)
hotkey(*keys)
type_text(text, layout="us")
release_all_keys()
```

Relative pointer:

```text
move_relative(dx, dy)
button_down(button)
button_up(button)
click_current(button="left")
drag_relative(dx, dy, button="left")
wheel(vertical=0, horizontal=0)
release_all_buttons()
```

Absolute pointer:

```text
move_absolute(x, y)
contact_down(x, y)
contact_move(x, y)
contact_up(x, y)
click_absolute(x, y, button="left")
drag_absolute(start, end, button="left")
release_contact()
```

The macro language should call this semantic API. Do not expand the macro DSL
until the transport and state model are reliable.

### Report codecs

Use separate codecs for:

- keyboard;
- relative mouse;
- pen/stylus;
- touch screen;
- status/system reports.

Every codec must validate:

- report ID and report length;
- signed and unsigned field widths;
- coordinate ranges;
- button, modifier, contact, and in-range masks;
- release report;
- advertised optional fields such as wheels;
- unsupported operations.

## Delivery Phases

### Phase A — Discovery and diagnostics

This is the first implementation slice.

Deliver:

- device-profile data structures;
- complete HID enumeration records;
- physical-device grouping;
- deterministic selection by serial or stable path;
- structured diagnostics for missing, duplicate, unexpected, and inaccessible
  collections;
- explicit development-mode handling for shared test identities;
- fixture-driven tests for zero, one, multiple, partial, and duplicate devices.

Do not change input report bytes in Phase A.

Exit gate:

- one Epiphan unit is represented as one physical device with its observed
  collections;
- two simulated or physical units cannot have their interfaces mixed;
- diagnostics contain enough information to create or refine a device profile;
- existing public APIs remain compatible or have a documented migration path.

### Phase B — Keyboard correctness

Deliver:

- explicit key-down and key-up;
- pressed-key and modifier state;
- release-all behavior;
- complete US-layout encoding for letters, digits, punctuation, symbols,
  whitespace, navigation, editing, function keys, and common modifiers;
- deterministic errors for unsupported characters;
- raw HID-usage escape hatch for research and uncommon keys;
- tests for report bytes, rollover boundary, cancellation, exception, shutdown,
  and reconnect.

Exit gate:

- US-layout text and named-key operations are verified on Windows, Linux, and a
  pre-boot target;
- no supported failure path leaves a key or modifier pressed.

### Phase C — Generic relative mouse

Deliver:

- signed relative X/Y movement;
- button down/up;
- click at current position;
- drag;
- vertical and horizontal wheel when advertised;
- button-state tracking and release-all;
- BIOS/UEFI, bootloader, installer, recovery, Windows, and Linux validation.

Exit gate:

- generic relative mouse works on targets that do not accept pen or touch;
- unsupported wheel or button functions fail explicitly.

### Phase D — Pen and touch

Deliver:

- separate pen and touch codecs;
- contact, tip, in-range, confidence, button, and contact-ID semantics as
  advertised by descriptors and verified captures;
- viewport-to-target coordinate transformation;
- absolute click and drag;
- explicit target-mode selection and user override.

Exit gate:

- pen and touch are not conflated;
- corner, center, click, drag, contact, and release tests pass on supported
  graphical targets.

### Phase E — Multi-device and resilience

Deliver:

- multiple simultaneous KVM sessions;
- reconnect and stale-handle replacement;
- per-device and per-target input-mode preferences;
- concurrency controls;
- long-duration and repeated disconnect tests.

### Phase F — OpenKVM2USB identities

Deliver:

- profiles for approved OpenKVM2USB laboratory and permanent identities;
- shared test identities rejected unless development mode is enabled;
- the same semantic input API validated against Epiphan and open firmware.

## Pointer Mode Selection

Expose:

- `generic-relative`;
- `pen-absolute`;
- `touch-absolute`;
- `auto`.

Recommended policy:

- BIOS, UEFI, GRUB, text installers, and recovery environments: keyboard plus
  generic relative mouse;
- graphical desktops: verified absolute mode when appropriate, with relative
  mouse retained as a fallback;
- drag- or button-sensitive applications: use only a mode whose codec has
  verified button-state semantics;
- persist user override per physical KVM and target profile.

## Protocol Acquisition

Collect one operation per capture where practical.

Keyboard captures:

- key down and key up;
- shifted letters and symbols;
- modifiers;
- Ctrl+Alt+Delete;
- rollover boundary;
- lock-key and LED behavior.

Relative mouse captures:

- positive and negative one-unit movement;
- maximum positive and negative movement;
- every advertised button down and up;
- drag;
- vertical and horizontal wheel.

Pen and touch captures:

- center and four corners;
- hover or in-range state when available;
- contact down, move, and up;
- button-state variations;
- click and drag.

Raw captures and proprietary artifacts belong in the private research vault.
Only reviewed, sanitized protocol facts and independently written codecs belong
in the public repository.

## Validation Matrix

| Target state | Keyboard | Relative mouse | Pen/touch |
| --- | --- | --- | --- |
| BIOS/UEFI | Required | Required where pointer exists | Optional |
| GRUB/bootloader | Required | Validate where supported | Not relied upon |
| Linux console/text UI | Required | Validate where supported | Not relied upon |
| Linux desktop | Required | Required | Required when advertised |
| Windows desktop/login | Required | Required | Required when advertised |
| Windows recovery/installer | Required | Required | Validate with relative fallback |

Use target-side receivers when an operating system is present:

- Linux `evtest` or an evdev/libinput test receiver;
- Windows Raw Input or HID test receiver;
- visible screen confirmation for pre-boot environments.

## Safety and Failure Handling

Always attempt a release/reset sequence during:

- normal completion;
- macro cancellation;
- exception handling;
- backend replacement;
- device disconnect;
- device switch;
- application shutdown.

Return structured results and errors. Do not silently suppress device-open,
selection, encoding, or report-write failures.

## Coordination

Issue #8 is the canonical work item. See `docs/REMOTE_AGENT_COORDINATION.md` for
how the web assistant and local agents exchange state through GitHub.

## Public References

- Epiphan technical specifications:
  <https://www.epiphan.com/userguides/kvm2usb-30/Content/UserGuides/VideoGrabber/KVM/1-GettingStarted/tech-specs.htm>
- Epiphan pointer modes:
  <https://www.epiphan.com/userguides/kvm2usb-30/Content/UserGuides/VideoGrabber/KVM/2-Control/mouse-type.htm>
- Epiphan known issues:
  <https://www.epiphan.com/userguides/kvm2usb-30/Content/UserGuides/VideoGrabber/KVM/3-Advanced/known-issues.htm>
- OpenKVM2USB USB identity policy: `SemperSupra/OpenKVM2USB` PR #22 until
  merged, then `docs/USB_IDENTITY.md` in that repository.
