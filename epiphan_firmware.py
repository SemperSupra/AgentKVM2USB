from __future__ import annotations

from dataclasses import dataclass
import hashlib
import re
from typing import Iterable


@dataclass(frozen=True)
class Fx3ImageRecord:
    address: int
    data: bytes

    @property
    def word_count(self) -> int:
        return len(self.data) // 4


@dataclass(frozen=True)
class Fx3TransferChunk:
    address: int
    data: bytes

    @property
    def w_value(self) -> int:
        return self.address & 0xFFFF

    @property
    def w_index(self) -> int:
        return (self.address >> 16) & 0xFFFF


@dataclass(frozen=True)
class Fx3Image:
    signature: bytes
    image_control: int
    image_type: int
    records: tuple[Fx3ImageRecord, ...]
    entry_address: int
    checksum: int
    calculated_checksum: int
    trailing_bytes: bytes
    sha256: str

    @property
    def checksum_valid(self) -> bool:
        return self.checksum == self.calculated_checksum

    def iter_transfer_chunks(self, max_chunk_size: int = 0x1000) -> Iterable[Fx3TransferChunk]:
        if max_chunk_size <= 0:
            raise ValueError("max_chunk_size must be positive")
        if max_chunk_size % 4:
            raise ValueError("max_chunk_size must be 32-bit word aligned")
        for record in self.records:
            for offset in range(0, len(record.data), max_chunk_size):
                yield Fx3TransferChunk(record.address + offset, record.data[offset:offset + max_chunk_size])


@dataclass(frozen=True)
class FpgaBitstream:
    sync_offset: int
    sync_word: bytes
    preamble: bytes
    payload: bytes
    sha256: str

    @property
    def has_sync_word(self) -> bool:
        return self.sync_offset >= 0


@dataclass(frozen=True)
class FpgaPacket:
    offset: int
    raw_word: int
    packet_type: int
    opcode: str
    register: int | None
    register_name: str | None
    word_count: int
    data_truncated: bool
    data_words_preview: tuple[int, ...]

    def as_dict(self) -> dict:
        return {
            "offset": self.offset,
            "raw_word": self.raw_word,
            "raw_word_hex": f"0x{self.raw_word:08x}",
            "packet_type": self.packet_type,
            "opcode": self.opcode,
            "register": self.register,
            "register_name": self.register_name,
            "word_count": self.word_count,
            "data_truncated": self.data_truncated,
            "data_words_preview": [f"0x{word:08x}" for word in self.data_words_preview],
        }


@dataclass(frozen=True)
class EdidSummary:
    raw: bytes
    sha256: str
    block_checksums: tuple[bool, ...]
    manufacturer_id: str
    product_code: int
    version: str
    monitor_name: str | None

    @property
    def block_count(self) -> int:
        return len(self.raw) // 128

    @property
    def checksums_valid(self) -> bool:
        return bool(self.block_checksums) and all(self.block_checksums)


def _read_u32le(data: bytes, offset: int) -> int:
    if offset + 4 > len(data):
        raise ValueError("unexpected end of FX3 image")
    return int.from_bytes(data[offset:offset + 4], "little")


_BIT_REVERSE_TABLE = bytes(int(f"{byte:08b}"[::-1], 2) for byte in range(256))

FPGA_PACKET_OPCODES = {
    0: "nop",
    1: "read",
    2: "write",
    3: "reserved",
}

FPGA_REGISTER_NAMES = {
    0x00: "CRC",
    0x01: "FAR",
    0x02: "FDRI",
    0x03: "FDRO",
    0x04: "CMD",
    0x05: "CTL",
    0x06: "MASK",
    0x07: "STAT",
    0x08: "LOUT",
    0x09: "COR1",
    0x0A: "COR2",
    0x0B: "PWRDN_REG",
    0x0C: "FLR",
    0x0D: "IDCODE",
    0x0E: "CWDT",
    0x10: "HC_OPT_REG",
    0x11: "CSBO",
    0x12: "GENERAL1",
    0x13: "GENERAL2",
    0x14: "GENERAL3",
    0x15: "GENERAL4",
    0x16: "GENERAL5",
    0x17: "MODE",
    0x18: "PU_GWE",
    0x19: "PU_GTS",
    0x1A: "MFWR",
    0x1B: "CCLK_FREQ",
    0x1C: "SEU_OPT",
    0x1D: "EXP_SIGN",
    0x1E: "RDBK_SIGN",
    0x1F: "BOOTSTS",
    0x20: "EYE_MASK",
    0x21: "CBC_REG",
}


