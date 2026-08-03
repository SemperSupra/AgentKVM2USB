# Recovered Epiphan Capability Matrix

Last reviewed: 2026-08-02

This document tracks recovered functionality from official Epiphan KVM2USB 3.0
apps, drivers, and firmware. It separates static-confirmed facts from inferred
behavior and from hardware actions that remain deferred.

Official artifacts and hashes are recorded in `VENDOR_ARTIFACTS.md`. Reverse
engineering outputs are under ignored `.work/re-analysis/`.

## Current Recovery Status

| Area | Recovery status | Notes |
| --- | --- | --- |
| UVC video capture | Implemented | KVM2USB 3.0 exposes standard UVC; Windows DirectShow/OpenCV capture works at `1920x1080` YUY2/60 fps. |
| Live input signal/resolution | Implemented | HID usage `0x103`, feature report `3`, returns width, height, and active flag. |
| Keyboard injection | Implemented, static-confirmed | SDK now emits vendor report ID `1`, length `9`, with a legacy fallback. |
| Mouse injection | Implemented, static-confirmed, not live-validated | SDK emits vendor report ID `2`, length `5`, for relative movement, button, and wheel reports. |
| Touch injection | Implemented, static-confirmed | SDK now emits vendor report ID `5`, length `7`, with a legacy fallback. |
| Touch type selection | Implemented, static-confirmed, not live-validated | SDK exposes feature report `6`, length `2`; this is a write path. |
| Slave re-enumeration | Implemented, static-confirmed, not live-validated | SDK uses feature report `7`, length `2`; this is a write path. |
| Firmware version via HID | Implemented, static-confirmed, live-verified | Vendor app calls `hid_get_indexed_string(..., 3, ..., 0x100)` and converts the wide string to UTF-8. SDK exposes this as `get_firmware_version()` and in `get_status()`. Live unit returned `4.0.0.39896`. |
| Device discovery/selection | Recovered at function level | Vendor app has device model, scanner, selection, add/remove/close signals. |
| Input grab/release | Recovered at function level | Vendor app captures host keyboard/mouse, maps native keys to HID, clips/centers cursor, and toggles full screen. |
| Host hotkeys | Recovered at function level | Vendor app implements Ctrl+Alt+Del, Alt+Tab, Alt+Space, GUI key, full screen, and host action registry. |
| Image export/clipboard/print | Recovered at app level | Vendor app can copy/export/print current image and print preview. |
| Configuration tool launch | Recovered at app level | KVM app launches `EpiphanCaptureConfig`. |
| User modes | Static-confirmed request, structure, and UI semantics | Config tool reads/writes three 5-byte user modes with request `0xB3` through MI_00. Each mode has width, height, and disabled byte fields. |
| Input status via config interface | Static-confirmed request and parser | Config tool reads request `0xB2`; SDK has an offline parser for the recovered payload shape. |
| Device flags/settings | Static-confirmed request, bit map, and UI labels | Config tool uses request `0xE2` read and `0xE3` write for byte-sized flags; recovered bits are preserve aspect ratio, performance mode, and multichannel audio selector. |
| EDID validation | Recovered at app level | Config tool parses EDID, checks format/checksum, and reports empty/invalid EDID. |
| EDID/update transfer | Static-confirmed request family | Config tool uses request `0xA0` for chunked write/read-verify image transfer. This path overlaps update/repair behavior, so live writes are high-risk. |
| Firmware update/repair | Partially recovered with offline parser | Config tool supports soft/hard repair, firmware package parsing, flash-status polling, FX3 and FPGA flashing. `epiphan_firmware.py` now parses FX3 images, validates checksums, and plans chunks offline. Live implementation remains deferred high-risk work. |
| Firmware package EDID | Parsed and tool-supported | Package includes validated `EPH` EDID with 1920x1080, 1280x720, and 1920x1200 detailed timings. `scripts/inspect_epiphan_firmware.py` extracts EDID summary fields offline. |
| FPGA package payload | Partially parsed | `kvm2usb3.bin` has a Xilinx-style sync word `55 99 aa 66` at offset `0x10`; packet-level decoding remains open. |
| Firmware internals | Initial static inventory | Main firmware image includes ThreadX, Cypress FX3, UVC, HID master/slave, FPGA streaming, ADV7611 audio, EDID, user modes, VESA modes, I2C, SPI storage, GPIF, DMA, LED, and board services. |

## KVM App Function Inventory

The Linux AppImage preserves product-level C++ names. The relevant KVM app
classes and functions are:

