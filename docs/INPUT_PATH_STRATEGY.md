# Input Path Recovery and Compatibility Strategy

Canonical issue: #8. Future multi-device roadmap: #23 and
`docs/MULTI_DEVICE_MEDIA_SPEECH_ROADMAP.md`.

## Scope

The input path includes:

- discovering and grouping the HID collections belonging to one physical KVM;
- keyboard, relative mouse, pen, touch, and status codecs;
- explicit key, button, and contact state;
- target-mode selection;
- release-all and reconnect safety;
- multiple attached KVM units without interface mixing.

It excludes firmware, FPGA, EDID, flash, and undocumented persistent writes.

## Principles

1. Semantic actions remain separate from report bytes.
2. A physical KVM is the unit of selection.
3. Descriptors and measured target behavior define codecs.
4. Relative mouse, pen, and touch semantics remain distinct.
5. Input state is explicit and always releasable.
6. Shared development USB identities require explicit opt-in.
7. Successful host writes are not proof of target delivery.
8. Multi-device orchestration starts only after one-device correctness is proven.

## Device Profiles

Profiles define:

- VID/PID and string constraints;
- serial behavior and firmware range;
- interface topology;
- usage page, usage, interface, report IDs, and lengths;
- descriptor fingerprints;
- capabilities, codecs, and quirks;
- report-ID prefix behavior.

Initial profiles:

- `epiphan-kvm2usb3`;
- approved OpenKVM2USB lab/permanent identities;
- simulator/replay fixtures.

## Physical Device Grouping

Discovery records every HID path plus UVC and MI_00 association evidence:

- serial;
- PnP ContainerId;
- composite instance;
- location path;
- controller/hub/port;
- manufacturer/product/release;
- interface number, usage page, usage, and descriptor fingerprint;
- access/open diagnostics.

Collections are grouped into one stable `PhysicalKvm`. Multiple matches require an
explicit selector. Partial, duplicate, inaccessible, or mixed devices fail
closed.

## Semantic Input API

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
click_current(button)
drag_relative(dx, dy, button)
wheel(vertical, horizontal)
release_all_buttons()
```

Absolute pointer:

```text
move_absolute(x, y)
contact_down(x, y)
contact_move(x, y)
contact_up(x, y)
click_absolute(x, y, button)
drag_absolute(start, end, button)
release_contact()
```

Unsupported semantics fail explicitly; absolute actions are never silently
translated into uncalibrated relative movement.

## Delivery Phases

### Phase A — Discovery and diagnostics

- profile structures;
- complete enumeration records;
- stable physical grouping;
- deterministic selectors;
- partial/duplicate/inaccessible diagnostics;
- fixture tests for zero, one, and multiple devices.

### Phase B — Keyboard correctness

- explicit key down/up;
- pressed-key/modifier state;
- release-all;
- complete initial US layout;
- deterministic unsupported-character errors;
- exact report, rollover, failure, cancellation, reconnect, and shutdown tests;
- target-receipt validation.

Current blocker: #14 and #22; implementation PR: #13.

### Phase C — Generic relative mouse

- signed movement;
- buttons, click, drag, and wheels;
- explicit state and release-all;
- BIOS/UEFI, bootloader, recovery, Windows, and Linux validation.

### Phase D — Pen and touch

- separate codecs;
- contact, tip, in-range, confidence, button, and contact-ID semantics where
  advertised;
- coordinate transformation;
- explicit mode and user override;
- corner, center, click, drag, and release validation.

### Phase E — Multi-device and resilience

#### E1 — Stable identity

Group HID, UVC, and MI_00 by serial, ContainerId, composite device, location path,
hub, and port. Camera index is never the persistent ID.

#### E2 — No-mixing selection

Reject ambiguous, partial, duplicate, inaccessible, and mixed units. Prove with
two-device fixtures.

#### E3 — Session isolation

One connected session per physical KVM with independent locks, input state,
video ownership, health, runtime root, and release-all behavior.

#### E4 — Concurrency

Two KVMs connected simultaneously; concurrent health/video; harmless input reaches
only the explicitly selected target.

#### E5 — Topology and bandwidth

Expose controller/hub/port evidence for the later control plane's stream and
bandwidth policy.

Higher-level worker processes, target bundles, API routing, dashboard, media, and
speech belong to #12 and #23 after this exit gate.

### Phase F — OpenKVM2USB identities

- approved lab and permanent profiles;
- shared IDs require development mode;
- same semantic conformance tests as Epiphan.

## Validation Matrix

| Target state | Keyboard | Relative mouse | Pen/touch |
| --- | --- | --- | --- |
| BIOS/UEFI | Required | Required where supported | Optional |
| Bootloader/text UI | Required | Validate where supported | Not relied upon |
| Linux desktop | Required | Required | Required when advertised |
| Windows desktop/login | Required | Required | Required when advertised |
| Recovery/installer | Required | Required | Validate with relative fallback |

Use target-side event receivers where possible and visible screen evidence for
preboot states.

## Failure Handling

Always attempt release/reset during normal completion, cancellation, exception,
backend replacement, device switch, disconnect, reconnect, and shutdown. Return
structured results; do not swallow selection, open, encoding, or write failures.

## Exit Gate

One-device semantic correctness is validated first. Phase E completes only when
two attached KVM units remain isolated through discovery, selection, operation,
disconnect, reconnect, and long-duration concurrency tests.