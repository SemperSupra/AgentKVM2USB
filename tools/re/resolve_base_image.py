#!/usr/bin/env python3
"""Resolve an official base image tag to an immutable digest and record it.

The digest is used as a recorded build input for the runner image (passed to
docker build via PYTHON_BASE_IMAGE). Resolution is automated so the digest is
never hard-coded by hand. Provenance records the source repository, requested
tag, resolved digest, architecture, and retrieval timestamp.

All Docker invocations go through the selected runtime adapter so the pinned
context/distribution is used.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import pathlib
import sys
from typing import Any

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from re_runtime import Adapter, read_runtime_json  # noqa: E402


def resolve_base_image(
    *,
    adapter: Adapter,
    image: str,
    output: pathlib.Path,
) -> dict[str, Any]:
    result = adapter.run(adapter.docker(["image", "inspect", image]), capture=True)
    if result.returncode != 0:
        # Pull the requested tag first so the digest reflects the current tag.
        pulled = adapter.run(adapter.docker(["pull", image]), capture=False)
        if pulled.returncode != 0:
            raise RuntimeError(f"docker pull {image} failed: {pulled.stderr.strip()[:200]}")
        result = adapter.run(adapter.docker(["image", "inspect", image]), capture=True)
        if result.returncode != 0:
            raise RuntimeError(f"docker image inspect {image} failed: {result.stderr.strip()[:200]}")
    data = json.loads(result.stdout)[0]
    repo_digests = data.get("RepoDigests") or []
    if not repo_digests:
        raise RuntimeError(f"no RepoDigests recorded for {image}")
    digest = repo_digests[0]
    record = {
        "schema_version": 1,
        "source_repository": digest.split("@", 1)[0],
        "requested_tag": image,
        "resolved_digest": digest,
        "architecture": data.get("Architecture"),
        "os": data.get("Os"),
        "image_id": data.get("Id"),
        "retrieved_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
    return record


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--image", required=True, help="base image tag, e.g. python:3.12-slim-bookworm")
    parser.add_argument("--output", required=True, type=pathlib.Path)
    parser.add_argument("--repo-root", default=str(pathlib.Path(__file__).resolve().parents[2]))
    parser.add_argument("--runtime-json", default=None)
    args = parser.parse_args()

    runtime_json = args.runtime_json or os.path.join(args.repo_root, ".work", "re", "runtime.json")
    selection = read_runtime_json(runtime_json)
    adapter = Adapter(selection, args.repo_root)
    record = resolve_base_image(adapter=adapter, image=args.image, output=args.output)
    # Print the immutable reference so the bootstrap can set PYTHON_BASE_IMAGE.
    print(record["resolved_digest"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
