#!/usr/bin/env python3
"""Shared Docker runtime probe, selection, and adapter for the RE toolchain.

This module is the single source of truth for how the reverse-engineering
toolchain talks to a Docker daemon on this workstation:

* ``probe_docker_desktop`` / ``probe_wsl_engine`` produce structured diagnostics
  about each candidate runtime without modifying the host beyond an optional,
  opt-out-able Docker Desktop start that uses bounded polling.
* ``select_runtime`` applies the issue #14 selection rules and records the
  decision in ``.work/re/runtime.json``.
* ``Adapter`` turns every subsequent Docker / Compose / Bash operation into the
  correct transport argv for the selected runtime.

Every function accepts an injectable ``run`` callable so the entire runtime
matrix is testable with a mocked runner and no real Docker daemon.

Selection rules (issue #14 review, comment 5166102442):

* an explicit ``DockerDesktop`` or ``WslEngine`` selection wins and fails
  clearly when that candidate is unavailable;
* a single healthy candidate is selected;
* when both are healthy, the active healthy Docker Desktop Linux context is
  preferred, otherwise the selected native WSL Engine is used;
* when neither is healthy a structured diagnostic is emitted and nothing is
  installed;
* the selection is written once and the adapter never switches runtime after a
  toolchain run starts.
"""

from __future__ import annotations

import argparse
import dataclasses
import datetime as _dt
import json
import os
import re
import shutil
import subprocess
import sys
import time
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

DEFAULT_WSL_DISTRIBUTION = "Ubuntu"
RUNTIME_JSON_REL = ".work/re/runtime.json"
START_POLL_SECONDS = 2.0
DEFAULT_START_TIMEOUT_SECONDS = 120
ALL_RUNTIMES = ("DockerDesktop", "WslEngine")


@dataclasses.dataclass
class ProcResult:
    returncode: int
    stdout: str = ""
    stderr: str = ""


