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


def _list_context_names(run: Runner, docker: str) -> List[str]:
    r = run([docker, "context", "ls", "--format", "{{.Name}}"], capture=True)
    if r.returncode != 0:
        return []
    return [line.strip() for line in r.stdout.splitlines() if line.strip()]


def _active_context_name(run: Runner, docker: str) -> Optional[str]:
    r = run([docker, "context", "show"], capture=True)
    if r.returncode == 0:
        name = r.stdout.strip()
        return name or None
    return None


def _context_endpoint(run: Runner, docker: str, name: str) -> str:
    r = run([docker, "context", "inspect", name, "--format", "{{.Endpoints.docker.Host}}"], capture=True)
    if r.returncode == 0:
        return r.stdout.strip()
    return ""


def _is_desktop_attributable_endpoint(endpoint: str) -> bool:
    """Positive Docker Desktop ownership signal: the Docker Desktop Linux
    named-pipe endpoint (dockerDesktopLinuxEngine). A context name alone is not
    ownership evidence."""
    return "dockerdesktoplinuxengine" in endpoint.lower()


def _find_desktop_linux_context(run: Runner, docker: str) -> Optional[Dict[str, Any]]:
    """Find the Docker Desktop-owned Linux context without mutating the global
    context. A context is Desktop-owned only when its endpoint is positively
    attributable to Docker Desktop (the Docker Desktop Linux named-pipe
    endpoint). A context merely named ``desktop-linux`` with a custom or remote
    endpoint is NOT accepted as Desktop ownership evidence."""
    names = _list_context_names(run, docker)
    active = _active_context_name(run, docker)
    ordered: List[str] = []
    if active and active in names:
        ordered.append(active)
    ordered.extend(n for n in names if n not in ordered)
    for name in ordered:
        endpoint = _context_endpoint(run, docker, name)
        if _is_desktop_attributable_endpoint(endpoint):
            return {
                "name": name,
                "endpoint": endpoint,
                "active": name == active,
                "active_context_name": active,
                "ownership_signal": "docker-desktop-linux-named-pipe-endpoint",
            }
    return None


def _installed_desktop_evidence(run: Runner, docker: str) -> List[str]:
    """Read-only evidence that Docker Desktop itself is installed, for older
    Desktop versions where ``docker desktop status`` is unsupported."""
    evidence: List[str] = []
    r = run([docker, "desktop", "--help"], capture=True)
    if r.returncode == 0:
        evidence.append("docker-desktop-cli-plugin")
    r = run(["sc", "query", "com.docker.service"], capture=True)
    if r.returncode == 0:
        evidence.append("com.docker.service")
    return evidence


