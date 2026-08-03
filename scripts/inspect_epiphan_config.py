from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from epiphan_config import parse_recovered_response, recovered_request_map


def parse_hex_payload(text: str) -> bytes:
    clean = text.replace("0x", "").replace(",", " ").replace(":", " ")
    return bytes(int(part, 16) for part in clean.split())


def main() -> int:
    parser = argparse.ArgumentParser(description="Inspect recovered Epiphan config request metadata offline.")
    parser.add_argument("--include-writes", action="store_true", help="Include high-risk write/update requests in output.")
    parser.add_argument("--parse", choices=["input_status", "user_mode", "device_flags"], help="Parse a hex payload.")
    parser.add_argument("--payload", help="Hex bytes to parse with --parse.")
    parser.add_argument("--pretty", action="store_true")
    args = parser.parse_args()

    if args.parse:
        if not args.payload:
            parser.error("--payload is required with --parse")
        result = parse_recovered_response(args.parse, parse_hex_payload(args.payload))
    else:
        result = recovered_request_map(include_writes=args.include_writes)
    print(json.dumps(result, indent=2 if args.pretty else None, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