def parse_fx3_image(data: bytes) -> Fx3Image:
    """Parse a Cypress FX3 image used by the Epiphan firmware package."""
    data = bytes(data)
    if len(data) < 16:
        raise ValueError("FX3 image is too small")
    if data[:2] != b"CY":
        raise ValueError("FX3 image signature must be 'CY'")

    records = []
    calculated_checksum = 0
    offset = 4

    while True:
        word_count = _read_u32le(data, offset)
        offset += 4
        address = _read_u32le(data, offset)
        offset += 4

        if word_count == 0:
            checksum = _read_u32le(data, offset)
            offset += 4
            return Fx3Image(
                signature=data[:2],
                image_control=data[2],
                image_type=data[3],
                records=tuple(records),
                entry_address=address,
                checksum=checksum,
                calculated_checksum=calculated_checksum & 0xFFFFFFFF,
                trailing_bytes=data[offset:],
                sha256=hashlib.sha256(data).hexdigest(),
            )

        byte_count = word_count * 4
        if offset + byte_count > len(data):
            raise ValueError("FX3 image record extends past end of data")
        chunk = data[offset:offset + byte_count]
        for pos in range(0, len(chunk), 4):
            calculated_checksum += int.from_bytes(chunk[pos:pos + 4], "little")
        records.append(Fx3ImageRecord(address=address, data=chunk))
        offset += byte_count


def parse_fpga_bitstream(data: bytes) -> FpgaBitstream:
    """Locate the Xilinx-style sync word in an Epiphan FPGA bitstream payload."""
    data = bytes(data)
    sync_words = (bytes.fromhex("55 99 aa 66"), bytes.fromhex("aa 99 55 66"))
    best_offset = -1
    best_word = b""
    for sync_word in sync_words:
        offset = data.find(sync_word)
        if offset >= 0 and (best_offset < 0 or offset < best_offset):
            best_offset = offset
            best_word = sync_word
    return FpgaBitstream(
        sync_offset=best_offset,
        sync_word=best_word,
        preamble=data[:best_offset] if best_offset >= 0 else data,
        payload=data[best_offset:] if best_offset >= 0 else b"",
        sha256=hashlib.sha256(data).hexdigest(),
    )


def normalize_fpga_payload(bitstream: FpgaBitstream) -> bytes:
    """Return canonical Xilinx packet bytes, reversing file byte bit order if needed."""
    if not bitstream.payload:
        return b""
    if bitstream.payload.startswith(bytes.fromhex("aa 99 55 66")):
        return bitstream.payload
    normalized = bytes(_BIT_REVERSE_TABLE[byte] for byte in bitstream.payload)
    if normalized.startswith(bytes.fromhex("aa 99 55 66")):
        return normalized
    return bitstream.payload


