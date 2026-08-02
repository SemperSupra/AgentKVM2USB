# Epiphan Vendor Artifact Inventory

Last reviewed: 2026-08-02

This file records official Epiphan downloads used for static reverse-engineering.
Artifacts are stored under `.work/epiphan-downloads/` and extracted under
`.work/epiphan-extracted/`. Both paths are ignored by Git.

Do not install drivers, run vendor tools against connected hardware, flash
firmware, write EDID, or send unknown USB control transfers without an explicit
hardware-safe test plan.

## Official Sources

- KVM2USB 3.0 support page:
  `https://www.epiphan.com/support/kvm2usb-3-0-software-documentation/`
- Legacy KVM2USB driver/support page:
  `https://www.epiphan.com/support/kvm2usb-drivers-documentation/`

## Downloaded Artifacts

| Category | File | SHA256 |
| --- | --- | --- |
| KVM2USB 3.0 firmware | `firmware-kvm2usb3-uvc-4.0.0-r39896.fw` | `6a07699235aea25b00f601f13b5ef3fe5ec3e56237e9ef5b6c10939c15145039` |
| KVM2USB 3.0 Windows app/config tool | `KvmAppWin64-0.99.27-20171125.zip` | `dc514a7e50ed890c0c115114eec1f64a30f96d8edb04ba8a41191a199debc6c5` |
| KVM2USB 3.0 Linux app | `KvmApp-0.99.26-20170928-x86_64.AppImage` | `806fb08d68178dc87f51d1875e0c035c1039da1701135ddd39fa00818f40ff81` |
| Legacy Epiphan Windows USB/PCI driver, 64-bit | `epiphan-usb-pci-drivers-windows-64bit-3.30.2.0010-32219-1751.zip` | `411dd1acddf10fd96319216244cbbf2564f4f0f6c89dc9d5001b883b002b8c5e` |
| Legacy Epiphan Windows USB/PCI driver, 32-bit | `epiphan-usb-pci-drivers-windows-32bit-3.30.2.0010-32219-1751.zip` | `baa40cdef518cb14f6477fc777fd70e405e7e77f34aab9eaa9512e934a0c9f86` |

The KVM2USB 3.0 support page labels the Windows capture configuration tool as
version `0.99.2`, but the current official download filename is
`KvmAppWin64-0.99.27-20171125.zip`.

## KVM App Bundle Findings

The Windows app bundle contains:

- `KvmApp.exe`
- `EpiphanCaptureConfig.exe`
- `libusb-1.0.dll`, version `1.0.21.11156`
- `driver/epiphan_avio_series.inf`
- `driver/winusbcoinstaller2.dll`
- `driver/WdfCoInstaller01011.dll`

The INF is the most important current clue. It installs WinUSB for the
vendor-specific configuration interface:

| Device | Hardware ID |
| --- | --- |
| KVM2USB 3.0 Configuration | `VID_2B77&PID_3661&MI_00` |
| KVM2USB 3.0 Sandbox | `VID_2B77&PID_366F` |
| KVM2USB 3.0 Repair | `VID_2B77&PID_3660` |

It also registers device interface GUID:

```text
{9f543223-cede-4fa3-b376-a25ce9a30e74}
```

This matches the Windows PnP observation that USB MI_00 currently appears as
`KVM2USB 3.0 Config` with problem code `28` when no vendor/WinUSB driver is
installed. The missing config functionality is likely behind MI_00 rather than
the UVC camera or HID collections.

Static strings from `KvmApp.exe` show the control app uses `hidapi` for KVM
keyboard, mouse, touch, feature, and firmware-version access. Relevant strings:

- `getInputScreenResolutionFeature`
- `KvmInputScreenResolutionReport`
- `KvmReenumerateReport`
- `KvmTouchTypeReport`
- `HID path/feature`
- `hid_get_feature_report`
- `hid_send_feature_report`
- `hid_write`

