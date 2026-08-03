# OpenKVM2USB Recovery And Recreation Strategy

Last reviewed: 2026-08-03

This repository is the public integration baseline for KVM2USB 3.0 host
operation and protocol recovery. The long-term program is an independently
reproducible open implementation across host software, USB protocols, FX3
firmware, GPIF II, and Spartan-6 FPGA logic.

Full recovery does not mean reconstructing Epiphan source code. The defensible
target is behavioral compatibility:

1. Recover observable behavior and protocols.
2. Recover enough low-level structure to understand the existing implementation.
3. Write independent, functionally compatible open source.
4. Produce reproducible builds.
5. Validate equivalence with automated tests and physical hardware.

## Completion Levels

| Level | Goal | Current position |
| --- | --- | --- |
| A | Open host replacement | Partly achieved. AgentKVM2USB uses UVC/HID for video/status/input without the Epiphan app. |
| B | Open protocol and driverless operation | In progress. HID and UVC are mapped; MI_00 vendor requests are partly mapped and should use WinUSB/libusb, not a custom kernel driver. |
| C | Open FX3 application firmware | Not started. First release may build against a locally installed proprietary Infineon FX3 SDK without redistributing the SDK. |
| D | Fully independent firmware and FPGA implementation | Research target. Spartan-6 still practically requires ISE 14.7 for place/route/bitgen. |

Default driver strategy: no custom kernel driver. Use operating-system UVC/HID
class drivers and WinUSB/libusb only for vendor-specific control interfaces.

## Repository Trust Zones

| Zone | Repository/store | Contents |
| --- | --- | --- |
| Public integration | `SemperSupra/AgentKVM2USB` | Host app, public protocol libraries, diagnostics, sanitized docs, tests, release packaging. No proprietary vendor binaries. |
| Private evidence vault | `SemperSupra/AgentKVM2USB-research-private` or encrypted object store | Vendor installers, firmware packages, extracted binaries, captures, photos, flash dumps, traces, restricted docs, chain-of-custody records. |
| Public clean implementation | `SemperSupra/OpenKVM2USB` | Clean host/protocol/fx3/fpga/hardware/tooling implementation that consumes only public docs, sanitized specs, test vectors, measurements, and facts. |

The clean implementation repository should use separate sessions or agents for
evidence analysis, specification writing, and implementation. Each session must
record which public specs and artifact hashes it was allowed to use.

Suggested `OpenKVM2USB` layout:

```text
OpenKVM2USB/
├── host/
├── protocol/
├── fx3/
├── fpga/
├── hardware/
├── tools/
├── environments/
├── manifests/
└── docs/
```

## Required Environments

| Environment | Purpose | Notes |
| --- | --- | --- |
| Windows host and hardware lab | Run AgentKVM2USB, original app in isolation, USBPcap/Wireshark, DirectShow/UVC/HID tests, portable packages, GPIF II Designer | Standardize on HIDAPI, UVC/OpenCV or Media Foundation, and libusb/WinUSB. |
| FX3 Windows VM | Install official EZ-USB FX3 SDK and GPIF II Designer | Snapshot immediately after install; record installer hashes, license, paths, toolchain, and sample build hashes. |
| Reproducible FX3 CLI build | Automated Linux/WSL/container builds from a local vendor cache | Do not publish images containing Infineon SDK files unless redistribution is explicitly permitted. |
| Xilinx ISE 14.7 VM | Spartan-6 build flow | Use ISE VM for `xst`, `ngdbuild`, `map`, `par`, `bitgen`, `promgen`, `impact`, `xdl`, and XDLRC. |
| FPGA reverse lab | Packet parsing, HAL/TORC/Yosys/Verilator/cocotb/SymbiYosys analysis | Project X-Ray is a process model, not a Spartan-6 database source. |

## Workstreams

