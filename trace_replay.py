from __future__ import annotations

import json
from pathlib import Path
from typing import Iterator


class TraceReplay:
    """Reads deterministic experiment directories for no-hardware replay."""

    def __init__(self, experiment_dir: str | Path):
        self.experiment_dir = Path(experiment_dir)

    def read_json(self, name: str) -> dict:
        path = self.experiment_dir / name
        with path.open("r", encoding="utf-8") as handle:
            return json.load(handle)

    def iter_jsonl(self, name: str = "host-log.jsonl") -> Iterator[dict]:
        path = self.experiment_dir / name
        with path.open("r", encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if line:
                    yield json.loads(line)

    def descriptor_summary(self) -> dict:
        descriptors = self.read_json("descriptors.json")
        if "vid" in descriptors or "pid" in descriptors:
            return {
                "vid": _hex_string(descriptors.get("vid")),
                "pid": _hex_string(descriptors.get("pid")),
                "manufacturer": descriptors.get("manufacturer"),
                "product": descriptors.get("product"),
                "interface_count": len(descriptors.get("interfaces", [])),
            }
        device = descriptors.get("device", {})
        interfaces = []
        for configuration in descriptors.get("configurations", []):
            interfaces.extend(configuration.get("interfaces", []))
        return {
            "vid": device.get("vid"),
            "pid": device.get("pid"),
            "manufacturer": device.get("manufacturer"),
            "product": device.get("product"),
            "interface_count": len(interfaces),
        }

    def device_status(self) -> dict:
        return self.read_json("device-status.json")

    def mi00_status(self) -> dict:
        return self.read_json("mi00-status.json")


def _hex_string(value) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        return value
    return f"{int(value):04x}"
