from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from trace_replay import TraceReplay


def main() -> int:
    parser = argparse.ArgumentParser(description="Summarize an AgentKVM2USB experiment trace directory.")
    parser.add_argument("experiment_dir", type=Path)
    parser.add_argument("--pretty", action="store_true")
    args = parser.parse_args()

    replay = TraceReplay(args.experiment_dir)
    host_events = list(replay.iter_jsonl()) if (args.experiment_dir / "host-log.jsonl").exists() else []
    result = {
        "experiment_dir": str(args.experiment_dir),
        "descriptors": replay.descriptor_summary() if (args.experiment_dir / "descriptors.json").exists() else None,
        "device_status": replay.device_status() if (args.experiment_dir / "device-status.json").exists() else None,
        "host_event_count": len(host_events),
        "host_event_types": sorted({event.get("event") or event.get("type") for event in host_events if event.get("event") or event.get("type")}),
    }
    print(json.dumps(result, indent=2 if args.pretty else None, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