def iter_fpga_packets(
    bitstream: FpgaBitstream,
    *,
    max_packets: int | None = None,
    max_data_preview_words: int = 8,
) -> Iterable[FpgaPacket]:
    """Iterate canonical Xilinx configuration packets after the sync word."""
    payload = normalize_fpga_payload(bitstream)
    if len(payload) < 8:
        return
    offset = 4
    packets = 0
    last_register = None
    while offset + 4 <= len(payload):
        if max_packets is not None and packets >= max_packets:
            return
        raw_word = int.from_bytes(payload[offset:offset + 4], "big")
        offset += 4
        packet_type = (raw_word >> 29) & 0x7
        opcode_value = (raw_word >> 27) & 0x3
        opcode = FPGA_PACKET_OPCODES.get(opcode_value, f"unknown_{opcode_value}")
        register = None
        word_count = 0
        if packet_type == 1:
            register = (raw_word >> 13) & 0x3FFF
            word_count = raw_word & 0x7FF
            last_register = register
        elif packet_type == 2:
            register = last_register
            word_count = raw_word & 0x07FFFFFF
        else:
            word_count = 0
        if opcode == "nop":
            register = None

        requested_data_end = offset + word_count * 4
        data_truncated = requested_data_end > len(payload)
        data_end = min(requested_data_end, len(payload))
        preview = []
        for data_offset in range(offset, min(data_end, offset + max_data_preview_words * 4), 4):
            if data_offset + 4 <= len(payload):
                preview.append(int.from_bytes(payload[data_offset:data_offset + 4], "big"))
        yield FpgaPacket(
            offset=offset - 4,
            raw_word=raw_word,
            packet_type=packet_type,
            opcode=opcode,
            register=register,
            register_name=FPGA_REGISTER_NAMES.get(register) if register is not None else None,
            word_count=word_count,
            data_truncated=data_truncated,
            data_words_preview=tuple(preview),
        )
        packets += 1
        offset = data_end


def summarize_fpga_packets(bitstream: FpgaBitstream) -> dict:
    packets = list(iter_fpga_packets(bitstream))
    by_register = {}
    by_opcode = {}
    type_counts = {}
    total_data_words = 0
    truncated_packet_count = 0
    for packet in packets:
        type_counts[str(packet.packet_type)] = type_counts.get(str(packet.packet_type), 0) + 1
        by_opcode[packet.opcode] = by_opcode.get(packet.opcode, 0) + 1
        total_data_words += packet.word_count
        if packet.data_truncated:
            truncated_packet_count += 1
        if packet.register_name:
            by_register[packet.register_name] = by_register.get(packet.register_name, 0) + 1
    return {
        "packet_count": len(packets),
        "packet_type_counts": type_counts,
        "opcode_counts": by_opcode,
        "register_counts": by_register,
        "total_data_words": total_data_words,
        "truncated_packet_count": truncated_packet_count,
        "first_packets": [packet.as_dict() for packet in packets[:16]],
    }


def parse_epiphan_text_edid(data: bytes | str) -> bytes:
    """Extract raw EDID bytes from Epiphan's text-formatted EDID dump."""
    if isinstance(data, bytes):
        text = data.decode("ascii", errors="ignore")
    else:
        text = data
    values = []
    for line in text.splitlines():
        if "|" not in line:
            continue
        _addr, byte_text = line.split("|", 1)
        values.extend(int(match, 16) for match in re.findall(r"\b[0-9A-Fa-f]{2}\b", byte_text))
    return bytes(values)


def summarize_edid(raw: bytes) -> EdidSummary:
    raw = bytes(raw)
    if len(raw) < 128 or len(raw) % 128:
        raise ValueError("EDID byte length must be a non-zero multiple of 128")
    if raw[:8] != bytes.fromhex("00 ff ff ff ff ff ff 00"):
        raise ValueError("EDID header is invalid")

    manufacturer = ((raw[8] << 8) | raw[9])
    manufacturer_id = "".join(
        chr(((manufacturer >> shift) & 0x1F) + 0x40)
        for shift in (10, 5, 0)
    )
    monitor_name = None
    for offset in range(54, 126, 18):
        descriptor = raw[offset:offset + 18]
        if descriptor[:5] == b"\x00\x00\x00\xfc\x00":
            monitor_name = descriptor[5:18].split(b"\x0a", 1)[0].decode("ascii", errors="ignore").strip()
            break

    return EdidSummary(
        raw=raw,
        sha256=hashlib.sha256(raw).hexdigest(),
        block_checksums=tuple(sum(raw[offset:offset + 128]) % 256 == 0 for offset in range(0, len(raw), 128)),
        manufacturer_id=manufacturer_id,
        product_code=int.from_bytes(raw[10:12], "little"),
        version=f"{raw[18]}.{raw[19]}",
        monitor_name=monitor_name or None,
    )
