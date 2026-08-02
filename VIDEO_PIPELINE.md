# AgentKVM2USB Video Pipeline Notes

Last reviewed: 2026-08-02

## Current Physical Signal Path

```text
Wyse 5070 DisplayPort
-> StarTech DisplayPort to HDMI adapter
-> StarTech HDMI to DVI adapter
-> Epiphan KVM cable
-> Epiphan KVM2USB 3.0
-> USB 3.0 host connection
-> Windows DirectShow / UVC
-> OpenCV
```

The current adapter chain produces visible capture from the Wyse firmware screen.
A single active DisplayPort-to-DVI-D adapter or cable is still preferred for
long-term reliability because it reduces EDID and timing negotiation variables.

## Confirmed Host Enumeration

The KVM2USB 3.0 enumerates as a standard UVC camera plus four vendor-defined HID
collections on interface 3:

| Usage | Current interpretation |
| --- | --- |
| `0x101` | Keyboard output |
| `0x102` | Mouse output |
| `0x103` | Touch output plus live input mode feature report |
| `0x104` | System/control collection; feature-report reads currently fail |

The live input mode is exposed on HID usage `0x103`, feature report `3`.
The observed report bytes were:

```text
80 07 38 04 01
```

Decoded as little-endian fields:

| Bytes | Meaning |
| --- | --- |
| `80 07` | Width `1920` |
| `38 04` | Height `1080` |
| `01` | Active signal |

The older assumption that usage `0x104`, feature report `0`, contained input
resolution was wrong for the current device/firmware path. That read path is now
only a fallback in the SDK.

Linux vendor-app disassembly confirms the HID report map used by KVM2USB 3.0:

| Report | Direction | Function |
| --- | --- | --- |
| `1`, length `9` | output | Keyboard report |
| `2`, length `5` | output | Mouse report |
| `3`, length `6` | feature read | Input width, height, active flag |
| `5`, length `7` | output | Touch report |
| `6`, length `2` | feature write | Touch type |
| `7`, length `2` | feature write | Re-enumerate slave |

Only report `3` has been exercised as a read-only status path in the SDK during
this investigation. Output reports and feature writes should be tested only on a
safe firmware screen or sacrificial OS session.

## DirectShow / UVC Capabilities

`ffmpeg -list_options true -f dshow -i video="KVM2USB 3.0"` reports YUY2-only
capture modes. Each mode advertises approximately `15` to `60.0002` fps:

| Resolution |
| --- |
| `640x360` |
| `640x480` |
| `720x480` |
| `720x576` |
| `800x600` |
| `960x540` |
| `1024x768` |
| `1280x720` |
| `1280x1024` |
| `1600x1200` |
| `1920x1080` |
| `1920x1200` |

OpenCV currently opens the device through the `DSHOW` backend at `1920x1080`
with FOURCC `YUY2`. The enhanced probe observed `180` unique captured frames
over `3` seconds, measured `60.0 fps`, while the Wyse firmware screen was static.

## Current Signal Model

There are separate layers that can succeed or fail independently:

| Layer | Evidence | Current state |
| --- | --- | --- |
| Physical video | Snapshot shows Wyse firmware text | Working |
| HID live mode | `touch_feature_3` reports `1920x1080 active` | Working |
| UVC device open | OpenCV/DirectShow opens KVM2USB when GUI is closed | Working |
| Frame content | Sparse white text on black screen | Working, but mostly black |
| GUI/probe concurrency | DirectShow device is exclusive in practice | One process at a time |

Sparse firmware screens may have a very low non-black pixel ratio. A mostly black
frame with readable text must not be treated as a blank/no-signal frame solely
because the non-black ratio is small.

## Reboot Observation

During a Wyse reboot on 2026-08-02, the monitor loop captured these visible
states:

| State | Signal report |
| --- | --- |
| Dell logo | `1920x1080 active` |
| PXE/media check | `1920x1080 active` |
| No bootable devices found | `1920x1080 active` |

No HID live-mode resolution change or signal drop was observed during the
captured reboot window. UVC frame shape remained `1080x1920x3`, and the final
probe measured `60.0 fps`.

## EDID Visibility

The currently accessible read-only paths do not expose the Wyse-facing EDID:

| Path | Result |
| --- | --- |
| Windows `WmiMonitorID` | Shows the host machine's own displays, not the target-facing KVM EDID |
| UVC / DirectShow | Exposes capture formats and frame sizes, not EDID contents |
| HID usage `0x103` | Exposes live mode and active flag, not EDID contents |
| USB MI_00 `KVM2USB 3.0 Config` | Present but has Windows problem code `28` because no vendor driver is installed |

EDID inspection likely requires the official Epiphan configuration driver/tool or
a reverse-engineered read-only command through the vendor config interface.
EDID writes remain deferred high-risk work.

Static analysis of the official Linux configuration tool shows EDID IO behind
the MI_00 vendor config interface, using libusb vendor control transfers. The
observed update/EDID paths include request `0xA0` for chunked write/read-verify
transfer, request `0xC4` for one-byte flash-status polling, and
requests `0xC5`/`0xD4` in firmware/update flows. These are not used by the
current SDK.

## Remaining Investigation

- Live-validate the recovered HID write paths on a sacrificial target session:
  keyboard report `1`, mouse report `2`, touch report `5`, touch-type feature
  report `6`, and re-enumerate feature report `7`.
- Confirm whether the DirectShow mode list changes with different target input
  resolutions or adapter chains.
- Measure source-frame cadence using SDK frame sequence numbers over longer
  intervals and while the target display changes.
- Validate keyboard, mouse, touch, and macro injection only on safe firmware
  screens or a sacrificial OS session.
- Defer firmware flashing, EDID writes, raw USB control writes, and unknown HID
  writes until there is an explicit hardware-safe test plan.