| Class | Recovered functions/capabilities |
| --- | --- |
| `KvmDevice` | `open`, `getVideoFrame`, `getSizeReport`, `getFirmwareVersion`, `sendKeyboardReport`, `sendMouseReport`, `sendTouchReport`, `sendTouchTypeReport`, `sendReenumerateSlaveReport` |
| `HidApiKvmDevice` | HID-backed implementation of open, video-frame retrieval, size/status feature read, USB string descriptor firmware version, keyboard, mouse, touch, touch type, and re-enumeration |
| `HidApiV4l2KvmDevice` | Linux V4L2 video plus hidapi control implementation with the same KVM report methods |
| `V4l2KvmDevice` | Linux V4L2 device open, video frame, size report, keyboard, mouse, touch, and touch type paths |
| `KvmController` | Device scanning/selection, device add/remove/close signals, frame signal, input resolution signal, and report forwarding |
| `KvmWorker` | Scanning, device selection, frame callback, input-size polling, and report forwarding |
| `KvmVideo` | Video thread/run loop and frame callback |
| `KvmWidget` | Frame drawing, keyboard/mouse/touch event processing, input grab/release, cursor clipping/centering, host key handling, full screen toggle, mouse emulation options |
| `KvmMainWindow` | Device activation/list/dialog, UI setup/update, status bar, settings save/restore, image copy/export/print, full screen, host hotkeys, config-tool launch |
| `DeviceListModel` / `DeviceListDialog` | Device table model, add/remove/clear, selection dialog, connect action |
| `UpdateChecker` | Firmware/software update check and download workflow |

The app also contains native key maps for Windows, macOS, and Linux evdev:
`WIN_NATIVE_TO_HID`, `MAC_NATIVE_TO_HID`, and `EVDEV_NATIVE_TO_HID`.

## HID Reports

Linux `KvmApp` disassembly confirms:

| Operation | HID API | Report ID | Length | Payload |
| --- | --- | ---: | ---: | --- |
| Keyboard output | `hid_write` | `1` | `9` | Report ID plus 8-byte keyboard report |
| Mouse output | `hid_write` | `2` | `5` | Report ID plus 4-byte mouse report |
| Touch output | `hid_write` | `5` | `7` | Report ID plus 4-byte touch report and 2-byte contact/type field |
| Input size/status | `hid_get_feature_report` | `3` | `6` | Report ID plus `width_le16`, `height_le16`, active flag |
| Touch type | `hid_send_feature_report` | `6` | `2` | Report ID plus 1-byte touch type |
| Re-enumerate slave | `hid_send_feature_report` | `7` | `2` | Report ID plus zero byte |

Only the read-only input size/status report should be considered fully safe by
default. Output reports should be validated only on a sacrificial target or safe
firmware screen. Feature writes are deferred unless explicitly approved.

Touch reports follow the vendor app's 6-byte payload. The first payload byte is
ORed with `0x02` before send, which matches the USB digitizer pattern of keeping
the pointer in range while using bit `0x01` for contact. The SDK press report is
`[5, flags|0x02, x_lo, x_hi, y_lo, y_hi, 0]`; release clears contact while
keeping the final coordinates.

Firmware/version display is separate from the report table. `HidApiKvmDevice`
uses `hid_get_indexed_string()` with string index `3` and a `0x100` wide-character
buffer, then converts the result to a regular string. The connected unit returned
`4.0.0.39896`.

## Capture Configuration Tool

The Linux `EpiphanCaptureConfig` binary exposes a compact configuration stack:

| Class | Recovered functions/capabilities |
| --- | --- |
| `DeviceScanner` | USB device scan, new-device event, scan completion, scan error |
| `ConfigDeviceTask` | Base configuration task object |
| `ConfigDeviceAction` | Initializes libusb config action and owns request execution |
| `ConfigDeviceBase` | `getConfigDeviceData`, `setConfigDeviceData`, request-complete signals, error filtering |
| `ConfigDeviceActionBase<InputStatusInfo, 0xB2, 0x00>` | Input-status read path |
| `ConfigDeviceActionBase<UserMode, 0xB3, 0xB3>` | User-mode read/write path |
| `ConfigDeviceActionBase<unsigned char, 0xE2, 0xE3>` | Byte-sized device flag read/write path |
| `UpdateRepair` | Device scan/list, input-status timer, user-mode widgets/store, settings request, update button, settings button, firmware file selection, soft/hard repair UI |
| `UpdateTask` | Firmware package open, progress, error, complete, FX3 and FPGA update paths |
| `Zip` / `ZipFile` / `ZipStat` | Firmware `.fw` ZIP package open, stat, read, CRC/name/size validation |
| `parse_edid(std::istream&)` | EDID text parser and validator |

Confirmed libusb request shape:

