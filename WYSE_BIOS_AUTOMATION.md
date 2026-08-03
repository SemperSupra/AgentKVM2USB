# Wyse BIOS Automation Map

Last updated: 2026-08-03

## Objective

Map the attached Wyse firmware setup screens so AgentKVM2USB can automate
bring-up for multiple machines using KVM video plus macro-driven HID input.

## Current Live State

Video capture is healthy.

Observed through `EpiphanKVM_SDK.get_status()`:

```json
{
  "resolution": "1920x1080",
  "is_signal_active": true,
  "signal_source": "touch_feature_3",
  "firmware_version": "4.0.0.39896"
}
```

The captured Wyse screen currently shows:

```text
No bootable devices found.
Press F1 key to retry boot.
Press F2 key to reboot into setup.
Press F5 key to run onboard diagnostics.
```

Read-only MI_00 status after the Wyse power cycle also reports:

```text
RGB 1920x1080p@60.318, HDMI
```

## Current Blocker

The KVM2USB accepts keyboard HID reports from the host, but the Wyse did not
react to them during the live BIOS-entry probe.

Confirmed host-side write behavior:

| Probe | Host HID result | Wyse result |
| --- | --- | --- |
| `PRESS f2` | Macro succeeded | No visible change |
| `PRESS f5` | Macro succeeded | No visible change |
| `HOTKEY ctrl alt delete` | Macro succeeded | No visible change |
| `PRESS capslock` twice | `{"press": 9, "release": 9}` each time | KVM LED status remained `caps=false` |
| Raw keyboard report with ID `1` | `hid.write(...)` returned `9` | No visible change |
| Legacy keyboard report without report ID | `hid.write(...)` returned `-1` | Not valid for this device |

Interpretation: the host-to-KVM2USB keyboard report path is functioning, but
the Wyse-facing USB HID side is not affecting the target. The highest-priority
physical check is the target-side USB connection from the Epiphan KVM cable to
the Wyse. The video-only DVI path can work even when that USB leg is absent or
not enumerated.

Post-power-cycle note: after the Wyse was power-cycled, video stayed stable at
`1920x1080 active`, the boot-failure prompt returned, and another `PRESS f2`
still wrote `9` byte press/release reports without changing the screen.

## Required Pre-Mapping Verification

Use this sequence before BIOS exploration:

```text
1. Confirm the Epiphan KVM cable USB-A lead is connected to the Wyse.
2. Power-cycle or reboot the Wyse so firmware enumerates the KVM keyboard.
3. Capture the screen and verify `1920x1080 active`.
4. Run `PRESS f2` from the no-boot screen.
5. If still unchanged, run `HOTKEY ctrl alt delete` and watch for reboot.
6. Do not change BIOS values until a key press visibly moves between screens.
```

## Beagle-12 HID Path Diagnostic

The Beagle-12 should be controlled by the host PC and placed inline on the
target side of the KVM2USB, between the Epiphan KVM cable USB-A lead and the
Wyse USB port.

```text
Host PC control USB
  -> Beagle-12 control port

Captured USB bus:
Host PC
  -> USB 3.0 cable
  -> KVM2USB 3.0
  -> Epiphan KVM cable USB-A lead
  -> Beagle-12
  -> Wyse USB port
```

Do not put the Beagle between the host PC and the KVM2USB for this blocker. We
already know the host PC can write valid reports to the KVM2USB; the unknown
segment is the KVM2USB slave HID side presented to the Wyse.

Prior DE2-115 evidence from `SemperSupra/DE2-115` is directly useful here:

- The DE2 host-mode path with KVM2USB inline showed repeated
  connect/disconnect/reset but no useful packets.
- The same KVM2USB validated on the normal PC hub path as
  `VID_2B77&PID_3661`.
- The Beagle saw real `SETUP`, descriptor, `ACK`, and `IN/NAK` traffic on a
  healthy PC-side path, so for the Wyse capture we should treat "resets only"
  as materially different from "enumerates then ignores key reports".
- The DE2 process also used correlated host actions plus analyzer evidence; the
  matching AgentKVM2USB script is now `scripts/capture_hid_path_experiment.py`.

Current host analyzer state:

```text
Device: Total Phase Beagle Protocol Analyzer
Instance ID: USB\VID_1679&PID_2001\TP1112-141536
Windows status: OK
Driver service: WinUSB
Problem: CM_PROB_NONE / Code 0
Vendor API detect.py: port 0 available, serial 1112-141536
Interpretation: Windows sees the analyzer control interface and the Total Phase
API can open it.
```

Official Total Phase setup notes say the Beagle USB 12 is used with Data Center
or the Beagle API for low/full-speed USB monitoring, and the Windows USB driver
must be installed before the Beagle can be used by the host software. Data
Center can then save captures as CSV, binary, or `.tdc`.

Capture procedure:

