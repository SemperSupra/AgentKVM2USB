#!/usr/bin/env python3
"""Apply reviewed low-risk GitHub repository metadata from the tracked manifest.

This command is intentionally separate from validation. It requires --apply,
uses the authenticated GitHub CLI, and changes only description, homepage,
default branch, and topics. Visibility and archived-state differences are
reported and must be handled by a human through a separately reviewed action.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import shutil
import subprocess
import sys
from typing import Any


def run(argv: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(argv, cwd=cwd, text=True, capture_output=True, check=False)


def load_manifest(root: Path) -> dict[str, Any]:
    path = root / ".github" / "repository-metadata.json"
    return json.loads(path.read_text(encoding="utf-8"))


def normalize_topics(value: Any) -> set[str]:
    result: set[str] = set()
    for entry in value or []:
        if isinstance(entry, str):
            result.add(entry.lower())
        elif isinstance(entry, dict) and entry.get("name"):
            result.add(str(entry["name"]).lower())
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--apply", action="store_true", help="perform the reviewed metadata update")
    args = parser.parse_args(argv)

    root = args.root.resolve()
    manifest = load_manifest(root)
    expected = manifest["repository"]
    repository = expected["name_with_owner"]

    gh = shutil.which("gh")
    if not gh:
        print("ERROR: authenticated gh CLI is required", file=sys.stderr)
        return 2

    fields = "nameWithOwner,description,homepageUrl,repositoryTopics,defaultBranchRef,visibility,isArchived"
    view = run([gh, "repo", "view", repository, "--json", fields], root)
    if view.returncode != 0:
        print(view.stderr or view.stdout, file=sys.stderr)
        return view.returncode or 2
    current = json.loads(view.stdout)

    current_visibility = str(current.get("visibility") or "").lower()
    expected_visibility = str(expected.get("visibility") or "").lower()
    if current_visibility != expected_visibility:
        print(
            f"ERROR: visibility drift requires explicit human review: {current_visibility!r} -> {expected_visibility!r}",
            file=sys.stderr,
        )
        return 3
    if bool(current.get("isArchived")) != bool(expected.get("archived")):
        print("ERROR: archived-state drift requires explicit human review", file=sys.stderr)
        return 3

    current_default = (current.get("defaultBranchRef") or {}).get("name")
    current_topics = normalize_topics(current.get("repositoryTopics"))
    expected_topics = normalize_topics(expected.get("topics"))

    changes: list[str] = []
    edit_args = [gh, "repo", "edit", repository]

    if current.get("description") != expected.get("description"):
        edit_args += ["--description", str(expected.get("description") or "")]
        changes.append("description")
    if current.get("homepageUrl") != expected.get("homepage"):
        edit_args += ["--homepage", str(expected.get("homepage") or "")]
        changes.append("homepage")
    if current_default != expected.get("default_branch"):
        edit_args += ["--default-branch", str(expected["default_branch"])]
        changes.append("default_branch")

    for topic in sorted(expected_topics - current_topics):
        edit_args += ["--add-topic", topic]
        changes.append(f"add-topic:{topic}")
    for topic in sorted(current_topics - expected_topics):
        edit_args += ["--remove-topic", topic]
        changes.append(f"remove-topic:{topic}")

    if not changes:
        print("PASS: remote repository metadata already matches the manifest")
        return 0

    print("Planned metadata changes:")
    for change in changes:
        print(f"- {change}")

    if not args.apply:
        print("No changes made. Re-run with --apply after review.")
        return 1

    result = run(edit_args, root)
    if result.returncode != 0:
        print(result.stderr or result.stdout, file=sys.stderr)
        return result.returncode or 2

    verify = run(
        [sys.executable, str(root / "scripts" / "validate_repository_metadata.py"), "--root", str(root), "--remote", "required"],
        root,
    )
    sys.stdout.write(verify.stdout)
    sys.stderr.write(verify.stderr)
    return verify.returncode


if __name__ == "__main__":
    raise SystemExit(main())
