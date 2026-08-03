# Firmware And FPGA Update Recovery

Last reviewed: 2026-08-03

This document tracks offline recovery of Epiphan KVM2USB 3.0 firmware and FPGA
update support. It is intentionally scoped to static parsing and transfer-plan
generation. Do not use this as authorization to flash firmware, write EDID, or
send raw USB vendor control transfers to connected hardware.

Official package analyzed:

```text
firmware-kvm2usb3-uvc-4.0.0-r39896.fw
SHA256: 6a07699235aea25b00f601f13b5ef3fe5ec3e56237e9ef5b6c10939c15145039
```

## Package Files

| File | Role | SHA256 |
| --- | --- | --- |
| `kvm2usb3.img` | Main Cypress FX3/ThreadX firmware image | `97c1e45f1af12ff7187275547e690b3105abe21c0f6187b9e99e5cd674fb3f3a` |
| `kvm2usb3-sandbox.img` | Sandbox/repair Cypress FX3 firmware image | `f744a812c62208812392d9f085bbfe6f3184a3871c339e21487d6ab2e246e07d` |
| `kvm2usb3.bin` | FPGA bitstream payload | `0b917e5ba03ff745c5bb7d09aceec29d255bb72e7027a0fd65c49334e5533d8b` |
| `edid_kvm2usb3_uvc.edid` | Text EDID dump | `9f8861146a7fd86ac2e5e833ad7945b4c82e7507c6500e28f33a497fe1b8ac5e` for parsed raw bytes |

Metadata files:

| File | Value |
| --- | --- |
| `version.info` | `4.0.0-r39896` |
| `product.info` | `kvm2usb3` |
| `fpga.info` | `r4895` |
| `edid.info` | `r39807` |

## FX3 Image Container

The `.img` files use a Cypress FX3-style image container:

```text
0x00: "CY" signature
0x02: image control byte
0x03: image type byte
then repeated:
  uint32_le word_count
  uint32_le address
  word_count * 4 data bytes
terminator:
  uint32_le word_count == 0
  uint32_le entry_address
  uint32_le checksum
```

The checksum is the 32-bit sum of all little-endian data words across non-empty
records. The new `epiphan_firmware.py` parser validates this offline and can
produce request `0xA0` transfer chunks matching the vendor updater's address
split: `wValue = low16(address)`, `wIndex = high16(address)`.

Recovered real-image layout:

| Image | Control | Type | Records | 0x1000 chunks | Entry | Checksum |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| `kvm2usb3.img` | `0x1c` | `0xb0` | `6` | `61` | `0x4002a114` | `0x19fc6591` valid |
| `kvm2usb3-sandbox.img` | `0x1c` | `0xb0` | `5` | `51` | `0x400207a4` | `0x2f1dea7f` valid |

Main image records:

| Record | Address | Words | Bytes |
| ---: | ---: | ---: | ---: |
| 0 | `0x00000100` | `2082` | `8328` |
| 1 | `0x40003000` | `16384` | `65536` |
| 2 | `0x40013000` | `16384` | `65536` |
| 3 | `0x40023000` | `16384` | `65536` |
| 4 | `0x40033000` | `6187` | `24748` |
| 5 | `0x4004b000` | `2803` | `11212` |

Sandbox image records:

| Record | Address | Words | Bytes |
| ---: | ---: | ---: | ---: |
| 0 | `0x00000100` | `2082` | `8328` |
| 1 | `0x40003000` | `16384` | `65536` |
| 2 | `0x40013000` | `16384` | `65536` |
| 3 | `0x40023000` | `12108` | `48432` |
| 4 | `0x4004b000` | `3723` | `14892` |

## FPGA Bitstream

`kvm2usb3.bin` is not an FX3 image. It has 16 bytes of `0xff` preamble followed
by the Xilinx-style sync word:

```text
offset 0x10: 55 99 aa 66
```

The payload after the sync word begins with configuration command words such as
`0c8500e0`, `04008c85`, and `200c8c82`. The next recovery step is a Xilinx
Spartan-6 bitstream packet decoder that can distinguish header, configuration,
CRC, and desynchronization commands.

The file stores bit-reversed bytes. Reversing the bits in each byte normalizes
the sync word to canonical Xilinx `aa 99 55 66`. AMD packet documentation
describes Type 1 register packets with a 14-bit register field where only the
low five bits are used, and opcode `00` as NOOP. The firmware inspector now
emits first-pass packet counts, opcode counts, register counts, truncation
counts, and the first 16 decoded packet-like records without dumping frame
data.

Current real-payload first-pass summary:

| Field | Value |
| --- | --- |
| packet-like records | `134` |
| opcode counts | `nop=131`, `reserved=1`, `write=2` |
| packet type counts | `0=116`, `1=12`, `2=1`, `4=5` |
| truncated interpretations | `1` |
| first normalized header | `0x30a10007`, type-1 write to low-five-bit register `LOUT`, word count `7` |

The reserved packet type values and one truncated interpretation mean this is
bit-order and partial packet-framing recovery, not a complete Spartan-6 semantic
decode. Possibilities include a payload region that is not plain configuration
packets, an encapsulated stream, compression/encryption, or a remaining
Spartan-6-specific framing rule. Next step: cross-check against UG380 and TORC
before treating register names, CRC behavior, or frame payload boundaries as
authoritative.

## Vendor Update Sequence

Linux `EpiphanCaptureConfig` disassembly recovers the following update transfer
behavior:

| Step | Request | Direction | Notes |
| --- | ---: | --- | --- |
| Initiate access | `0xC5` | OUT `0x40` | Zero-length vendor OUT before transfer |
| FX3 chunk write | `0xA0` | OUT `0x40` | Chunk size capped at `0x1000` bytes |
| FX3 chunk verify | `0xA0` | IN `0xC0` | Same address and length read back and byte-compared |
| FX3 final/start | `0xA0` | OUT `0x40` | Zero-length transfer with entry address after checksum validation |
| Flash status | `0xC4` or supplied request | IN `0xC0` | One-byte polling helper; error labels include `FPGA` and `FX3` |
| Update/repair action | `0xD4` | OUT `0x40` | Zero-length vendor OUT with longer timeout |

Static strings show distinct stages for initiating repair, finding microcode,
starting microcode, flashing FX3 firmware, starting microcode reflash, finding
the FPGA image, flashing FPGA, writing FPGA header/block data, FPGA CRC checking,
and completing FPGA reflash. The exact FPGA write request sequence still needs
function-level disassembly and/or USBPcap against the official tool.

## Current Tooling Gap

The current WSL `objdump` cannot disassemble ARM binaries. To recover firmware
functions below the container level, use a prebuilt reverse-engineering image
with ARM support, such as a container including `binutils-arm-none-eabi`, Ghidra,
radare2, Capstone, and Kaitai Struct.

## Implementation Boundary

Implemented now:

- Offline FX3 image parsing and checksum validation.
- Offline FX3 transfer chunk planning.
- Offline FPGA bitstream sync-word detection.
- Offline Epiphan text EDID extraction and checksum validation.
- Offline firmware package inspection through
  `scripts/inspect_epiphan_firmware.py`.
- Unit tests for the recovered container formats.

Example:

```powershell
.venv\Scripts\python.exe scripts\inspect_epiphan_firmware.py `
  .work\epiphan-downloads\firmware-kvm2usb3-uvc-4.0.0-r39896.fw `
  --pretty
```

Deferred:

- Live update transport.
- FPGA write/CRC sequence implementation.
- Firmware signing or custom image generation.
- Any hardware write, repair-mode transition, or firmware start command.