def _looks_utf16(raw: bytes) -> bool:
    """Detect UTF-16LE output such as ``wsl.exe -l -v`` on Windows."""
    return bool(raw) and raw.count(0) > max(1, len(raw) // 4)


def _decode(raw: Optional[bytes]) -> str:
    if not raw:
        return ""
    if _looks_utf16(raw):
        return raw.decode("utf-16-le", "replace").lstrip("﻿")
    return raw.decode("utf-8", "replace")


def default_runner(
    argv: Sequence[str],
    *,
    capture: bool = False,
    cwd: Optional[str] = None,
    env: Optional[Dict[str, str]] = None,
    timeout: Optional[float] = None,
) -> ProcResult:
    """Run ``argv`` with subprocess. Captured output is decoded robustly
    (``wsl.exe -l -v`` emits UTF-16LE). When ``capture`` is false the child's
    stdout/stderr are inherited so exit codes and stderr are preserved for the
    caller."""
    if capture:
        proc = subprocess.run(list(argv), capture_output=True, cwd=cwd, env=env, timeout=timeout)
        return ProcResult(proc.returncode, _decode(proc.stdout), _decode(proc.stderr))
    proc = subprocess.run(list(argv), cwd=cwd, env=env, timeout=timeout)
    return ProcResult(proc.returncode, "", "")


Runner = Callable[..., ProcResult]


def probe_result(
    candidate: str,
    available: bool,
    healthy: bool,
    reason: str,
    diagnostics: Sequence[str],
    details: Dict[str, Any],
) -> Dict[str, Any]:
    return {
        "candidate": candidate,
        "available": bool(available),
        "healthy": bool(healthy),
        "reason": reason,
        "diagnostics": list(diagnostics),
        "details": details,
    }


def _active_docker_context(run: Runner, docker: str) -> Dict[str, str]:
    info: Dict[str, str] = {}
    r = run([docker, "context", "show"], capture=True)
    if r.returncode == 0:
        info["active_context"] = r.stdout.strip()
    r = run([docker, "context", "ls"], capture=True)
    if r.returncode == 0:
        for line in r.stdout.splitlines():
            stripped = line.lstrip()
            if stripped.startswith("*"):
                parts = stripped.split()
                if parts:
                    info["context"] = parts[0]
                if len(parts) >= 2:
                    info["endpoint"] = parts[-1]
                break
    return info


def probe_docker_desktop(
    run: Runner,
    *,
    no_start_docker_desktop: bool = False,
    start_timeout_s: float = DEFAULT_START_TIMEOUT_SECONDS,
) -> Dict[str, Any]:
    """Probe the Windows Docker Desktop candidate for actual usability.

    Records distinct causes: ``docker_cli_missing``, ``desktop_status_unsupported``,
    ``start_disabled``, ``start_failed``, ``start_timeout``,
    ``daemon_unavailable``, ``windows_container_mode``, ``compose_missing``.
    """
    diag: List[str] = []
    details: Dict[str, Any] = {}
    docker = shutil.which("docker")
    if not docker:
        return probe_result(
            "DockerDesktop", False, False, "docker_cli_missing",
            ["docker CLI was not found on PATH; Docker Desktop is not a usable runtime candidate."],
            details,
        )
    details["docker_cli"] = docker

    r = run([docker, "--version"], capture=True)
    if r.returncode == 0:
        details["client_version"] = r.stdout.strip()
    else:
        diag.append(f"docker --version failed: {r.stderr.strip()[:200]}")

    # `docker desktop status --format json` is supported by recent Desktop
    # versions; older installs fall back to docker info alone.
    status: Optional[Dict[str, Any]] = None
    r = run([docker, "desktop", "status", "--format", "json"], capture=True)
    if r.returncode == 0:
        try:
            status = json.loads(r.stdout)
            details["desktop_status"] = status
        except ValueError:
            diag.append(f"docker desktop status returned non-JSON output: {r.stdout.strip()[:200]}")
    else:
        diag.append("docker desktop status --format json is unsupported here; falling back to docker info")

    details.update(_active_docker_context(run, docker))
    available = True

    def _info_result() -> Tuple[bool, str]:
        """Return (ok, failure_reason). Failure reason distinguishes a Linux
        daemon that is unavailable from Docker Desktop running Windows containers."""
        r = run([docker, "info"], capture=True)
        if r.returncode != 0:
            diag.append(f"docker info failed: {r.stderr.strip()[:200] or r.stdout.strip()[:200]}")
            return False, "daemon_unavailable"
        ostype, server = parse_docker_info(r.stdout)
        details["server_os"] = ostype
        if server:
            details["server_version"] = server
        if ostype and ostype != "linux":
            diag.append(f"docker server is running {ostype} containers, not Linux")
            return False, "windows_container_mode"
        if not ostype:
            diag.append("docker info did not report an OSType")
            return False, "daemon_unavailable"
        return True, ""

    info_ok, info_fail_reason = _info_result()
    if not info_ok:
        if info_fail_reason == "windows_container_mode":
            return probe_result(
                "DockerDesktop", True, False, "windows_container_mode", diag, details
            )
        stopped = isinstance(status, dict) and str(status.get("Status", "")).lower() == "stopped"
        if stopped and not no_start_docker_desktop:
            diag.append("Docker Desktop is installed but stopped; starting it with bounded polling")
            r = run([docker, "desktop", "start"], capture=False)
            if r.returncode != 0:
                return probe_result(
                    "DockerDesktop", True, False, "start_failed",
                    diag + [f"docker desktop start failed: {r.stderr.strip()[:200]}"],
                    details,
                )
            deadline = time.monotonic() + start_timeout_s
            while time.monotonic() < deadline:
                if _info_result()[0]:
                    diag.append("Docker Desktop started and became healthy")
                    break
                time.sleep(START_POLL_SECONDS)
            else:
                return probe_result(
                    "DockerDesktop", True, False, "start_timeout",
                    diag + [f"Docker Desktop did not become healthy within {start_timeout_s:.0f}s"],
                    details,
                )
        elif stopped and no_start_docker_desktop:
            return probe_result(
                "DockerDesktop", True, False, "start_disabled",
                diag + ["Docker Desktop is stopped and -NoStartDockerDesktop prevented starting it"],
                details,
            )
        else:
            return probe_result("DockerDesktop", True, False, info_fail_reason or "daemon_unavailable", diag, details)
    else:
        diag.append("docker info succeeded with Linux containers")

    r = run([docker, "compose", "version"], capture=True)
    if r.returncode != 0:
        return probe_result(
            "DockerDesktop", True, False, "compose_missing",
            diag + [f"docker compose version failed: {r.stderr.strip()[:200]}"],
            details,
        )
    details["compose_version"] = r.stdout.strip()
    diag.append("docker compose version succeeded")
    return probe_result("DockerDesktop", True, True, "ok", diag, details)


def parse_docker_info(text: str) -> Tuple[str, str]:
    """Extract OSType and Server Version from plain ``docker info`` output.

    Plain-text parsing avoids relying on ``--format '{{...}}'`` templates, which
    ``wsl.exe`` can mangle when it relays arguments into a distribution.
    """
    ostype = ""
    server = ""
    for line in text.splitlines():
        if ":" not in line:
            continue
        key, _, value = line.partition(":")
        key = key.strip()
        value = value.strip()
        if key.lower() == "ostype":
            ostype = value
        elif key.lower() in ("server version", "server"):
            server = value
    return ostype, server


def parse_wsl_list(text: str) -> Dict[str, int]:
    """Parse ``wsl.exe -l -v`` output into ``{name: version}``.

    Handles the leading ``*`` default marker and whitespace padding. Names with
    spaces are uncommon for managed distributions and are not supported.
    """
    distros: Dict[str, int] = {}
    for line in text.splitlines():
        line = line.rstrip("\r").strip()
        if not line or line.upper().startswith("NAME"):
            continue
        if line.lower().startswith("windows subsystem") or line.lower().startswith("copyright"):
            continue
        stripped = line[1:].strip() if line.startswith("*") else line
        parts = stripped.split()
        if len(parts) >= 3 and parts[-1].isdigit():
            distros[parts[0]] = int(parts[-1])
    return distros


def probe_wsl_engine(run: Runner, *, distribution: str = DEFAULT_WSL_DISTRIBUTION) -> Dict[str, Any]:
    """Probe the native Docker Engine inside the selected WSL distribution.

    Records distinct causes: ``wsl_unavailable``, ``distro_missing``,
    ``non_wsl2``, ``cli_missing``, ``daemon_unavailable``,
    ``server_not_linux``, ``compose_missing``. Never installs Docker Engine or
    Compose. ``--exec`` is used so a Docker Desktop WSL-integration shim is not
    mistaken for a native CLI.
    """
    diag: List[str] = []
    details: Dict[str, Any] = {}
    wsl = shutil.which("wsl") or "wsl.exe"
    details["wsl_exe"] = wsl

    r = run([wsl, "-l", "-v"], capture=True)
    if r.returncode != 0:
        return probe_result(
            "WslEngine", False, False, "wsl_unavailable",
            [f"wsl.exe -l -v failed: {r.stderr.strip()[:200]}"],
            details,
        )
    distros = parse_wsl_list(r.stdout)
    details["wsl_distributions"] = distros
    if distribution not in distros:
        return probe_result(
            "WslEngine", True, False, "distro_missing",
            [f"WSL distribution {distribution!r} is not installed; found: {sorted(distros)}"],
            details,
        )
    version = distros[distribution]
    details["wsl_distribution"] = distribution
    details["wsl_version"] = version
    if version != 2:
        return probe_result(
            "WslEngine", True, False, "non_wsl2",
            [f"WSL distribution {distribution!r} is WSL {version}, not WSL 2"],
            details,
        )

    # Native binary check: --exec does not see the Desktop WSL-integration shim.
    r = run([wsl, "-d", distribution, "--exec", "docker", "--version"], capture=True)
    if r.returncode != 0:
        return probe_result(
            "WslEngine", True, False, "cli_missing",
            [f"native docker CLI was not found inside WSL distribution {distribution!r}"],
            details,
        )
    details["client_version"] = r.stdout.strip()

    r = run([wsl, "-d", distribution, "--exec", "docker", "info"], capture=True)
    if r.returncode != 0:
        return probe_result(
            "WslEngine", True, False, "daemon_unavailable",
            [f"docker info inside {distribution!r} failed; the WSL Docker daemon may be stopped: {r.stderr.strip()[:200]}"],
            details,
        )
    ostype, server = parse_docker_info(r.stdout)
    details["server_os"] = ostype
    if server:
        details["server_version"] = server
    if ostype and ostype != "linux":
        return probe_result(
            "WslEngine", True, False, "server_not_linux",
            [f"WSL Docker server reports OSType {ostype!r}, not linux"],
            details,
        )

    r = run([wsl, "-d", distribution, "--exec", "docker", "compose", "version"], capture=True)
    if r.returncode != 0:
        return probe_result(
            "WslEngine", True, False, "compose_missing",
            [f"docker compose version inside {distribution!r} failed: {r.stderr.strip()[:200]}"],
            details,
        )
    details["compose_version"] = r.stdout.strip()
    diag.append(f"native Docker Engine inside WSL {distribution!r} is healthy")
    return probe_result("WslEngine", True, True, "ok", diag, details)


def _describe_failure(probes: Dict[str, Dict[str, Any]]) -> List[Dict[str, Any]]:
    return [
        {
            "candidate": probes[c]["candidate"],
            "reason": probes[c]["reason"],
            "diagnostics": probes[c]["diagnostics"],
        }
        for c in ALL_RUNTIMES
    ]


def _build_metadata(probes: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
    d = probes["DockerDesktop"]["details"]
    w = probes["WslEngine"]["details"]
    return {
        "os_type": "windows" if os.name == "nt" else os.name,
        "client_version": d.get("client_version") or w.get("client_version"),
        "server_version": d.get("server_version") or w.get("server_version"),
        "server_os": d.get("server_os") or w.get("server_os"),
        "compose_version": d.get("compose_version") or w.get("compose_version"),
        "docker_desktop": {
            "context": d.get("context"),
            "active_context": d.get("active_context"),
            "endpoint": d.get("endpoint"),
            "desktop_status": d.get("desktop_status"),
            "client_version": d.get("client_version"),
            "server_version": d.get("server_version"),
            "server_os": d.get("server_os"),
            "compose_version": d.get("compose_version"),
        },
        "wsl": {
            "distribution": w.get("wsl_distribution"),
            "version": w.get("wsl_version"),
            "distributions": w.get("wsl_distributions"),
            "docker_cli": w.get("docker_cli"),
            "client_version": w.get("client_version"),
            "server_version": w.get("server_version"),
            "server_os": w.get("server_os"),
            "compose_version": w.get("compose_version"),
        },
    }


def select_runtime(
    *,
    requested: str,
    wsl_distribution: str,
    no_start_docker_desktop: bool,
    run: Runner,
    repo_root: str,
    start_timeout_s: float = DEFAULT_START_TIMEOUT_SECONDS,
    now_iso: Optional[str] = None,
) -> Dict[str, Any]:
    """Probe both candidates and apply the issue #14 selection rules."""
    requested = requested or "Auto"
    if requested not in ("Auto",) + ALL_RUNTIMES:
        raise ValueError(f"unsupported ContainerRuntime {requested!r}")

    probes = {
        "DockerDesktop": probe_docker_desktop(
            run, no_start_docker_desktop=no_start_docker_desktop, start_timeout_s=start_timeout_s
        ),
        "WslEngine": probe_wsl_engine(run, distribution=wsl_distribution),
    }
    desktop = probes["DockerDesktop"]
    wsl = probes["WslEngine"]

    selected: Optional[str] = None
    reason = ""
    if requested == "DockerDesktop":
        if desktop["healthy"]:
            selected = "DockerDesktop"
            reason = "explicit DockerDesktop selection is healthy"
        else:
            reason = f"explicit DockerDesktop selection is unavailable: {desktop['reason']}"
    elif requested == "WslEngine":
        if wsl["healthy"]:
            selected = "WslEngine"
            reason = f"explicit WslEngine selection is healthy in {wsl_distribution!r}"
        else:
            reason = f"explicit WslEngine selection is unavailable: {wsl['reason']}"
    else:
        if desktop["healthy"] and wsl["healthy"]:
            context = (desktop["details"].get("active_context") or desktop["details"].get("context") or "").lower()
            if "desktop" in context:
                selected = "DockerDesktop"
                reason = "both healthy; active Docker Desktop Linux context preferred"
            else:
                selected = "WslEngine"
                reason = "both healthy; no active Docker Desktop Linux context, preferred native WSL Engine"
        elif desktop["healthy"]:
            selected = "DockerDesktop"
            reason = "only Docker Desktop is healthy"
        elif wsl["healthy"]:
            selected = "WslEngine"
            reason = "only the native WSL Engine is healthy"
        else:
            reason = "no healthy Docker runtime candidate; nothing was installed"

    selection: Dict[str, Any] = {
        "schema_version": 1,
        "generated_utc": now_iso or _dt.datetime.now(_dt.timezone.utc).isoformat(),
        "requested_runtime": requested,
        "wsl_distribution": wsl_distribution,
        "no_start_docker_desktop": bool(no_start_docker_desktop),
        "selected_runtime": selected,
        "selection_reason": reason,
        "probes": probes,
    }
    if selected:
        selection["metadata"] = _build_metadata(probes)
    else:
        selection["selection_error"] = _describe_failure(probes)
    return selection


def write_runtime_json(selection: Dict[str, Any], path: str) -> str:
    path = os.path.abspath(path)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(selection, handle, indent=2, sort_keys=True)
        handle.write("\n")
    return path


def read_runtime_json(path: str) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as handle:
        return json.load(handle)


def _bash_quote(value: str) -> str:
    return "'" + value.replace("'", "'\"'\"'") + "'"


# ------------------------------------------------------------------- Beagle


def find_linux_beagle_api(vendor_extract_root: str) -> Optional[str]:
    """Return the staged Linux Beagle API library path, or None when absent."""
    for root, _dirs, files in os.walk(vendor_extract_root):
        for name in files:
            if re.match(r"^(beagle\.so|libbeagle\.so)", name):
                return os.path.join(root, name)
    return None


def find_windows_beagle_api(vendor_extract_root: str) -> Optional[str]:
    """Return the staged Windows Beagle API directory (contains beagle_py.py)."""
    for root, _dirs, files in os.walk(vendor_extract_root):
        if "beagle_py.py" in files:
            return root
    return None


def choose_beagle_route(runtime: str, linux_api: Optional[str], windows_api: Optional[str]) -> Dict[str, Any]:
    """A missing Linux Beagle API blocks only containerized live capture; the
    Windows host shim remains available and emits the same JSONL format."""
    if runtime == "WslEngine" and linux_api:
        return {"route": "container", "linux_api": linux_api}
    if windows_api:
        return {"route": "windows_host", "windows_api_dir": windows_api}
    return {"route": "unavailable"}


class Adapter:
    """Turn toolchain operations into the correct transport argv for the
    selected runtime. Desktop mode invokes Windows ``docker``/``docker compose``
    from the Windows repository path. WSL Engine mode invokes Docker inside the
    selected distribution through ``wsl.exe --cd <wsl path> --exec`` so no shell
    re-parses the repository path."""

    def __init__(
        self,
        selection: Dict[str, Any],
        repo_root: str,
        run: Optional[Runner] = None,
        wsl_exe: Optional[str] = None,
    ):
        self.selection = selection
        self.repo_root = os.path.abspath(repo_root)
        self.runtime = selection.get("selected_runtime") or selection.get("runtime")
        if self.runtime not in ALL_RUNTIMES:
            raise ValueError(f"unsupported runtime: {self.runtime!r}")
        self.wsl_distribution = selection.get("wsl_distribution") or DEFAULT_WSL_DISTRIBUTION
        self._run = run or default_runner
        self._wsl_exe = wsl_exe or (shutil.which("wsl") or "wsl.exe")
        self._wsl_repo_path: Optional[str] = None
        self._path_cache: Dict[str, str] = {}

    @property
    def wsl_repo_path(self) -> str:
        if self._wsl_repo_path is None:
            self._wsl_repo_path = self.to_wsl_path(self.repo_root)
        return self._wsl_repo_path

    def to_wsl_path(self, win_path: str) -> str:
        """Convert a Windows path once using a discrete ``wslpath -a`` argument.
        Desktop mode never converts paths for Docker operations."""
        if self.runtime == "DockerDesktop":
            return win_path
        if win_path in self._path_cache:
            return self._path_cache[win_path]
        r = self._run(
            [self._wsl_exe, "-d", self.wsl_distribution, "--exec", "wslpath", "-a", win_path],
            capture=True,
        )
        if r.returncode != 0:
            raise RuntimeError(
                f"wslpath conversion failed for {win_path!r} in {self.wsl_distribution!r}: {r.stderr.strip()[:200]}"
            )
        converted = r.stdout.strip()
        if not converted:
            raise RuntimeError(f"wslpath returned an empty path for {win_path!r}")
        self._path_cache[win_path] = converted
        return converted

    def docker(self, args: Sequence[str]) -> List[str]:
        if self.runtime == "DockerDesktop":
            return ["docker", *args]
        return [
            self._wsl_exe,
            "--cd",
            self.wsl_repo_path,
            "-d",
            self.wsl_distribution,
            "--exec",
            "docker",
            *args,
        ]

    def compose(self, args: Sequence[str]) -> List[str]:
        return self.docker(["compose", *args])

    def bash(self, script_rel: str, script_args: Sequence[str] = (), env: Optional[Dict[str, str]] = None) -> List[str]:
        """Invoke a repository bash script inside the WSL distribution. Desktop
        mode drives the toolchain natively through PowerShell, so this raises
        rather than inventing a Git-Bash transport."""
        if self.runtime == "DockerDesktop":
            raise RuntimeError(
                "bash scripts are only invoked through the WSL Engine adapter; "
                "Docker Desktop mode drives the toolchain natively through PowerShell"
            )
        assignments = " ".join(f"{k}={_bash_quote(str(v))}" for k, v in (env or {}).items())
        quoted_args = " ".join(_bash_quote(str(a)) for a in script_args)
        cmd = f"bash {script_rel}"
        if quoted_args:
            cmd += " " + quoted_args
        if assignments:
            cmd = assignments + " " + cmd
        return [
            self._wsl_exe,
            "--cd",
            self.wsl_repo_path,
            "-d",
            self.wsl_distribution,
            "--exec",
            "bash",
            "-lc",
            cmd,
        ]

    def run(self, argv: Sequence[str], capture: bool = False, **kwargs: Any) -> ProcResult:
        return self._run(list(argv), capture=capture, **kwargs)


# --------------------------------------------------------------------------- CLI


def _cli_probe(args: argparse.Namespace) -> int:
    os.chdir(args.repo_root)
    selection = select_runtime(
        requested=args.requested,
        wsl_distribution=args.wsl_distribution,
        no_start_docker_desktop=args.no_start_docker_desktop,
        run=default_runner,
        repo_root=args.repo_root,
        start_timeout_s=args.start_timeout_s,
        now_iso=args.now,
    )
    write_runtime_json(selection, args.runtime_json)
    print(json.dumps(selection, indent=2, sort_keys=True))
    # Every toolchain entrypoint requires a usable runtime.
    return 0 if selection["selected_runtime"] else 2


def _strip_separator(value: List[str]) -> List[str]:
    """argparse REMAINDER keeps the ``--`` separator; drop it for the child argv."""
    if value and value[0] == "--":
        return value[1:]
    return value


def _cli_docker(args: argparse.Namespace) -> int:
    selection = read_runtime_json(args.runtime_json)
    adapter = Adapter(selection, args.repo_root)
    os.chdir(args.repo_root)
    return adapter.run(adapter.docker(_strip_separator(args.args))).returncode


def _cli_compose(args: argparse.Namespace) -> int:
    selection = read_runtime_json(args.runtime_json)
    adapter = Adapter(selection, args.repo_root)
    os.chdir(args.repo_root)
    return adapter.run(adapter.compose(_strip_separator(args.args))).returncode


def _cli_bash(args: argparse.Namespace) -> int:
    selection = read_runtime_json(args.runtime_json)
    adapter = Adapter(selection, args.repo_root)
    env: Dict[str, str] = {}
    for item in args.env or []:
        key, sep, value = item.partition("=")
        if sep:
            env[key] = value
    os.chdir(args.repo_root)
    return adapter.run(adapter.bash(args.script, _strip_separator(args.arg), env)).returncode


def _cli_wslpath(args: argparse.Namespace) -> int:
    selection = read_runtime_json(args.runtime_json)
    adapter = Adapter(selection, args.repo_root)
    print(adapter.to_wsl_path(args.path))
    return 0


def _cli_beagle_route(args: argparse.Namespace) -> int:
    selection = read_runtime_json(args.runtime_json)
    runtime = selection.get("selected_runtime")
    vendor_root = os.path.join(args.repo_root, ".work", "vendor", "totalphase", "extracted")
    linux_api = find_linux_beagle_api(vendor_root) if os.path.isdir(vendor_root) else None
    windows_api = find_windows_beagle_api(vendor_root) if os.path.isdir(vendor_root) else None
    print(json.dumps(choose_beagle_route(runtime, linux_api, windows_api), sort_keys=True))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    p_probe = sub.add_parser("probe", help="probe and select the Docker runtime; writes runtime.json")
    p_probe.add_argument("--requested", default="Auto", choices=["Auto", "DockerDesktop", "WslEngine"])
    p_probe.add_argument("--wsl-distribution", default=DEFAULT_WSL_DISTRIBUTION)
    p_probe.add_argument("--no-start-docker-desktop", action="store_true")
    p_probe.add_argument("--repo-root", required=True)
    p_probe.add_argument("--runtime-json", required=True)
    p_probe.add_argument("--start-timeout-s", type=float, default=DEFAULT_START_TIMEOUT_SECONDS)
    p_probe.add_argument("--now", default=None, help="ISO timestamp override for deterministic tests")
    p_probe.set_defaults(func=_cli_probe)

    p_docker = sub.add_parser("docker", help="run `docker <args...>` through the selected adapter")
    p_docker.add_argument("--runtime-json", required=True)
    p_docker.add_argument("--repo-root", required=True)
    p_docker.add_argument("args", nargs=argparse.REMAINDER)
    p_docker.set_defaults(func=_cli_docker)

    p_compose = sub.add_parser("compose", help="run `docker compose <args...>` through the selected adapter")
    p_compose.add_argument("--runtime-json", required=True)
    p_compose.add_argument("--repo-root", required=True)
    p_compose.add_argument("args", nargs=argparse.REMAINDER)
    p_compose.set_defaults(func=_cli_compose)

    p_bash = sub.add_parser("bash", help="run a repository bash script through the WSL Engine adapter")
    p_bash.add_argument("--runtime-json", required=True)
    p_bash.add_argument("--repo-root", required=True)
    p_bash.add_argument("--script", required=True)
    p_bash.add_argument("--env", action="append", default=[])
    p_bash.add_argument("arg", nargs=argparse.REMAINDER)
    p_bash.set_defaults(func=_cli_bash)

    p_wslpath = sub.add_parser("wslpath", help="convert a Windows path for the selected runtime")
    p_wslpath.add_argument("--runtime-json", required=True)
    p_wslpath.add_argument("--repo-root", required=True)
    p_wslpath.add_argument("--path", required=True)
    p_wslpath.set_defaults(func=_cli_wslpath)

    p_route = sub.add_parser("beagle-route", help="decide the Beagle capture route for the selected runtime")
    p_route.add_argument("--runtime-json", required=True)
    p_route.add_argument("--repo-root", required=True)
    p_route.set_defaults(func=_cli_beagle_route)
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
