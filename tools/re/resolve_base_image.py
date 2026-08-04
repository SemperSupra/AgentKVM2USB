#!/usr/bin/env python3
"""Resolve an official base image tag to an immutable digest and record it.

The digest is used as a recorded build input for the runner image (passed to
docker build via PYTHON_BASE_IMAGE). Resolution is automated so the digest is
never hard-coded by hand, and the requested tag is refreshed on every call so a
stale local cache is never mistaken for the current registry state.

The requested tag is explicitly pulled through the selected runtime adapter
(and its recorded Docker Desktop context) before inspection. The RepoDigest
matching the requested repository is selected rather than blindly taking the
first entry. Provenance records the requested tag, the previously locked
digest, the newly resolved digest, whether the remote tag changed, the
architecture and OS, the resolution method, and the retrieval timestamp.

All Docker invocations go through the selected runtime adapter, which also
fails closed if the recorded Docker Desktop context drifted.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import pathlib
import sys
from typing import Any, List, Optional

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from re_runtime import Adapter, read_runtime_json  # noqa: E402


def _repository_of(image: str) -> str:
    """Return the repository portion of a tag (e.g. ``python`` for
    ``python:3.12-slim-bookworm``), ignoring any registry host."""
    repo = image.split("/")[-1]
    return repo.split(":")[0]


def _select_matching_repo_digest(repo_digests: List[str], repository: str) -> Optional[str]:
    """Select the RepoDigest whose repository matches the requested one rather
    than blindly returning the first entry (which could belong to another tag
    aliased onto the same image)."""
    for entry in repo_digests:
        if entry.startswith(repository + "@") or entry.split("@", 1)[0].rstrip("/") == repository:
            return entry
    return None


def read_previous_lock(output: pathlib.Path) -> Optional[dict[str, Any]]:
    if not output.is_file():
        return None
    try:
        with open(output, "r", encoding="utf-8") as handle:
            return json.load(handle)
    except (ValueError, OSError):
        return None


def resolve_base_image(
    *,
    adapter: Adapter,
    image: str,
    output: pathlib.Path,
) -> dict[str, Any]:
    previous = read_previous_lock(output)
    previous_digest = (previous or {}).get("resolved_digest")

    # Refresh: explicitly pull the requested tag on every call so a cached stale
    # tag is not treated as the current registry state.
    pulled = adapter.run(adapter.docker(["pull", image]), capture=True)
    if pulled.returncode != 0:
        raise RuntimeError(
            f"docker pull {image} failed: {pulled.stderr.strip()[:200] or pulled.stdout.strip()[:200]}"
        )

    result = adapter.run(adapter.docker(["image", "inspect", image]), capture=True)
    if result.returncode != 0:
        raise RuntimeError(f"docker image inspect {image} failed: {result.stderr.strip()[:200]}")
    data = json.loads(result.stdout)[0]

    repository = _repository_of(image)
    repo_digests = data.get("RepoDigests") or []
    digest = _select_matching_repo_digest(repo_digests, repository)
    if not digest:
        raise RuntimeError(
            f"no RepoDigest matching repository {repository!r} for {image}; got {repo_digests}"
        )

    remote_changed = previous_digest is not None and previous_digest != digest
    record = {
        "schema_version": 2,
        "source_repository": repository,
        "requested_tag": image,
        "previously_locked_digest": previous_digest,
        "resolved_digest": digest,
        "remote_tag_changed": remote_changed,
        "architecture": data.get("Architecture"),
        "os": data.get("Os"),
        "image_id": data.get("Id"),
        "resolution_method": "docker pull <tag> + inspect, RepoDigest matched to requested repository",
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
    if record.get("remote_tag_changed"):
        print(
            f"INFO: base tag {args.image} changed from {record['previously_locked_digest']} "
            f"to {record['resolved_digest']}",
            file=sys.stderr,
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
