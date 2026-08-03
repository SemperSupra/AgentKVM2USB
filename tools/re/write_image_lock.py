#!/usr/bin/env python3
"""Resolve mutable image tags to local immutable digests and record provenance.

Every Docker invocation goes through the selected runtime adapter so the
recorded Docker Desktop context (or WSL distribution) is always used — an
unqualified direct ``docker`` call would bypass the pinned context. Provenance
includes the selected runtime, context/distribution, endpoint, versions, server
OS, Compose version, a SHA-256 of ``.work/re/runtime.json``, and both the
runtime-selection and image-lock timestamps.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import pathlib
import sys
from typing import Any

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from re_runtime import Adapter, read_runtime_json  # noqa: E402

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


def inspect_image(adapter: Adapter, image: str) -> dict[str, Any]:
    result = adapter.run(adapter.docker(["image", "inspect", image]), capture=True)
    if result.returncode != 0:
        raise RuntimeError(f"docker image inspect {image} failed: {result.stderr.strip()[:200]}")
    return json.loads(result.stdout)[0]


def local_locked_tag(adapter: Adapter, image: str, image_id: str) -> str:
    """Create a stable local alias when a locally built image has no registry digest."""
    name = image.split("@", 1)[0]
    last_slash = name.rfind("/")
    last_colon = name.rfind(":")
    repository = name[:last_colon] if last_colon > last_slash else name
    short_id = image_id.removeprefix("sha256:")[:16]
    locked = f"{repository}:locked-{short_id}"
    result = adapter.run(adapter.docker(["image", "tag", image, locked]), capture=True)
    if result.returncode != 0:
        raise RuntimeError(f"docker image tag {image} {locked} failed: {result.stderr.strip()[:200]}")
    return locked


def sha256_of_file(path: str) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def build_runtime_provenance(selection: dict[str, Any], runtime_json_path: str) -> dict[str, Any]:
    meta = selection.get("metadata") or {}
    return {
        "selected_runtime": selection.get("selected_runtime"),
        "requested_runtime": selection.get("requested_runtime"),
        "context": meta.get("context"),
        "endpoint": meta.get("endpoint"),
        "wsl_distribution": meta.get("wsl_distribution"),
        "wsl_version": meta.get("wsl_version"),
        "client_version": meta.get("client_version"),
        "server_version": meta.get("server_version"),
        "server_os": meta.get("server_os"),
        "compose_version": meta.get("compose_version"),
        "runtime_json_sha256": sha256_of_file(runtime_json_path) if os.path.isfile(runtime_json_path) else None,
        "runtime_selection_timestamp": selection.get("generated_utc"),
        "image_lock_generated_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
    }


def write_image_lock(
    *,
    env_file: pathlib.Path,
    locked_env: pathlib.Path,
    output: pathlib.Path,
    repo_root: str,
    runtime_json: str,
    adapter: Adapter | None = None,
) -> dict[str, Any]:
    if adapter is None:
        selection = read_runtime_json(runtime_json)
        adapter = Adapter(selection, repo_root)
    else:
        selection = adapter.selection

    lines, values = parse_env(env_file)
    records: list[dict[str, Any]] = []
    replacements: dict[str, str] = {}

    for key in IMAGE_KEYS:
        image = values.get(key)
        if not image:
            continue
        data = inspect_image(adapter, image)
        repo_digests = data.get("RepoDigests") or []
        image_id = data.get("Id", image)
        immutable = repo_digests[0] if repo_digests else local_locked_tag(adapter, image, image_id)
        replacements[key] = immutable
        records.append(
            {
                "variable": key,
                "requested_tag": image,
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
    locked_env.parent.mkdir(parents=True, exist_ok=True)
    locked_env.write_text("\n".join(output_lines) + "\n", encoding="utf-8")

    lock = {
        "schema_version": 2,
        "runtime": build_runtime_provenance(selection, runtime_json),
        "images": records,
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(lock, indent=2) + "\n", encoding="utf-8")
    return lock


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--env-file", required=True, type=pathlib.Path)
    parser.add_argument("--output", required=True, type=pathlib.Path)
    parser.add_argument("--locked-env", required=True, type=pathlib.Path)
    parser.add_argument("--repo-root", default=str(pathlib.Path(__file__).resolve().parents[2]))
    parser.add_argument("--runtime-json", default=None)
    args = parser.parse_args()

    runtime_json = args.runtime_json or os.path.join(
        args.repo_root, ".work", "re", "runtime.json"
    )
    write_image_lock(
        env_file=args.env_file,
        locked_env=args.locked_env,
        output=args.output,
        repo_root=args.repo_root,
        runtime_json=runtime_json,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
