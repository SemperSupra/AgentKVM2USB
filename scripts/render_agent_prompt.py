#!/usr/bin/env python3
"""Render repository-owned kickoff prompts without requiring chat history."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
PROMPTS = {
    "local": ROOT / "prompts" / "LOCAL_AGENT_KICKOFF.md",
    "web": ROOT / "prompts" / "WEB_AGENT_REVIEW.md",
    "bootstrap": ROOT / "prompts" / "NEW_REPOSITORY_BOOTSTRAP.md",
}


def default_repository() -> str:
    manifest_path = ROOT / ".github" / "repository-metadata.json"
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        value = manifest["repository"]["name_with_owner"]
    except (OSError, ValueError, KeyError, TypeError) as exc:
        raise RuntimeError(f"cannot derive repository from {manifest_path}: {exc}") from exc
    if not isinstance(value, str) or value.count("/") != 1:
        raise RuntimeError("repository.name_with_owner must be owner/name")
    return value


def render(mode: str, repository: str, issue: int | None) -> str:
    template_path = PROMPTS[mode]
    text = template_path.read_text(encoding="utf-8")
    text = text.replace("{{REPOSITORY}}", repository)
    if "{{ISSUE}}" in text:
        if issue is None:
            raise ValueError(f"--issue is required for {mode} prompts")
        text = text.replace("{{ISSUE}}", str(issue))
    unresolved = [token for token in ("{{REPOSITORY}}", "{{ISSUE}}") if token in text]
    if unresolved:
        raise ValueError(f"unresolved prompt tokens: {', '.join(unresolved)}")
    return text


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=sorted(PROMPTS))
    parser.add_argument("--repository", help="GitHub owner/name; defaults to repository-metadata.json")
    parser.add_argument("--issue", type=int, help="canonical GitHub issue number")
    parser.add_argument("--output", type=Path, help="write the rendered prompt to this file")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    repository = args.repository or default_repository()
    if repository.count("/") != 1:
        print("error: --repository must be owner/name", file=sys.stderr)
        return 2
    if args.issue is not None and args.issue < 1:
        print("error: --issue must be a positive integer", file=sys.stderr)
        return 2
    try:
        output = render(args.mode, repository, args.issue)
    except (OSError, RuntimeError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(output, encoding="utf-8")
    else:
        sys.stdout.write(output)
        if not output.endswith("\n"):
            sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
