#!/usr/bin/env python3
"""Deterministic sanitized summarizer for offline Trivy image scans.

The full Trivy JSON is preserved under ignored .work. This script produces a
sanitized JSON and Markdown summary covering every CRITICAL and HIGH finding
with the fields required by the issue #14 hardening review:

- advisory/CVE ID, severity, package name, ecosystem, installed/fixed version,
  fixed vs unfixed status, dependency path / source layer when available,
  presence in the final runtime image, package purpose, and a short exposure
  note reflecting the container execution model (non-root, no runtime network,
  read-only root, all capabilities dropped, no-new-privileges, no Docker
  socket, read-only evidence mounts).

``--gate`` implements the acceptance gate: it exits non-zero when any CRITICAL
finding has a vendor-provided fixed version available (i.e. it is fixable). The
summary never claims that runtime hardening eliminates an underlying
vulnerability.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from typing import Any, Dict, List, Optional

EXECUTION_MODEL_NOTE = (
    "Execution model: non-root analyst user; network_mode none; read-only root "
    "filesystem; all Linux capabilities dropped; no-new-privileges; no Docker "
    "socket; evidence and vendor mounts read-only. The affected package is only "
    "reachable through offline analysis of mounted evidence; this does not "
    "eliminate the underlying vulnerability."
)

# Purpose heuristics keyed by package name substrings, ordered longest-first so
# more specific names win.
PURPOSE_RULES: List[tuple[str, str]] = [
    ("angr", "angr symbolic/static analysis (SMT-based)"),
    ("claripy", "angr constraint solver backend"),
    ("pyvex", "angr VEX IR lifters"),
    ("cle", "angr binary loader"),
    ("archinfo", "angr architecture metadata"),
    ("angr-data", "angr bundled analysis data"),
    ("capstone", "disassembly engine (capstone)"),
    ("z3", "SMT solver (Z3) used by angr"),
    ("pyusb", "USB device access (libusb binding)"),
    ("scapy", "packet parsing (USB capture decode)"),
    ("pyshark", "Wireshark capture parsing"),
    ("tshark", "USB trace decoding (TShark)"),
    ("wireshark", "USB trace decoding (Wireshark libs)"),
    ("yara", "signature scanning"),
    ("binutils", "GNU binary utilities (ARM analysis)"),
    ("qemu", "QEMU user-mode emulation (ARM execution)"),
    ("gdb", "GNU debugger (multiarch)"),
    ("libusb", "USB host library"),
    ("python", "Python runtime / standard library"),
    ("openssl", "TLS/crypto library"),
    ("libc", "C standard library"),
]


def classify_purpose(package: str) -> str:
    lower = package.lower()
    for needle, purpose in PURPOSE_RULES:
        if needle in lower:
            return purpose
    return "base OS / toolchain dependency"


def fixed_status(fixed_version: Optional[str]) -> str:
    return "fixed" if fixed_version else "unfixed"


def exposure_note(record: Dict[str, Any]) -> str:
    return EXECUTION_MODEL_NOTE


def source_layer(vuln: Dict[str, Any], result: Dict[str, Any]) -> Optional[str]:
    layer = vuln.get("Layer") or {}
    if layer.get("DiffID"):
        return layer["DiffID"]
    source = result.get("Source") or {}
    if source.get("ID"):
        return source["ID"]
    return None


def dependency_path(vuln: Dict[str, Any]) -> Optional[List[str]]:
    paths = vuln.get("Paths") or []
    return paths or None


def summarize(
    data: Dict[str, Any],
) -> Dict[str, Any]:
    records: List[Dict[str, Any]] = []
    for result in data.get("Results", []):
        vulns = result.get("Vulnerabilities") or []
        pkg_class = result.get("Class", "unknown")
        pkg_type = result.get("Type", "unknown")
        ecosystem = f"{pkg_type}" if pkg_class == "lang-pkgs" else pkg_type
        for vuln in vulns:
            severity = (vuln.get("Severity") or "UNKNOWN").upper()
            if severity not in ("CRITICAL", "HIGH"):
                continue
            fixed = vuln.get("FixedVersion") or ""
            record = {
                "id": vuln.get("VulnerabilityID"),
                "severity": severity,
                "package_name": vuln.get("PkgName"),
                "ecosystem": ecosystem,
                "installed_version": vuln.get("InstalledVersion"),
                "fixed_version": fixed or None,
                "fixed_status": fixed_status(fixed),
                "dependency_path": dependency_path(vuln),
                "source_layer": source_layer(vuln, result),
                "present_in_final_runtime_image": True,  # Trivy scanned the final image
                "purpose": classify_purpose(vuln.get("PkgName") or ""),
                "exposure_note": exposure_note(vuln),
            }
            records.append(record)

    criticals = [r for r in records if r["severity"] == "CRITICAL"]
    highs = [r for r in records if r["severity"] == "HIGH"]
    fixable_criticals = [r for r in criticals if r["fixed_status"] == "fixed"]

    return {
        "schema_version": 1,
        "summary": {
            "criticals_total": len(criticals),
            "criticals_fixable": len(fixable_criticals),
            "criticals_unfixed": len(criticals) - len(fixable_criticals),
            "highs_total": len(highs),
            "highs_fixable": sum(1 for r in highs if r["fixed_status"] == "fixed"),
            "highs_unfixed": sum(1 for r in highs if r["fixed_status"] == "unfixed"),
        },
        "gate": {
            "zero_fixable_criticals": len(fixable_criticals) == 0,
            "fixable_critical_ids": [r["id"] for r in fixable_criticals],
        },
        "criticals": sorted(criticals, key=lambda r: (r["id"] or "")),
        "highs_by_package": _aggregate_highs(highs),
    }


def _aggregate_highs(highs: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    by_pkg: Dict[str, List[Dict[str, Any]]] = {}
    for r in highs:
        by_pkg.setdefault(r["package_name"], []).append(r)
    agg: List[Dict[str, Any]] = []
    for pkg in sorted(by_pkg):
        recs = by_pkg[pkg]
        agg.append(
            {
                "package_name": pkg,
                "ecosystem": recs[0]["ecosystem"],
                "installed_version": recs[0]["installed_version"],
                "purpose": recs[0]["purpose"],
                "findings": len(recs),
                "fixable": sum(1 for r in recs if r["fixed_status"] == "fixed"),
                "unfixed": sum(1 for r in recs if r["fixed_status"] == "unfixed"),
                "remediation_status": "has-fixes" if any(r["fixed_status"] == "fixed" for r in recs) else "unfixed",
                "ids": sorted(r["id"] for r in recs),
            }
        )
    return agg


def render_markdown(summary: Dict[str, Any]) -> str:
    s = summary["summary"]
    lines: List[str] = []
    lines.append("# Trivy vulnerability triage (sanitized)")
    lines.append("")
    lines.append("## Summary")
    lines.append("")
    lines.append(
        f"- CRITICAL: {s['criticals_total']} total, {s['criticals_fixable']} fixable, "
        f"{s['criticals_unfixed']} unfixed"
    )
    lines.append(
        f"- HIGH: {s['highs_total']} total, {s['highs_fixable']} fixable, {s['highs_unfixed']} unfixed"
    )
    lines.append(f"- Gate (zero fixable CRITICAL): {'PASS' if summary['gate']['zero_fixable_criticals'] else 'FAIL'}")
    lines.append("")

    lines.append("## CRITICAL findings")
    lines.append("")
    if not summary["criticals"]:
        lines.append("None.")
    for r in summary["criticals"]:
        lines.append(f"### {r['id']} — {r['package_name']}")
        lines.append("")
        lines.append(f"- Severity: {r['severity']}")
        lines.append(f"- Package: {r['package_name']} ({r['ecosystem']})")
        lines.append(f"- Installed: {r['installed_version']}")
        lines.append(f"- Fixed version: {r['fixed_version'] or 'none available'}")
        lines.append(f"- Status: {r['fixed_status']}")
        lines.append(f"- Purpose: {r['purpose']}")
        lines.append(f"- In final runtime image: {r['present_in_final_runtime_image']}")
        if r["source_layer"]:
            lines.append(f"- Source layer: {r['source_layer']}")
        if r["dependency_path"]:
            lines.append(f"- Dependency path: {', '.join(r['dependency_path'])}")
        lines.append(f"- Exposure: {r['exposure_note']}")
        lines.append("")

    lines.append("## HIGH findings by package")
    lines.append("")
    if not summary["highs_by_package"]:
        lines.append("None.")
    for agg in summary["highs_by_package"]:
        lines.append(
            f"- **{agg['package_name']}** ({agg['ecosystem']}, installed {agg['installed_version']}): "
            f"{agg['findings']} findings, {agg['fixable']} fixable, {agg['unfixed']} unfixed "
            f"({agg['remediation_status']}) — {agg['purpose']}"
        )
    lines.append("")
    lines.append("> This summary does not claim that runtime hardening eliminates an "
                 "underlying vulnerability; it reflects the hardened execution model only.")
    return "\n".join(lines)


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, help="full Trivy JSON")
    parser.add_argument("--output", required=True, help="sanitized JSON output")
    parser.add_argument("--markdown", required=True, help="sanitized Markdown output")
    parser.add_argument("--gate", action="store_true", help="exit non-zero if any fixable CRITICAL exists")
    args = parser.parse_args(argv)

    with open(args.input, "r", encoding="utf-8") as handle:
        data = json.load(handle)
    summary = summarize(data)

    with open(args.output, "w", encoding="utf-8") as handle:
        json.dump(summary, handle, indent=2, sort_keys=True)
        handle.write("\n")
    with open(args.markdown, "w", encoding="utf-8") as handle:
        handle.write(render_markdown(summary))

    s = summary["summary"]
    print(
        f"CRITICAL {s['criticals_total']} (fixable {s['criticals_fixable']}, "
        f"unfixed {s['criticals_unfixed']}) | HIGH {s['highs_total']} | "
        f"gate={'PASS' if summary['gate']['zero_fixable_criticals'] else 'FAIL'}"
    )
    if args.gate and not summary["gate"]["zero_fixable_criticals"]:
        print("Gate FAILED: fixable CRITICAL findings remain.", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