| Request | Direction | Recovered use |
| ---: | --- | --- |
| `0xB2` | vendor IN `0xC0` | Input status |
| `0xB3` | vendor IN/OUT `0xC0`/`0x40` | User mode read/write |
| `0xE2` | vendor IN `0xC0` | Byte-sized flag read |
| `0xE3` | vendor OUT `0x40` | Byte-sized flag write |
| `0xA0` | vendor IN/OUT `0xC0`/`0x40` | Chunked image/EDID transfer with write/read-verify behavior |
| `0xC4` | vendor IN `0xC0` | One-byte update flash-status polling helper |
| `0xC5` | vendor OUT `0x40` | Update/repair flow |
| `0xD4` | vendor OUT `0x40` | Update/repair flow |

The static analysis is enough to design a read-only probe, but not enough to run
unknown USB writes safely.

Recovered structures:

| Structure | Offset | Field | Notes |
| --- | ---: | --- | --- |
| `InputStatusInfo` | `0x00` | source string | Null-terminated ASCII-ish text; falls back to `unknown` in the UI |
| `InputStatusInfo` | `0x0c` | mode/status string | Null-terminated text; falls back to `unknown` |
| `InputStatusInfo` | `0x14` | refresh rate | 32-bit little-endian milli-Hz value displayed after division by `1000.0` |
| `InputStatusInfo` | `0x18` | width | 16-bit little-endian; non-zero required for active signal |
| `InputStatusInfo` | `0x1a` | height | 16-bit little-endian; non-zero required for active signal |
| `InputStatusInfo` | `0x1c` | scan flag | Live HDMI `1920x1080` status returns `0x00`; parser preserves this as `scan_flag_raw` and currently interprets `0` as progressive. Confirm against additional modes. |
| `UserMode` | `0x00` | width | 16-bit little-endian; UI spinbox range `0..65535` |
| `UserMode` | `0x02` | height | 16-bit little-endian; UI spinbox range `0..65535` |
| `UserMode` | `0x04` | disabled flag | One byte; the UI has three checkable user-mode group boxes and stores `disabled = !checked` |
| device flags | `0x00` | flags byte | `0x02` preserve aspect ratio, `0x04` performance mode, `0x10` audio selector for multichannel inputs |

The `InputStatusInfo` UI label format string is
`%1 %2x%3%4@%5, %6`; invalid or zero-size status displays `no signal`.

The SDK currently implements offline parsers/builders for the recovered config
payloads: `parse_config_input_status()`, `parse_config_flags()`,
`build_config_flags()`, `parse_config_user_mode()`, and
`build_config_user_mode()`. It intentionally does not issue MI_00 USB control
requests yet.

`epiphan_config.py` and `scripts/inspect_epiphan_config.py` expose the recovered
MI_00 request map and payload parser dispatch in machine-consumable form. Write
and update requests are represented as metadata only.

`mi00_probe.py` and `scripts/probe_mi00_config.py` add the guarded live-probe
surface for blocker 1. The probe is read-only by construction: it exposes only
static-confirmed vendor IN requests `0xB2`, `0xB3`, and `0xE2`, requires
`--execute-read-only` before issuing a transfer, and has no implementation path
for vendor OUT, firmware update, EDID write, or FPGA write requests.

The read-only path is now integrated for application use:

| Surface | Behavior |
| --- | --- |
| `EpiphanKVM_SDK.get_config_status()` | One-shot MI_00 read-only status with failure-as-data output |
| `EpiphanKVM_SDK.get_device_health(include_mi00=True)` | Adds MI_00 details to the structured health model only when explicitly requested |
| `hardware_probe.py --include-mi00` | Includes MI_00 source, mode, refresh, flags, and user-mode data in the diagnostic JSON |
| GUI Tools -> Read Config Status | Performs one on-demand read-only query and displays the parsed result |

First live read-only MI_00 probe after official WinUSB INF binding:

| Request | Payload | Parsed result |
| --- | --- | --- |
| `0xB2` input status | `52 47 42 00 00 00 00 00 00 00 00 00 48 44 4d 49 00 00 00 00 a4 ea 00 00 80 07 38 04 00` | `RGB`, mode `HDMI`, `1920x1080`, active, refresh approximately `60.068 Hz` |
| `0xE2` device flags | `fe` | preserve aspect ratio, performance mode, and multichannel audio bits set; high bits still unmapped |
| `0xB3` user mode | `ff ff ff ff ff` | disabled sentinel for tested `wValue`/`wIndex` values `0..2` |

Recovered update transfer behavior:

| Step | Request | Direction | Details |
| --- | ---: | --- | --- |
| Initiate access | `0xC5` | OUT | Zero-length vendor OUT observed before the transfer path |
| Chunk write | `0xA0` | OUT | Address split as `wValue = low16(address)`, `wIndex = high16(address)`, chunk size capped at `0x1000` bytes |
| Chunk verify | `0xA0` | IN | Reads the same address/length back and compares every byte |
| Final/start | `0xA0` | OUT | Zero-length transfer with final address after checksum validation |
| Flash status | `0xC4` or supplied byte | IN | One-byte polling helper with `FPGA`/`FX3` labels used in error messages |
| Update/repair action | `0xD4` | OUT | Zero-length vendor OUT with longer timeout in update/repair flow |

