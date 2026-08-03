from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from epiphan_firmware import (
    parse_epiphan_text_edid,
    parse_fpga_bitstream,
    parse_fx3_image,
    summarize_edid,
)


FX3_IMAGE_NAMES = {"kvm2usb3.img", "kvm2usb3-sandbox.img"}
FPGA_IMAGE_NAMES = {"kvm2usb3.bin"}


def inspect_payload(name: str, data: bytes) -> dict:
    base = {
        "name": name,
        "size": len(data),
    }
    if name in FX3_IMAGE_NAMES or data.startswith(b"CY"):
        image = parse_fx3_image(data)
        base.update(
            {
                "kind": "fx3_image",
                "sha256": image.sha256,
                "image_control": image.image_control,
                "image_type": image.image_type,
                "record_count": len(image.records),
                "transfer_chunk_count": len(list(image.iter_transfer_chunks())),
                "entry_address": image.entry_address,
                "checksum": image.checksum,
                "calculated_checksum": image.calculated_checksum,
                "checksum_valid": image.checksum_valid,
                "records": [
                    {
                        "address": record.address,
                        "word_count": record.word_count,
                        "byte_count": len(record.data),
                    }
                    for record in image.records
                ],
            }
        )
    elif name in FPGA_IMAGE_NAMES:
        bitstream = parse_fpga_bitstream(data)
        base.update(
            {
                "kind": "fpga_bitstream",
                "sha256": bitstream.sha256,
                "sync_offset": bitstream.sync_offset,
                "sync_word": bitstream.sync_word.hex(),
                "preamble_size": len(bitstream.preamble),
                "payload_size": len(bitstream.payload),
            }
        )
    elif name.endswith(".edid"):
        edid = summarize_edid(parse_epiphan_text_edid(data))
        base.update(
            {
                "kind": "edid_text_dump",
                "sha256": edid.sha256,
                "raw_size": len(edid.raw),
                "block_count": edid.block_count,
                "block_checksums": list(edid.block_checksums),
                "checksums_valid": edid.checksums_valid,
                "manufacturer_id": edid.manufacturer_id,
                "product_code": edid.product_code,
                "version": edid.version,
                "monitor_name": edid.monitor_name,
            }
        )
    elif name.endswith(".info"):
        base.update(
            {
                "kind": "package_metadata",
                "value": data.decode("ascii", errors="ignore").strip(),
            }
        )
    else:
        base["kind"] = "unknown"
    return base


def inspect_path(path: Path) -> dict:
    if zipfile.is_zipfile(path):
        entries = []
        with zipfile.ZipFile(path) as archive:
            for info in sorted(archive.infolist(), key=lambda item: item.filename):
                if info.is_dir():
                    continue
                data = archive.read(info.filename)
                entry = inspect_payload(Path(info.filename).name, data)
                entry["archive_path"] = info.filename
                entries.append(entry)
        return {
            "path": str(path),
            "kind": "firmware_package",
            "entries": entries,
        }
    return {
        "path": str(path),
        **inspect_payload(path.name, path.read_bytes()),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Inspect Epiphan firmware artifacts offline.")
    parser.add_argument("paths", nargs="+", type=Path)
    parser.add_argument("--pretty", action="store_true", help="Pretty-print JSON output.")
    args = parser.parse_args()

    results = [inspect_path(path) for path in args.paths]
    print(json.dumps(results, indent=2 if args.pretty else None, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