```text
1. Start the Beagle capture before powering on or power-cycling the Wyse.
2. Power-cycle the Wyse.
3. Watch for USB reset, speed negotiation, device descriptor, configuration
   descriptor, HID descriptor, report descriptor, Set Configuration, and Set Idle
   or Set Protocol traffic.
4. After the boot-failure screen appears, run the host-side HID experiment:

   .venv\Scripts\python.exe scripts\capture_beagle_usb12.py `
     --max-events 6000 `
     --max-seconds 15 `
     --output .work\beagle\wyse-hid-capslock-inline-decoded.jsonl

   .venv\Scripts\python.exe scripts\capture_hid_path_experiment.py `
     --experiment-id wyse-hid-capslock-inline-decoded `
     --operator codex

5. Stop the Beagle capture and store it in the private evidence vault with the
   same experiment ID.
```

Latest inline Beagle result:

```text
Capture: .work\beagle\wyse-hid-capslock-inline-decoded.jsonl
Experiment: .work\experiments\wyse-hid-capslock-inline-decoded
Capture window: 2026-08-03T06:29:49Z through 2026-08-03T06:30:04Z
Macro window: 2026-08-03T06:29:55Z through 2026-08-03T06:29:57Z
Beagle records: 3736
USB event records: 1 TARGET_CONNECT_UNRESET
Token traffic: 1868 IN polls from Wyse to address 23 endpoint 2
Handshake traffic: 1867 NAK
HID data packets: 0
Host macro result: two Caps Lock presses, each write returned 9-byte press and
release reports
KVM2USB status before/after: 1920x1080 active, firmware 4.0.0.39896, Caps Lock
LED false before and after
```

Interpretation: the Wyse-facing USB leg is electrically present and the Wyse is
polling the KVM2USB target-side interrupt endpoint, but the KVM2USB never returns
keyboard data during host-side Caps Lock writes. This shifts the blocker away
from a missing cable and toward the KVM2USB target-side HID forwarding state,
target-side enumeration mode, or a missing vendor-app activation/re-enumeration
step.

Expected downstream evidence if the target-side path is healthy:

| Event | Expected on Beagle |
| --- | --- |
| Wyse power-up | USB reset and enumeration on the Wyse-facing cable |
| Device descriptor | A keyboard/mouse-class or composite HID device from the KVM2USB slave side |
| HID setup | `Set Configuration`, HID report descriptor reads, and idle/protocol setup |
| `PRESS capslock` | Interrupt IN keyboard report with usage `0x39`, then release report |
| Wyse LED response | Output report or control transfer from Wyse changing Caps Lock LED state |
| `PRESS f2` | Interrupt IN keyboard report with usage `0x3B`, then release report |

Decision tree:

| Beagle finding | Interpretation | Next action |
| --- | --- | --- |
| No bus activity at all | Cable, port, or KVM slave power/link problem | Try another Wyse USB port and confirm the KVM cable USB-A lead |
| Reset but no descriptors | Electrical/link or device-side enumeration failure | Try USB 2.0-only path/hub and inspect KVM cable |
| Descriptors but no HID interface | KVM2USB slave side not presenting keyboard/mouse | Compare with vendor app behavior and recovered re-enumeration report |
| HID interface enumerates, but no key reports after host macro | KVM2USB firmware is not forwarding host writes to slave HID | Capture host-side USBPcap in parallel and compare timestamps |
| Key reports appear, but Wyse does not respond | Wyse firmware input policy/port issue | Try another USB port and map BIOS USB settings with a physical keyboard |
| Key and LED reports appear | HID path works | Continue BIOS setup mapping |

Once the target reacts, use this setup-entry macro:

```text
PRESS f2
DELAY 5000
```

If entry must happen during POST instead of the no-boot screen:

```text
HOTKEY ctrl alt delete
DELAY 500
PRESS f2
DELAY 200
PRESS f2
DELAY 200
PRESS f2
DELAY 5000
```

## Mapping Discipline

Capture one screen per stable BIOS page and transcribe:

| Field | Meaning |
| --- | --- |
| Path | Left-menu/category path to the page |
| Visible settings | Labels and current values exactly as shown |
| Safe navigation | Keys used to arrive without changing values |
| Automation impact | Whether the setting affects boot, display, USB, network, PXE, security, or recovery |
| Change risk | Read-only, low, medium, high |
| Desired fleet default | Leave blank until a bring-up policy is approved |

Use arrows, `tab`, `esc`, and page keys for exploration. Avoid `enter`, `space`,
or value-changing keys unless the current page clearly requires expansion and
the selected control is known not to toggle a setting.

## Initial BIOS Map

Only the pre-setup boot-failure page has been mapped so far because target-side
HID input did not visibly affect the Wyse.

| Path | Visible settings or actions | Safe navigation | Automation impact | Change risk |
| --- | --- | --- | --- | --- |
| Boot failure screen | `F1` retry boot; `F2` reboot into setup; `F5` onboard diagnostics | Function keys only after target HID is verified | Setup entry and diagnostics entry | Low |

## Next Pages To Map

After target HID is verified:

1. System information and BIOS version.
2. Boot sequence and UEFI/PXE order.
3. Integrated NIC and PXE controls.
4. USB configuration and USB boot support.
5. Video/display settings.
6. Secure Boot and TPM/security posture.
7. Virtualization support.
8. Power management and wake behavior.
9. POST behavior, keyboard errors, and fast boot.
10. Maintenance/service tag, BIOS events, and diagnostics.