This path is treated as write/update behavior, not as a safe EDID read API,
until USBPcap confirms an official read-only configuration-tool operation.

## Driver And Access Layer

| Platform/package | Scope | Relevance |
| --- | --- | --- |
| Windows KVM app `epiphan_avio_series.inf` | Installs WinUSB for config devices | Relevant to KVM2USB 3.0 MI_00 config access |
| Linux AppImage `99-usbkvm.rules` | Grants `plugdev` access to USB/hidraw | Relevant to Linux user-space KVM app access |
| Windows legacy `epiphan64.inf` / `epiphan.inf` | Installs `vga2usb.sys` and `vga2pcie.sys` for VID_5555-era devices | Not the normal KVM2USB 3.0 UVC/HID path |

KVM2USB 3.0 normal mode IDs from the WinUSB INF:

| Mode | ID |
| --- | --- |
| Configuration | `VID_2B77&PID_3661&MI_00` |
| Sandbox | `VID_2B77&PID_366F` |
| Repair | `VID_2B77&PID_3660` |

The legacy driver package targets older IDs such as `VID_5555&PID_1120` for
older KVM2USB hardware and `VID_04B4&PID_8613` for a firmware-loader device. It
also registers Windows Kernel Streaming capture/audio interfaces for legacy
VGA2USB/VGA2PCIe-class devices.

## Firmware Package

The official `.fw` package contains:

| File | Recovered role |
| --- | --- |
| `version.info` | Package version `4.0.0-r39896` |
| `product.info` | Product `kvm2usb3` |
| `edid.info` | EDID revision `r39807` |
| `fpga.info` | FPGA revision `r4895` |
| `edid_kvm2usb3_uvc.edid` | Text hex EDID dump |
| `kvm2usb3.bin` | FPGA or microcode payload; low-string-density data |
| `kvm2usb3.img` | Main FX3/ThreadX firmware image |
| `kvm2usb3-sandbox.img` | Sandbox/repair-oriented firmware image |

See `FIRMWARE_UPDATE_RECOVERY.md` for FX3 record tables, checksums, transfer
chunk counts, and FPGA bitstream notes.

Static firmware strings identify these components:

| Component | Evidence |
| --- | --- |
| RTOS | ThreadX ARM9/RVDS string |
| USB controller | Cypress FX3 strings, `cyfxtx.cpp`, `CYWBFX3B` |
| USB request handling | `STANDARD_RQT`, `CLASS_RQT`, `VENDOR_RQT`, request targets |
| UVC | `UvcBase.cpp`, `UvcFunction.cpp`, `StreamingStopThread` |
| HID | `KvmHidFunction.cpp`, `KvmHidMaster`, `KvmHidSlave` |
| Video pipeline | `AutoDetectInputThread`, `StreamingFromFPGAThread`, `abstractvideograbber.cpp`, `abstractscaler.cpp`, `vesamodes.c` |
| FPGA path | `FpgaUsbThread`, `FpgaUsbIsrThread`, `FpgaProg`, `fpgastreamer.cpp`, `FpgaMonitor` |
| Audio | `AV.io HDMI Audio`, `Audio input`, `ADV7611(Audio)`, `abstractaudiograbber.cpp`, `abstractfpgaaudiochip.cpp` |
| EDID | `edid.cpp`, firmware-packaged EDID |
| User modes | `usermodes.cpp` |
| Board/control | `BoardServices.cpp`, `led.cpp`, `LedThread`, `gpio.cpp`, `i2c.cpp`, `spi_store.cpp`, `dmachannel.cpp`, `gpif.c` |

## Remaining Gaps

| Gap | Next static step | Hardware-safe dynamic step |
| --- | --- | --- |
| User-mode live values | Compare current device user-mode records to recovered parser | Read-only MI_00 request `0xB3` after WinUSB binding approval |
| Input-status live comparison | Validate recovered parser against real `0xB2` bytes | Compare read-only `0xB2` result with HID report `3` |
| Device-flag live values | Compare current device flag byte to recovered bit parser | Read-only `0xE2` only after WinUSB binding approval |
| EDID read-only path | Determine whether the official tool has a separate safe EDID read operation | USBPcap-confirmed read-only EDID dump after WinUSB binding approval |
| Firmware update protocol | Continue static analysis only | Keep writes deferred |
| Firmware architecture map | Identify CPU/loader format and segment boundaries for `.img` files | No hardware action needed |
