#!/usr/bin/env python3
"""Build and publish AgentKVM2USB portable assets with the local GitHub CLI."""

from __future__ import annotations

import argparse
import hashlib
import re
import shlex
import shutil
import subprocess
import sys
from pathlib import Path

PROJECT_NAME = "AgentKVM2USB"
DEFAULT_REPOSITORY = "SemperSupra/AgentKVM2USB"


def repository_root() -> Path:
    return Path(__file__).resolve().parents[1]


def read_project_version(root: Path) -> str:
    text = (root / "epiphan_sdk.py").read_text(encoding="utf-8")
    match = re.search(r'^\s*VERSION\s*=\s*["\']([^"\']+)["\']', text, re.MULTILINE)
    if not match:
        raise RuntimeError("Could not find VERSION in epiphan_sdk.py")
    return match.group(1)


def parse_args() -> argparse.Namespace:
    root = repository_root()
    default_tag = f"v{read_project_version(root).lstrip('vV')}"
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tag", default=default_tag, help=f"Release tag (default: {default_tag}).")
    parser.add_argument("--repository", default=DEFAULT_REPOSITORY, help="GitHub repository in owner/name form.")
    parser.add_argument("--target", default="main", help="Target branch or commit for a newly created tag.")
    parser.add_argument("--notes-file", type=Path, help="Optional Markdown release-notes file.")
    parser.add_argument("--draft", action="store_true", help="Create a new release as a draft.")
    parser.add_argument("--prerelease", action="store_true", help="Create a new release as a prerelease.")
    parser.add_argument("--skip-build", action="store_true", help="Upload existing artifacts from dist/.")
    parser.add_argument("--dry-run", action="store_true", help="Build and verify assets, then print release actions without uploading.")
    return parser.parse_args()


def run(command: list[str], *, check: bool = True) -> subprocess.CompletedProcess[str]:
    print("+ " + shlex.join(command))
    return subprocess.run(command, check=check, text=True)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def verify_checksum(zip_path: Path, checksum_path: Path) -> None:
    if not zip_path.is_file() or not checksum_path.is_file():
        raise FileNotFoundError(f"Missing release artifact or checksum: {zip_path}, {checksum_path}")
    fields = checksum_path.read_text(encoding="ascii").strip().split()
    if len(fields) < 2:
        raise RuntimeError(f"Invalid checksum file: {checksum_path}")
    expected_hash, expected_name = fields[0].lower(), fields[-1]
    actual_hash = sha256_file(zip_path)
    if expected_name != zip_path.name or expected_hash != actual_hash:
        raise RuntimeError(f"Checksum verification failed for {zip_path.name}")


def main() -> int:
    args = parse_args()
    root = repository_root()
    tag = args.tag.strip()
    if not re.fullmatch(r"v[0-9A-Za-z][0-9A-Za-z._+-]*", tag):
        raise ValueError("Tag must use the form v<version>, for example v0.2.0")
    version = tag[1:]

    if args.notes_file and not args.notes_file.is_file():
        raise FileNotFoundError(f"Release notes file not found: {args.notes_file}")

    if not args.skip_build:
        run([sys.executable, str(root / "scripts" / "build_portable.py"), "--version", version])

    zip_path = root / "dist" / f"{PROJECT_NAME}-{tag}-windows-portable.zip"
    checksum_path = zip_path.with_name(zip_path.name + ".sha256")
    verify_checksum(zip_path, checksum_path)

    gh = shutil.which("gh")
    if not gh:
        raise RuntimeError("GitHub CLI 'gh' was not found. Install it and run 'gh auth login'.")

    run([gh, "auth", "status"])
    release_exists = run(
        [gh, "release", "view", tag, "--repo", args.repository],
        check=False,
    ).returncode == 0

    if args.dry_run:
        action = "update existing release" if release_exists else "create release"
        print(f"Dry run: would {action} {args.repository} {tag}.")
        print(f"Dry run: would upload {zip_path.name} and {checksum_path.name}.")
        return 0

    if not release_exists:
        create = [
            gh,
            "release",
            "create",
            tag,
            "--repo",
            args.repository,
            "--target",
            args.target,
            "--title",
            f"{PROJECT_NAME} {tag}",
        ]
        if args.notes_file:
            create += ["--notes-file", str(args.notes_file.resolve())]
        else:
            create += [
                "--notes",
                "Windows portable source distribution with local Python dependency bootstrap. See PACKAGING.md for installation and hardware caveats.",
            ]
        if args.draft:
            create.append("--draft")
        if args.prerelease:
            create.append("--prerelease")
        run(create)
    elif args.notes_file:
        run(
            [
                gh,
                "release",
                "edit",
                tag,
                "--repo",
                args.repository,
                "--notes-file",
                str(args.notes_file.resolve()),
            ]
        )

    run(
        [
            gh,
            "release",
            "upload",
            tag,
            str(zip_path),
            str(checksum_path),
            "--repo",
            args.repository,
            "--clobber",
        ]
    )

    print(f"Published {zip_path.name} and {checksum_path.name} to {args.repository} release {tag}.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, RuntimeError, ValueError, subprocess.CalledProcessError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        raise SystemExit(1)
