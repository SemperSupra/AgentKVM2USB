from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from epiphan_config import recovered_request_map
from mi00_probe import Mi00ProbeError, find_device, probe_summary, read_config_request


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Guarded read-only probe for the KVM2USB 3.0 MI_00 config interface."
    )
    parser.add_argument("--list", action="store_true", help="List detected device/interface metadata only.")
    parser.add_argument(
        "--read",
        choices=["input_status", "user_mode", "device_flags"],
        help="Run one static-confirmed read-only vendor IN request.",
    )
    parser.add_argument("--w-value", type=lambda text: int(text, 0), default=0)
    parser.add_argument("--w-index", type=lambda text: int(text, 0), default=0)
    parser.add_argument("--timeout-ms", type=int, default=1000)
    parser.add_argument("--libusb-dll", help="Optional explicit libusb-1.0.dll path.")
    parser.add_argument(
        "--execute-read-only",
        action="store_true",
        help="Required for --read. The tool never sends write/update requests.",
    )
    parser.add_argument("--request-map", action="store_true", help="Print the safe read-only request map.")
    parser.add_argument("--pretty", action="store_true")
    args = parser.parse_args()

    try:
        if args.request_map:
            result = recovered_request_map(include_writes=False)
        elif args.read:
            if not args.execute_read_only:
                parser.error("--execute-read-only is required with --read")
            dev = find_device(libusb_dll=args.libusb_dll)
            if dev is None:
                result = {"found": False, "error": "KVM2USB 3.0 USB device not found"}
            else:
                result = read_config_request(
                    dev,
                    args.read,
                    w_value=args.w_value,
                    w_index=args.w_index,
                    timeout_ms=args.timeout_ms,
                ).as_dict()
        else:
            result = probe_summary(libusb_dll=args.libusb_dll)
    except Mi00ProbeError as exc:
        result = {"error": str(exc)}
        print(json.dumps(result, indent=2 if args.pretty else None, sort_keys=True))
        return 2

    print(json.dumps(result, indent=2 if args.pretty else None, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