The Linux AppImage is higher-value for static analysis than the Windows bundle
because its ELF metadata preserves many C++ function names. Extracted files
include `KvmApp`, `EpiphanCaptureConfig`, `start.sh`, `install.sh`, `check.sh`,
and `udev/99-usbkvm.rules`. The udev rule grants `plugdev` access for product
IDs `2b77:3660`, `2b77:3661`, and `2b77:366f`, matching normal, repair, and
sandbox modes.

Linux `KvmApp` disassembly confirms these HID report layouts:

| Operation | HID API | Report ID | Length | Payload |
| --- | --- | ---: | ---: | --- |
| Keyboard output | `hid_write` | `1` | `9` | Report ID plus 8-byte keyboard report |
| Mouse output | `hid_write` | `2` | `5` | Report ID plus 4-byte mouse report |
| Touch output | `hid_write` | `5` | `7` | Report ID plus 4-byte touch coordinates/buttons and 2-byte contact/type field |
| Input size/status | `hid_get_feature_report` | `3` | `6` | Report ID plus `width_le16`, `height_le16`, active flag |
| Touch type | `hid_send_feature_report` | `6` | `2` | Report ID plus 1-byte touch type |
| Re-enumerate slave | `hid_send_feature_report` | `7` | `2` | Report ID plus zero byte |

This validates the SDK's current live-mode status source: HID usage `0x103`,
feature report `3`.

Static strings from `EpiphanCaptureConfig.exe` show the configuration tool uses
`libusb` for device configuration, firmware update, EDID IO, user modes, and
device flags. Relevant strings:

- `Probe DVI2USB3/SDI2USB3/KVM2USB3`
- `getConfigDeviceData`
- `setConfigDeviceData`
- `Error retreiving config device data: req=%1, status: %2`
- `Can't initiate EDID IO access`
- `Can't finalize EDID IO access`
- `Can't send EDID data to the device`
- `EDID data has incorrect checksum`
- `EDID data has incorrect format`
- `updateUserModesButton`
- `onGetDeviceInputStatusComplete`
- `Flashing FX3 firmware...`

Mangled template names in `EpiphanCaptureConfig.exe` include request-like byte
values that should be treated as hypotheses until confirmed by USBPcap or static
disassembly:

| Observed symbol fragment | Possible meaning |
| --- | --- |
| `ConfigDeviceActionBaseI15InputStatusInfoLh178ELh0ELt0ELt0EE` | request `0xB2` may read input status |
| `ConfigDeviceActionBaseI8UserModeLh179ELh179ELt0ELt0EE` | request `0xB3` may read/write user mode |
| `ConfigDeviceActionBaseIhLh226ELh227ELt0ELt0EE` | requests `0xE2`/`0xE3` may read/write a byte-sized flag |

Linux `EpiphanCaptureConfig` disassembly upgrades several of those from
hypothesis to static-confirmed request IDs. The app uses
`libusb_control_transfer()` with vendor IN `bmRequestType=0xC0` for reads and
vendor OUT `bmRequestType=0x40` for writes.

| Path | Request | Direction | Notes |
| --- | ---: | --- | --- |
| `ConfigDeviceActionBase<InputStatusInfo,...>::request` | `0xB2` | IN | Reads input status through `requestConfigDeviceData<InputStatusInfo>()` |
| `ConfigDeviceActionBase<UserMode,...>::request/store` | `0xB3` | IN/OUT | Reads and writes user mode data |
| `ConfigDeviceActionBase<unsigned char,...>::request/store` | `0xE2` / `0xE3` | IN/OUT | Reads and writes a byte-sized flag |
| Firmware/update path | `0xC4`, `0xC5`, `0xD4` | IN/OUT | Flash-status and update/repair flow; high-risk |
| EDID/update IO path | `0xA0` | IN/OUT | Used with chunked write/read-verify transfer; high-risk for writes |