| Workstream | Deliverables |
| --- | --- |
| Board and BOM recovery | Photos, component inventory, exact FPGA/FX3/flash markings, voltage rails, clocks, DDR topology, JTAG/UART, boot straps, FPGA-FX3 and video signal maps, partial KiCad schematic. |
| Behavioral and USB specification | Correlated captures for startup, status, HID, UVC, config requests, mode changes, and firmware update; machine-readable protocol specs backed by captures or public standards. |
| Host application reconstruction | Explicit backends for video, HID keyboard/mouse/touch, status, firmware; trace replay, simulator, descriptor fixtures, conformance tests, structured errors. |
| Firmware image recovery | Parse wrappers, checksums, load addresses, sections, descriptors, GPIF data, flash partitioning, and call graphs. Publish facts/specs, not decompiled code. |
| Open FX3 firmware | Composite descriptors, HID, UVC test source, explicit GPIF contract, safe RAM loading on dev board before KVM2USB hardware. |
| Spartan-6 bitstream recovery | Packet/frame parser, CRC verification, register writes, differential bit database, HAL netlist import, major functional-region identification. |
| Independent FPGA recreation | Clock/reset, GPIF loopback, color bars, registers, frame markers, DDR tests, video timing detection, one real mode, scaling/cropping, recovery. |

## Hardware Roles And Safety Gate

Use at least three devices:

| Unit | Role |
| --- | --- |
| Gold reference | Never written; behavioral comparison only. |
| Recovery unit | Read-only extraction and board tracing. |
| Sacrificial unit | RAM firmware, JTAG, flash, and recovery experiments. |

Before any write:

1. Identify every voltage domain.
2. Identify boot-mode pins.
3. Produce two independent flash dumps.
4. Confirm their hashes are identical.
5. Verify an external recovery method.
6. Preserve the gold unit.
7. Require an experiment record and explicit human approval.

## Milestones

| Milestone | Gate |
| --- | --- |
| 0 Packaging baseline | Resolve PR `#6`, preserve `v0.2.0`, and keep firmware scope out of that PR. |
| 1 Laboratory reproducibility | Vendor tools acquired/hashed, FX3 sample builds, ISE sample bitstream builds, HAL environment works, clean Windows VM works, evidence vault established. |
| 2 Behavioral specification | USB descriptors, HID reports, UVC formats, vendor requests, original app behavior, and replay fixtures documented. |
| 3 Open host stack | No vendor app, no custom kernel driver, Windows/Linux operation, conformance suite, long-running video/HID tests. |
| 4 Open FX3 firmware on dev hardware | Composite UVC/HID device enumerates, test frames stream, HID works, GPIF contract documented, RAM loading and recovery validated. |
| 5 FPGA understanding | Exact part/package known, parser complete, differential database started, functional regions identified, physical/logical FPGA-FX3 interface documented. |
| 6 Open FPGA test design | Test pattern reaches host through open FX3, DDR/frame pipeline works, one mode works, timing closes in ISE, reproducible bitstream produced. |
| 7 Complete open stack | Open host, protocol library, FX3 application firmware, FPGA RTL, public build docs, safe update/rollback, hardware validation. |

## Immediate Execution Order

1. Close out PR `#6` without adding new reverse-engineering scope.
2. Create the private evidence repository.
3. Create the public `OpenKVM2USB` repository and epic.
4. Add artifact, experiment, and environment schemas.
5. Acquire the FX3 SDK, ISE VM, and public documentation.
6. Verify one FX3 sample build and one XC6SLX16 sample bitstream.
7. Photograph and transcribe the complete FPGA and flash markings.
8. Inventory every known Epiphan binary by SHA256.
9. Capture original application USB behavior one operation at a time.
10. Add deterministic trace replay to this host application.
11. Develop replacement FX3 firmware on a development board.
12. Begin the Spartan-6 parser and differential mapping framework.
13. Do not write firmware or FPGA data to the gold reference unit.
14. Move to the sacrificial unit only after a verified recovery path exists.

## Licensing And Provenance Rules

- Work only on lawfully acquired devices.
- Preserve original binaries privately.
- Publish facts and specifications, not proprietary code.
- Do not redistribute AMD, Infineon, or Epiphan installers unless the license permits it.
- Use a new USB VID/PID for distributable replacement firmware.
- Maintain attribution and license manifests.
- Require DCO sign-off for contributions.
- Get legal review before publishing reconstructed firmware or FPGA artifacts.

Recommended starting licenses:

| Area | License |
| --- | --- |
| Host software and tools | Apache-2.0 or GPL-3.0 |
| Protocol specifications | CC BY 4.0 |
| FPGA RTL and hardware | CERN-OHL-S-2.0 |
| Test fixtures | Apache-2.0 unless they include restricted material |
