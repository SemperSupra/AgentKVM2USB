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