def probe_docker_desktop(
    run: Runner,
    *,
    no_start_docker_desktop: bool = False,
    start_timeout_s: float = DEFAULT_START_TIMEOUT_SECONDS,
) -> Dict[str, Any]:
    """Probe the Windows Docker Desktop candidate for actual usability.

    Requires *positive* Docker Desktop identity and records the Desktop-owned
    Linux context/endpoint as part of the immutable runtime decision. A custom
    or remote Windows Docker context that merely reaches a Linux daemon is
    rejected; the user's global Docker context is never mutated.

    Records distinct causes: ``docker_cli_missing``, ``desktop_identity_unsupported``,
    ``no_desktop_linux_context``, ``start_disabled``, ``start_failed``,
    ``start_timeout``, ``daemon_unavailable``, ``windows_container_mode``,
    ``compose_missing``.
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

    # ---- Positive Docker Desktop identity ----
    # Preferred: supported `docker desktop status --format json`. For older
    # Desktop versions, installed Desktop evidence plus a Desktop-owned Linux
    # context is required. An arbitrary custom/remote context is never accepted.
    status: Optional[Dict[str, Any]] = None
    r = run([docker, "desktop", "status", "--format", "json"], capture=True)
    if r.returncode == 0:
        try:
            status = json.loads(r.stdout)
            details["desktop_status"] = status
            details["desktop_identity"] = "desktop-status"
        except ValueError:
            diag.append("docker desktop status returned non-JSON output; requiring installed Desktop evidence")
    else:
        diag.append("docker desktop status --format json is unsupported; requiring installed Desktop evidence + Desktop-owned context")

    if details.get("desktop_identity") != "desktop-status":
        evidence = _installed_desktop_evidence(run, docker)
        details["desktop_installed_evidence"] = evidence
        if not evidence:
            return probe_result(
                "DockerDesktop", True, False, "desktop_identity_unsupported",
                diag + ["No supported docker desktop status and no installed Docker Desktop evidence "
                        "(docker desktop CLI plugin or com.docker.service). A custom/remote Windows "
                        "Docker context is not accepted as Docker Desktop."],
                details,
            )
        details["desktop_identity"] = "installed-evidence"

    # ---- Desktop-owned Linux context (never mutates the global context) ----
    ctx = _find_desktop_linux_context(run, docker)
    if not ctx:
        return probe_result(
            "DockerDesktop", True, False, "no_desktop_linux_context",
            diag + ["No Docker Desktop-owned Linux context (desktop-linux or a dockerDesktopLinuxEngine "
                    "endpoint) was found."],
            details,
        )
    details["selected_context"] = ctx["name"]
    details["context"] = ctx["name"]
    details["endpoint"] = ctx["endpoint"]
    details["context_is_active"] = ctx["active"]
    details["active_context"] = ctx.get("active_context_name")
    details["ownership_signal"] = ctx.get("ownership_signal")

    def _info_result() -> Tuple[bool, str]:
        """Return (ok, failure_reason). The daemon is queried through the
        recorded Desktop context explicitly."""
        r = run([docker, "--context", ctx["name"], "info"], capture=True)
        if r.returncode != 0:
            diag.append(f"docker --context {ctx['name']} info failed: {r.stderr.strip()[:200] or r.stdout.strip()[:200]}")
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
        diag.append(f"docker --context {ctx['name']} info succeeded with Linux containers")

    r = run([docker, "--context", ctx["name"], "compose", "version"], capture=True)
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


def _build_selected_metadata(selected: str, probes: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
    """Build top-level runtime metadata exclusively from the selected probe.

    A present-but-unhealthy nonselected candidate must not leak client, server,
    context, endpoint, or Compose values into the selected metadata. Candidate
    sub-objects remain labeled for diagnostics.
    """
    d = probes["DockerDesktop"]["details"]
    w = probes["WslEngine"]["details"]
    base: Dict[str, Any] = {
        "os_type": "windows" if os.name == "nt" else os.name,
        "selected_runtime": selected,
        "docker_desktop": {
            "context": d.get("selected_context") or d.get("context"),
            "endpoint": d.get("endpoint"),
            "active_context": d.get("active_context"),
            "context_is_active": d.get("context_is_active"),
            "ownership_signal": d.get("ownership_signal"),
            "desktop_status": d.get("desktop_status"),
            "desktop_identity": d.get("desktop_identity"),
            "desktop_installed_evidence": d.get("desktop_installed_evidence"),
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
    if selected == "DockerDesktop":
        base["client_version"] = d.get("client_version")
        base["server_version"] = d.get("server_version")
        base["server_os"] = d.get("server_os")
        base["compose_version"] = d.get("compose_version")
        base["context"] = d.get("selected_context") or d.get("context")
        base["endpoint"] = d.get("endpoint")
    else:
        base["client_version"] = w.get("client_version")
        base["server_version"] = w.get("server_version")
        base["server_os"] = w.get("server_os")
        base["compose_version"] = w.get("compose_version")
        base["context"] = None
        base["endpoint"] = None
        base["wsl_distribution"] = w.get("wsl_distribution")
        base["wsl_version"] = w.get("wsl_version")
    return base


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
            active_ctx = (desktop["details"].get("active_context") or "").lower()
            recorded_ctx = (desktop["details"].get("context") or "").lower()
            if active_ctx and recorded_ctx and active_ctx == recorded_ctx:
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
        selection["metadata"] = _build_selected_metadata(selected, probes)
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
        # Desktop mode pins the recorded context/endpoint as part of the
        # immutable runtime decision; every docker operation uses it explicitly.
        self._context: Optional[str] = None
        self._endpoint: Optional[str] = None
        if self.runtime == "DockerDesktop":
            meta = selection.get("metadata") or {}
            dd = meta.get("docker_desktop") or {}
            self._context = dd.get("context") or dd.get("selected_context")
            self._endpoint = dd.get("endpoint")

    @property
    def recorded_context(self) -> Optional[str]:
        return self._context

    @property
    def recorded_endpoint(self) -> Optional[str]:
        return self._endpoint

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
            base = ["docker"]
            if self._context:
                base += ["--context", self._context]
            return base + list(args)
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

    def verify_context(self) -> ProcResult:
        """Fail closed before significant operations.

        The recorded Desktop context must still exist, still be positively
        attributable to Docker Desktop, resolve to the recorded endpoint, and
        report a Linux daemon. A missing/changed context, a non-Desktop or
        redirected endpoint, or Windows containers aborts with non-zero. Uses
        ``self._run`` directly (never ``self.run``) so validation never
        recurses into itself.
        """
        if self.runtime != "DockerDesktop":
            return ProcResult(0, "", "")
        if not self._context:
            return ProcResult(2, "", "no recorded Docker Desktop context; refusing to run")
        r = self._run(
            ["docker", "context", "inspect", self._context, "--format", "{{.Endpoints.docker.Host}}"],
            capture=True,
        )
        if r.returncode != 0:
            return ProcResult(2, r.stdout, f"recorded Docker Desktop context {self._context!r} is missing")
        endpoint = r.stdout.strip()
        if not endpoint:
            return ProcResult(3, "", f"recorded Docker Desktop context {self._context!r} has no endpoint")
        if not _is_desktop_attributable_endpoint(endpoint):
            return ProcResult(
                3, "",
                f"recorded Docker Desktop context {self._context!r} endpoint {endpoint!r} "
                f"is not positively attributable to Docker Desktop",
            )
        if self._endpoint and endpoint != self._endpoint:
            return ProcResult(
                3, "",
                f"recorded Docker Desktop context {self._context!r} endpoint changed "
                f"from {self._endpoint!r} to {endpoint!r}",
            )
        r = self._run(["docker", "--context", self._context, "info"], capture=True)
        if r.returncode != 0:
            return ProcResult(4, r.stdout, f"docker --context {self._context!r} info failed")
        ostype, _server = parse_docker_info(r.stdout)
        if ostype and ostype != "linux":
            return ProcResult(
                5, "",
                f"recorded Docker Desktop context {self._context!r} reports {ostype!r} containers, not Linux",
            )
        return ProcResult(0, "", "")

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
        # Fail closed on every adapter-backed operation: the recorded Desktop
        # context must still exist, still be Desktop-attributable, still resolve
        # to the recorded endpoint, and still report a Linux daemon. This makes
        # direct helper execution (resolve_base_image, write_image_lock, image
        # inspect/tag, scans, builds, verification, cleanup) fail closed after
        # endpoint drift without a separate call site. verify_context uses
        # self._run directly, so this never recurses.
        if self.runtime == "DockerDesktop":
            check = self.verify_context()
            if check.returncode != 0:
                return ProcResult(check.returncode, check.stdout, check.stderr)
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


def _cli_verify_context(args: argparse.Namespace) -> int:
    selection = read_runtime_json(args.runtime_json)
    adapter = Adapter(selection, args.repo_root)
    result = adapter.verify_context()
    if result.returncode != 0:
        print(result.stderr or result.stdout, file=sys.stderr)
    return result.returncode


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

    p_verify = sub.add_parser(
        "verify-context",
        help="fail closed unless the recorded Desktop context still resolves to the recorded Linux endpoint",
    )
    p_verify.add_argument("--runtime-json", required=True)
    p_verify.add_argument("--repo-root", required=True)
    p_verify.set_defaults(func=_cli_verify_context)
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
