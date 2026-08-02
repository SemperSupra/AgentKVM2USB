from __future__ import annotations

from dataclasses import dataclass
import hashlib
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


def _read_u32le(data: bytes, offset: int) -> int:
    if offset + 4 > len(data):
        raise ValueError("unexpected end of FX3 image")
    return int.from_bytes(data[offset:offset + 4], "little")


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