The recovered config data structures are now concrete enough for offline
parsing and read-only probe design:

- `InputStatusInfo` request `0xB2` includes source text at offset `0x00`,
  mode/status text at `0x0c`, a 32-bit little-endian refresh-rate value at
  `0x14` displayed as milli-Hz divided by `1000.0`, width/height at
  `0x18`/`0x1a`, and a progressive/interlaced flag at `0x1c`. The UI displays
  it with
  `%1 %2x%3%4@%5, %6` or `no signal`.
- `UserMode` request `0xB3` stores width and height as little-endian 16-bit
  values followed by a one-byte disabled flag. The UI iterates exactly three
  checkable user modes, uses width/height spinbox ranges of `0..65535`, and
  stores `disabled = !checked`.
- Device flags request `0xE2` returns one byte. The settings UI maps bit `0x02`
  to `Preserve aspect ratio`, bit `0x04` to `Performance mode`, and bit `0x10`
  to `Audio selector for multichannel inputs`; request `0xE3` writes the byte
  back.

The EDID/update transfer path is more specific than the early string scan
showed. The vendor tool initiates access with zero-length `0xC5`, writes chunks
with vendor-OUT `0xA0`, verifies each chunk by reading the same address back
with vendor-IN `0xA0`, caps chunks at `0x1000` bytes, splits the 32-bit address
as `wValue = low16(address)` and `wIndex = high16(address)`, validates an
accumulated 32-bit checksum, then sends a final zero-length `0xA0`. A helper
polls one byte of flash status using vendor-IN request `0xC4` or another
caller-supplied request byte, with `FPGA` and `FX3` used as status labels. This
is update/repair machinery, not yet a safe read-only EDID dump API.

The static analysis does not by itself authorize issuing raw USB requests. It
does identify the likely read-only MI_00 probe surface once the WinUSB config
interface is intentionally bound.

## Firmware Package Findings

The `.fw` file is a ZIP-style package containing:

| File | Size |
| --- | ---: |
| `edid.info` | 7 |
| `edid_kvm2usb3_uvc.edid` | 1002 |
| `fpga.info` | 5 |
| `kvm2usb3.bin` | 465028 |
| `kvm2usb3.img` | 240960 |
| `kvm2usb3-sandbox.img` | 202780 |
| `product.info` | 9 |
| `version.info` | 13 |

Firmware metadata:

| File | Value |
| --- | --- |
| `version.info` | `4.0.0-r39896` |
| `product.info` | `kvm2usb3` |
| `edid.info` | `r39807` |
| `fpga.info` | `r4895` |

The EDID file is a text-formatted hex dump. Parsed raw EDID bytes:

- Byte count: `256`
- Raw-byte SHA256:
  `9f8861146a7fd86ac2e5e833ad7945b4c82e7507c6500e28f33a497fe1b8ac5e`
- Block count: `2`
- Both block checksums are valid
- Manufacturer ID: `EPH`
- Product code: `13921`
- EDID version: `1.3`

Base-block detailed timings:

| Mode | Pixel clock |
| --- | ---: |
| `1920x1080 @ ~59.934 Hz` | `138.500 MHz` |
| `1280x720 @ ~59.979 Hz` | `64.000 MHz` |
| `1920x1200 @ ~59.950 Hz` | `154.000 MHz` |

## Reverse-Engineering Plan

1. Keep using HID usage `0x103`, feature report `3`, for live mode in the SDK.
2. Add a read-only WinUSB/libusb probe for MI_00 only after deciding how to bind
   the WinUSB driver safely. Driver installation is a host-state change and
   should be explicit.
3. Use USBPcap while running only read-only actions in `EpiphanCaptureConfig.exe`
   to confirm request IDs for input status, device flags, user modes, and any
   distinct EDID read path.
4. Treat EDID writes, firmware update, sandbox/repair mode, and unknown control
   writes as deferred high-risk work.
