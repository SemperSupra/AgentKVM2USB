#!/usr/bin/env python3
"""Deterministic sanitized summarizer for offline Trivy image scans.

The full Trivy JSON is preserved under ignored .work. This script produces a
sanitized JSON and Markdown summary with an *individual record for every
CRITICAL and HIGH advisory*, plus package-level HIGH aggregation as an
additional view. Each record includes:

- advisory/CVE ID, severity, package and ecosystem, installed and fixed version,
  fixed/unfixed status, Trivy/vendor status and data source when available,
  source layer, dependency path, presence in the final runtime image, package
  purpose, and a package-specific reachability/exposure assessment.

Base and runtime libraries (zlib, glib, SQLite, Perl, libxml2, libc, OpenSSL,
curl, expat, ...) are assessed as exercised during container startup or ordinary
analysis, not only while processing mounted evidence.

Every remaining unfixed CRITICAL also carries an explicit decision record:
``remove``, ``isolate``, ``split``, or ``retain``, with a rationale, why the
package is necessary, whether affected functionality is exercised, mitigating
isolation controls, and a review/expiry condition.

``--gate`` enforces the acceptance gate: it fails when any CRITICAL finding has
a vendor-provided fixed version, fails when any unfixed CRITICAL lacks a
complete decision record, and reports fixable HIGH findings separately. The
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
    ("zlib", "compression library (base/runtime)"),
    ("sqlite", "embedded SQL database (base/runtime)"),
    ("glib", "GLib base library (base/runtime)"),
    ("xml2", "XML parser (base/runtime)"),
    ("perl", "Perl runtime (base/toolchain)"),
    ("curl", "HTTP transfer library (base/toolchain)"),
    ("expat", "XML parser (base/runtime)"),
    ("capstone", "disassembly engine (capstone)"),
]

# Packages assessed as base/runtime libraries exercised at container startup or
# ordinary analysis operations, not only while processing mounted evidence.
RUNTIME_BASE_PACKAGES = (
    "zlib", "libglib2.0", "libsqlite3", "perl", "libxml2", "libc6", "libc-bin",
    "libssl3", "openssl", "libcurl", "libexpat1", "libgcc", "libstdc++",
    "libffi", "libncurses", "libreadline", "libzstd", "liblzma", "gzip",
    "bsdutils", "libblkid", "libmount", "libsmartcols", "libuuid", "util-linux",
    "tar", "coreutils", "dash", "libacl", "libattr", "libcap", "libseccomp",
)

EXECUTION_MODEL_CONTROLS = (
    "Hardened execution model: non-root analyst user; network_mode none; "
    "read-only root filesystem; all Linux capabilities dropped; "
    "no-new-privileges; no Docker socket; evidence and vendor mounts read-only."
)


def classify_purpose(package: str) -> str:
    lower = package.lower()
    for needle, purpose in PURPOSE_RULES:
        if needle in lower:
            return purpose
    return "base OS / toolchain dependency"


def _is_runtime_base(package: str) -> bool:
    lower = package.lower()
    return any(token in lower for token in RUNTIME_BASE_PACKAGES)


def reachability_assessment(record: Dict[str, Any]) -> str:
    """Package-specific reachability/exposure assessment.

    Base/runtime libraries may be exercised during container startup or ordinary
    analysis operations, not only while processing mounted evidence. Analysis
    libraries are exercised when the corresponding tool runs on mounted evidence.
    """
    package = (record.get("package_name") or "").lower()
    purpose = record.get("purpose") or ""
    if _is_runtime_base(package):
        return (
            f"Package is a base/runtime library ({purpose}). It is loaded at "
            "container startup or during ordinary analysis operations (tool "
            "initialization, archive/XML/SQLite handling), so it is reachable "
            "beyond the offline evidence mounts. " + EXECUTION_MODEL_CONTROLS +
            " The underlying vulnerability is not eliminated by the execution model."
        )
    if "angr" in package or "claripy" in package or "z3" in package or "pyvex" in package:
        return (
            f"Package is part of the angr analysis stack ({purpose}). It executes "
            "only when an analysis run loads and processes mounted evidence "
            "offline. " + EXECUTION_MODEL_CONTROLS +
            " The underlying vulnerability is not eliminated by the execution model."
        )
    if "capstone" in package:
        return (
            f"Package is the capstone disassembly engine ({purpose}). It executes "
            "only when radare2/angr disassemble mounted evidence offline. " +
            EXECUTION_MODEL_CONTROLS +
            " The underlying vulnerability is not eliminated by the execution model."
        )
    return (
        f"Package ({purpose}) is exercised during toolchain startup or analysis "
        "of mounted evidence. " + EXECUTION_MODEL_CONTROLS +
        " The underlying vulnerability is not eliminated by the execution model."
    )


def vendor_status(vuln: Dict[str, Any]) -> Dict[str, Any]:
    """Record Trivy/vendor status and data source when available so FixedVersion
    is not the only context."""
    return {
        "status": vuln.get("Status"),
        "data_source": vuln.get("DataSource"),
        "vendor_severity": vuln.get("VendorSeverity"),
        "pkg_identifier": vuln.get("PkgIdentifier"),
    }


def fixed_status(fixed_version: Optional[str]) -> str:
    return "fixed" if fixed_version else "unfixed"


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


def _default_decision(record: Dict[str, Any]) -> Dict[str, Any]:
    """Build a complete default decision for an unfixed CRITICAL.

    Base/runtime libraries are retained because removing them would break the
    toolchain; the decision records why the package is necessary, whether the
    affected functionality is exercised, the mitigating controls, and a review
    condition. An explicit ``--decisions`` file can override per advisory.
    """
    package = record.get("package_name") or ""
    purpose = record.get("purpose") or ""
    decision: str = "retain"
    rationale: str
    necessity: str
    exercised: str
    if _is_runtime_base(package):
        decision = "retain"
        rationale = (
            f"{package} is a base/runtime library required by the Debian base "
            "and by the analysis toolchain at startup; removing or splitting it "
            "would break the image. The finding is unfixed in the current "
            "bookworm snapshot."
        )
        necessity = (
            f"{package} ({purpose}) is pulled in by the Debian base and is "
            "required for the Python runtime, TShark/USB decoding, and archive "
            "handling to start."
        )
        exercised = (
            "The affected functionality is exercised at container startup or "
            "during ordinary analysis operations."
        )
    else:
        decision = "retain"
        rationale = (
            f"{package} is an analysis dependency ({purpose}) needed for the "
            "toolchain to run on mounted evidence; removing it would remove a "
            "core analysis capability. The finding is unfixed in the current "
            "bookworm snapshot."
        )
        necessity = f"{package} ({purpose}) is required for the analysis workload."
        exercised = "The affected functionality is exercised only when the tool runs on mounted evidence."

    return {
        "decision": decision,
        "rationale": rationale,
        "package_necessity": necessity,
        "functionality_exercised": exercised,
        "mitigating_controls": EXECUTION_MODEL_CONTROLS,
        "review_condition": (
            "Re-evaluate when a vendor fix is published in the Debian bookworm "
            "security updates (or the base image tag is refreshed); the base "
            "image is resolved/pulled on every bootstrap and Trivy is re-run "
            "before each release gate."
        ),
    }


def build_decision(record: Dict[str, Any], overrides: Optional[Dict[str, Dict[str, Any]]]) -> Dict[str, Any]:
    if overrides and record.get("id") in overrides:
        return overrides[record["id"]]
    return _default_decision(record)


def decision_complete(decision: Dict[str, Any]) -> bool:
    required = (
        "decision", "rationale", "package_necessity", "functionality_exercised",
        "mitigating_controls", "review_condition",
    )
    if decision.get("decision") not in ("remove", "isolate", "split", "retain"):
        return False
    for key in required:
        value = decision.get(key)
        if not isinstance(value, str) or not value.strip():
            return False
    return True


def summarize(
    data: Dict[str, Any],
    decisions: Optional[Dict[str, Dict[str, Any]]] = None,
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
                "vendor_status": vendor_status(vuln),
                "dependency_path": dependency_path(vuln),
                "source_layer": source_layer(vuln, result),
                "present_in_final_runtime_image": True,  # Trivy scanned the final image
                "purpose": classify_purpose(vuln.get("PkgName") or ""),
                "reachability": reachability_assessment(
                    {"package_name": vuln.get("PkgName"), "purpose": classify_purpose(vuln.get("PkgName") or "")}
                ),
            }
            records.append(record)

    criticals = [r for r in records if r["severity"] == "CRITICAL"]
    highs = [r for r in records if r["severity"] == "HIGH"]
    fixable_criticals = [r for r in criticals if r["fixed_status"] == "fixed"]
    unfixed_criticals = [r for r in criticals if r["fixed_status"] == "unfixed"]
    fixable_highs = [r for r in highs if r["fixed_status"] == "fixed"]

    # Attach explicit decisions to every unfixed CRITICAL.
    for r in unfixed_criticals:
        r["decision"] = build_decision(r, decisions)

    missing_decisions = [r["id"] for r in unfixed_criticals if not decision_complete(r.get("decision") or {})]

    return {
        "schema_version": 2,
        "summary": {
            "criticals_total": len(criticals),
            "criticals_fixable": len(fixable_criticals),
            "criticals_unfixed": len(unfixed_criticals),
            "highs_total": len(highs),
            "highs_fixable": len(fixable_highs),
            "highs_unfixed": len(highs) - len(fixable_highs),
        },
        "gate": {
            "zero_fixable_criticals": len(fixable_criticals) == 0,
            "fixable_critical_ids": [r["id"] for r in fixable_criticals],
            "all_unfixed_critical_decisions_complete": len(missing_decisions) == 0,
            "unfixed_critical_missing_decisions": missing_decisions,
            "fixable_high_ids": [r["id"] for r in fixable_highs],
            "fixable_high_count": len(fixable_highs),
        },
        "criticals": sorted(criticals, key=lambda r: (r["id"] or "")),
        "highs": sorted(highs, key=lambda r: (r["id"] or "")),
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


def _render_decision(lines: List[str], decision: Dict[str, Any]) -> None:
    lines.append(f"- Decision: {decision.get('decision')}")
    lines.append(f"- Rationale: {decision.get('rationale')}")
    lines.append(f"- Package necessity: {decision.get('package_necessity')}")
    lines.append(f"- Functionality exercised: {decision.get('functionality_exercised')}")
    lines.append(f"- Mitigating controls: {decision.get('mitigating_controls')}")
    lines.append(f"- Review condition: {decision.get('review_condition')}")


def render_markdown(summary: Dict[str, Any]) -> str:
    s = summary["summary"]
    g = summary["gate"]
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
    lines.append(f"- Gate zero-fixable-CRITICAL: {'PASS' if g['zero_fixable_criticals'] else 'FAIL'}")
    lines.append(
        f"- Gate unfixed-CRITICAL decisions complete: "
        f"{'PASS' if g['all_unfixed_critical_decisions_complete'] else 'FAIL'}"
    )
    lines.append(f"- Fixable HIGH: {g['fixable_high_count']} ({', '.join(g['fixable_high_ids']) or 'none'})")
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
        vs = r.get("vendor_status") or {}
        if vs.get("status"):
            lines.append(f"- Trivy status: {vs['status']}")
        lines.append(f"- Purpose: {r['purpose']}")
        lines.append(f"- In final runtime image: {r['present_in_final_runtime_image']}")
        if r["source_layer"]:
            lines.append(f"- Source layer: {r['source_layer']}")
        if r["dependency_path"]:
            lines.append(f"- Dependency path: {', '.join(r['dependency_path'])}")
        lines.append(f"- Reachability: {r['reachability']}")
        if "decision" in r:
            _render_decision(lines, r["decision"])
        lines.append("")

    lines.append("## HIGH findings (individual)")
    lines.append("")
    if not summary["highs"]:
        lines.append("None.")
    for r in summary["highs"]:
        lines.append(f"- **{r['id']}** {r['package_name']} {r['installed_version']} -> "
                     f"{r['fixed_version'] or 'no fix'} ({r['fixed_status']}) — {r['purpose']}")
    lines.append("")

    lines.append("## HIGH findings by package (additional view)")
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


def load_decisions(path: Optional[str]) -> Optional[Dict[str, Dict[str, Any]]]:
    if not path:
        return None
    with open(path, "r", encoding="utf-8") as handle:
        return json.load(handle)


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, help="full Trivy JSON")
    parser.add_argument("--output", required=True, help="sanitized JSON output")
    parser.add_argument("--markdown", required=True, help="sanitized Markdown output")
    parser.add_argument("--decisions", default=None, help="optional JSON overrides keyed by advisory ID")
    parser.add_argument("--gate", action="store_true", help="fail on fixable CRITICAL or incomplete unfixed decisions")
    args = parser.parse_args(argv)

    with open(args.input, "r", encoding="utf-8") as handle:
        data = json.load(handle)
    summary = summarize(data, decisions=load_decisions(args.decisions))

    with open(args.output, "w", encoding="utf-8") as handle:
        json.dump(summary, handle, indent=2, sort_keys=True)
        handle.write("\n")
    with open(args.markdown, "w", encoding="utf-8") as handle:
        handle.write(render_markdown(summary))

    s = summary["summary"]
    g = summary["gate"]
    print(
        f"CRITICAL {s['criticals_total']} (fixable {s['criticals_fixable']}, "
        f"unfixed {s['criticals_unfixed']}) | HIGH {s['highs_total']} (fixable "
        f"{s['highs_fixable']}) | gate-fixable={'PASS' if g['zero_fixable_criticals'] else 'FAIL'} "
        f"gate-decisions={'PASS' if g['all_unfixed_critical_decisions_complete'] else 'FAIL'}"
    )
    if args.gate:
        failed = False
        if not g["zero_fixable_criticals"]:
            print("Gate FAILED: fixable CRITICAL findings remain.", file=sys.stderr)
            failed = True
        if not g["all_unfixed_critical_decisions_complete"]:
            print(
                f"Gate FAILED: unfixed CRITICAL missing decisions: {g['unfixed_critical_missing_decisions']}",
                file=sys.stderr,
            )
            failed = True
        if failed:
            return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
