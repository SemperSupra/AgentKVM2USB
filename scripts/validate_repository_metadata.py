#!/usr/bin/env python3
"""Validate repository identity, coordination files, and optional GitHub metadata.

The tracked manifest is authoritative for expected project-specific metadata.
This tool reports drift; it never edits the repository or GitHub settings.
It uses only the Python standard library. Remote checks use the authenticated
GitHub CLI when available.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
from typing import Any

BRANCH_PATTERNS = (
    re.compile(r"^issue-\d+-[a-z0-9][a-z0-9-]*$"),
    re.compile(r"^(governance|docs|release|hotfix)/[a-z0-9][a-z0-9-]*$"),
    re.compile(r"^(main|recovery/[a-z0-9][a-z0-9-]*)$"),
)

REQUIRED_REPOSITORY_FIELDS = {
    "name_with_owner",
    "display_name",
    "description",
    "visibility",
    "default_branch",
    "archived",
    "homepage",
    "topics",
}


def run(argv: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(argv, cwd=cwd, text=True, capture_output=True, check=False)


def git_branch(root: Path) -> str | None:
    result = run(["git", "branch", "--show-current"], root)
    if result.returncode != 0:
        return None
    value = result.stdout.strip()
    return value or None


def normalize_topics(value: Any) -> set[str]:
    if not value:
        return set()
    topics: set[str] = set()
    for entry in value:
        if isinstance(entry, str):
            topics.add(entry.lower())
        elif isinstance(entry, dict) and entry.get("name"):
            topics.add(str(entry["name"]).lower())
    return topics


def validate_local(root: Path, manifest: dict[str, Any], errors: list[str], warnings: list[str]) -> None:
    repo = manifest.get("repository")
    project = manifest.get("project")
    if manifest.get("schema_version") != 1:
        errors.append("unsupported or missing manifest schema_version")
    if not isinstance(repo, dict):
        errors.append("manifest.repository must be an object")
        return
    if not isinstance(project, dict):
        errors.append("manifest.project must be an object")
        return

    missing = sorted(REQUIRED_REPOSITORY_FIELDS - set(repo))
    if missing:
        errors.append(f"manifest.repository missing fields: {', '.join(missing)}")

    topics = repo.get("topics")
    if not isinstance(topics, list) or not topics or len(topics) != len(set(topics)):
        errors.append("repository topics must be a non-empty unique list")

    canonical = project.get("canonical_documents") or {}
    if not isinstance(canonical, dict) or not canonical:
        errors.append("project.canonical_documents must be a non-empty object")
    else:
        for role, rel in canonical.items():
            path = root / str(rel)
            if not path.is_file():
                errors.append(f"canonical document missing for {role}: {rel}")

    required_governance = (
        "AGENTS.md",
        "docs/REMOTE_AGENT_COORDINATION.md",
        ".github/agent-handoff.schema.json",
        ".github/ISSUE_TEMPLATE/agent-work.yml",
        ".github/pull_request_template.md",
    )
    for rel in required_governance:
        if not (root / rel).is_file():
            errors.append(f"required governance artifact missing: {rel}")

    readme = root / "README.md"
    if readme.is_file():
        text = readme.read_text(encoding="utf-8", errors="replace")
        display = str(repo.get("display_name") or "")
        if display and not text.startswith(f"# {display}"):
            errors.append(f"README title does not match display_name {display!r}")
        if "Epiphan KVM2USB 3.0" not in text:
            errors.append("README does not identify the supported Epiphan KVM2USB 3.0 hardware")
        if "docs/REMOTE_AGENT_COORDINATION.md" not in text:
            warnings.append("README does not link the canonical coordination document")
        if ".github/repository-metadata.json" not in text:
            warnings.append("README does not link the repository metadata manifest")
    else:
        errors.append("README.md is missing")

    branch = git_branch(root)
    if branch and not any(pattern.fullmatch(branch) for pattern in BRANCH_PATTERNS):
        errors.append(
            f"branch {branch!r} does not follow issue-N-purpose or approved namespaced branch conventions"
        )


def load_remote(root: Path, repository: str) -> tuple[dict[str, Any] | None, str | None]:
    gh = shutil.which("gh")
    if not gh:
        return None, "gh CLI is not available"
    fields = "nameWithOwner,description,homepageUrl,repositoryTopics,defaultBranchRef,visibility,isArchived"
    result = run([gh, "repo", "view", repository, "--json", fields], root)
    if result.returncode != 0:
        return None, result.stderr.strip() or result.stdout.strip() or "gh repo view failed"
    try:
        return json.loads(result.stdout), None
    except json.JSONDecodeError as exc:
        return None, f"invalid gh JSON: {exc}"


def validate_remote(manifest: dict[str, Any], remote: dict[str, Any], errors: list[str], warnings: list[str]) -> None:
    expected = manifest["repository"]
    comparisons = {
        "nameWithOwner": expected.get("name_with_owner"),
        "description": expected.get("description"),
        "homepageUrl": expected.get("homepage"),
        "visibility": str(expected.get("visibility") or "").upper(),
        "isArchived": expected.get("archived"),
    }
    for field, wanted in comparisons.items():
        actual = remote.get(field)
        if actual != wanted:
            errors.append(f"remote {field} drift: expected {wanted!r}, got {actual!r}")

    default_ref = remote.get("defaultBranchRef") or {}
    actual_default = default_ref.get("name") if isinstance(default_ref, dict) else None
    if actual_default != expected.get("default_branch"):
        errors.append(
            f"remote default branch drift: expected {expected.get('default_branch')!r}, got {actual_default!r}"
        )

    wanted_topics = normalize_topics(expected.get("topics"))
    actual_topics = normalize_topics(remote.get("repositoryTopics"))
    missing = sorted(wanted_topics - actual_topics)
    extra = sorted(actual_topics - wanted_topics)
    if missing:
        errors.append(f"remote topics missing expected project topics: {', '.join(missing)}")
    if extra:
        warnings.append(f"remote topics not declared in manifest: {', '.join(extra)}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument(
        "--remote",
        choices=("off", "auto", "required"),
        default="auto",
        help="check GitHub metadata with gh when available",
    )
    parser.add_argument("--json", action="store_true", help="emit a machine-readable report")
    args = parser.parse_args(argv)

    root = args.root.resolve()
    manifest_path = root / ".github" / "repository-metadata.json"
    errors: list[str] = []
    warnings: list[str] = []

    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        report = {"ok": False, "errors": [f"cannot load {manifest_path}: {exc}"], "warnings": []}
        print(json.dumps(report, indent=2) if args.json else report["errors"][0])
        return 2

    validate_local(root, manifest, errors, warnings)

    if args.remote != "off":
        repository = str((manifest.get("repository") or {}).get("name_with_owner") or "")
        remote, failure = load_remote(root, repository)
        if remote is not None:
            validate_remote(manifest, remote, errors, warnings)
        elif args.remote == "required":
            errors.append(f"remote metadata check unavailable: {failure}")
        else:
            warnings.append(f"remote metadata check skipped: {failure}")

    report = {
        "ok": not errors,
        "repository": (manifest.get("repository") or {}).get("name_with_owner"),
        "branch": git_branch(root),
        "errors": errors,
        "warnings": warnings,
    }

    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        for item in errors:
            print(f"ERROR: {item}")
        for item in warnings:
            print(f"WARNING: {item}")
        print("PASS: repository metadata and coordination checks" if not errors else "FAIL: repository metadata drift")

    return 0 if not errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
