#!/usr/bin/env python3
"""Resolve mutable image tags to local immutable digests and record provenance."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import pathlib
import subprocess
from typing import Any

IMAGE_KEYS = (
    "RADARE2_IMAGE",
    "ANGR_IMAGE",
    "GHIDRA_IMAGE",
    "BINWALK_IMAGE",
    "RE_RUNNER_IMAGE",
    "SYFT_IMAGE",
    "TRIVY_IMAGE",
)


def parse_env(path: pathlib.Path) -> tuple[list[str], dict[str, str]]:
    lines = path.read_text(encoding="utf-8").splitlines()
    values: dict[str, str] = {}
    for line in lines:
        if not line or line.lstrip().startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip()
    return lines, values


def inspect_image(image: str) -> dict[str, Any]:
    result = subprocess.run(
        ["docker", "image", "inspect", image],
        check=True,
        text=True,
        stdout=subprocess.PIPE,
    )
    return json.loads(result.stdout)[0]


def local_locked_tag(image: str, image_id: str) -> str:
    """Create a stable local alias when a locally built image has no registry digest."""
    name = image.split("@", 1)[0]
    last_slash = name.rfind("/")
    last_colon = name.rfind(":")
    repository = name[:last_colon] if last_colon > last_slash else name
    short_id = image_id.removeprefix("sha256:")[:16]
    locked = f"{repository}:locked-{short_id}"
    subprocess.run(["docker", "image", "tag", image, locked], check=True)
    return locked


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--env-file", required=True, type=pathlib.Path)
    parser.add_argument("--output", required=True, type=pathlib.Path)
    parser.add_argument("--locked-env", required=True, type=pathlib.Path)
    args = parser.parse_args()

    lines, values = parse_env(args.env_file)
    records: list[dict[str, Any]] = []
    replacements: dict[str, str] = {}

    for key in IMAGE_KEYS:
        image = values.get(key)
        if not image:
            continue
        data = inspect_image(image)
        repo_digests = data.get("RepoDigests") or []
        image_id = data.get("Id", image)
        immutable = repo_digests[0] if repo_digests else local_locked_tag(image, image_id)
        replacements[key] = immutable
        records.append(
            {
                "variable": key,
                "requested": image,
                "immutable_reference": immutable,
                "image_id": image_id,
                "repo_digests": repo_digests,
                "created": data.get("Created"),
                "architecture": data.get("Architecture"),
                "os": data.get("Os"),
            }
        )

    output_lines: list[str] = []
    seen: set[str] = set()
    for line in lines:
        if "=" in line and not line.lstrip().startswith("#"):
            key = line.split("=", 1)[0].strip()
            if key in replacements:
                output_lines.append(f"{key}={replacements[key]}")
                seen.add(key)
                continue
        output_lines.append(line)
    for key, value in replacements.items():
        if key not in seen:
            output_lines.append(f"{key}={value}")
    args.locked_env.parent.mkdir(parents=True, exist_ok=True)
    args.locked_env.write_text("\n".join(output_lines) + "\n", encoding="utf-8")

    lock = {
        "schema_version": 1,
        "generated_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "images": records,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(lock, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
