#!/usr/bin/env python3
"""Deterministic sanitized summarizer and acceptance gate for Trivy scans.

The full Trivy JSON is preserved under ignored .work. This script produces a
sanitized JSON and Markdown summary with an *individual record for every
CRITICAL and HIGH advisory*, plus package-level HIGH aggregation as an
additional view.

Explicit vulnerability acceptance
--------------------------------
Acceptance of an unfixed CRITICAL requires an exact, explicit policy entry from
a tracked policy file (default ``containers/re-runner/vulnerability-acceptance.json``).
A policy entry matches only when all four identity fields agree:

- advisory/CVE ID
- package name
- ecosystem
- installed version

Each policy entry must carry: decision (``remove`` | ``isolate`` | ``split`` |
``retain``), rationale, package necessity, whether affected functionality is
exercised, mitigating controls, a review date, and a review condition/expiry
trigger.

Generated default text is emitted only as a non-gating *recommendation* and
never satisfies the gate. The gate fails when:

- any CRITICAL finding has a vendor-provided fixed version (fixable);
- any unfixed CRITICAL lacks an exact policy match (missing, or a mismatch on
  advisory/package/ecosystem/installed version);
- any policy entry is incomplete;
- any policy entry is stale or orphaned (no longer matches a scanned CRITICAL);
- a previously accepted vulnerability now has a fixed version.

Package classification
----------------------
Package purpose and runtime/base classification use exact normalized names and
boundary-safe family patterns, never unrestricted substring matching. In
particular ``libcapstone4`` is classified as the Capstone disassembly engine and
is never matched by the base ``libcap`` token; ``libc6``/``libc-bin``, ``tar``,
and ``dash`` are exact base/runtime names.

The summary never claims that runtime hardening eliminates an underlying
vulnerability.
"""

from __future__ import annotations

import argparse
import json
import os
import pathlib
import re
import sys
from typing import Any, Dict, List, Optional, Tuple

# --------------------------------------------------------------------------- classification

# Exact package name -> (purpose, runtime_base, family).
EXACT_PACKAGE_CLASS: Dict[str, Tuple[str, bool, str]] = {
    # Capstone disassembly engine (analysis).
    "libcapstone4": ("capstone disassembly engine (used by angr/radare2 disassembly)", False, "capstone"),
    "capstone": ("capstone disassembly engine (used by angr/radare2 disassembly)", False, "capstone"),
    # angr analysis stack.
    "angr": ("angr symbolic/static analysis (SMT-based)", False, "angr"),
    "claripy": ("angr constraint solver backend", False, "angr"),
    "pyvex": ("angr VEX IR lifters", False, "angr"),
    "cle": ("angr binary loader", False, "angr"),
    "archinfo": ("angr architecture metadata", False, "angr"),
    "angr-data": ("angr bundled analysis data", False, "angr"),
    "z3-solver": ("SMT solver (Z3) used by angr", False, "angr"),
    # Python analysis libraries.
    "python": ("Python runtime / standard library", True, "runtime-base"),
    "pyusb": ("USB device access (libusb binding)", False, "analysis"),
    "scapy": ("packet parsing (USB capture decode)", False, "analysis"),
    "r2pipe": ("radare2 pipe binding", False, "analysis"),
    # Base / runtime libraries (exact names only; never unrestricted substrings).
    "zlib1g": ("compression library (zlib, base/runtime)", True, "runtime-base"),
    "libglib2.0-0": ("GLib base library (base/runtime)", True, "runtime-base"),
    "libsqlite3-0": ("embedded SQL database (SQLite, base/runtime)", True, "runtime-base"),
    "libxml2": ("XML parser (libxml2, base/runtime)", True, "runtime-base"),
    "perl-base": ("Perl runtime (base/toolchain)", True, "runtime-base"),
    "libc6": ("C standard library (base/runtime)", True, "runtime-base"),
    "libc-bin": ("C standard library (base/runtime)", True, "runtime-base"),
    "libcap": ("Linux capabilities library (base/runtime)", True, "runtime-base"),
    "tar": ("GNU tar archive utility (base/runtime)", True, "runtime-base"),
    "dash": ("POSIX shell (base/runtime)", True, "runtime-base"),
    "libcurl3-gnutls": ("HTTP transfer library (base/toolchain)", True, "runtime-base"),
    "libexpat1": ("XML parser (expat, base/runtime)", True, "runtime-base"),
    "libssl3": ("TLS/crypto library (OpenSSL, base/runtime)", True, "runtime-base"),
    "openssl": ("TLS/crypto library (base/runtime)", True, "runtime-base"),
    "libzstd1": ("Zstandard compression (base/runtime)", True, "runtime-base"),
    "liblzma5": ("XZ compression (base/runtime)", True, "runtime-base"),
    "gzip": ("gzip compression utility (base/runtime)", True, "runtime-base"),
    "bsdutils": ("base utilities (base/runtime)", True, "runtime-base"),
    "util-linux": ("base utilities (base/runtime)", True, "runtime-base"),
    "libblkid1": ("block device id library (base/runtime)", True, "runtime-base"),
    "libmount1": ("mount library (base/runtime)", True, "runtime-base"),
    "libsmartcols1": ("column table library (base/runtime)", True, "runtime-base"),
    "libuuid1": ("UUID library (base/runtime)", True, "runtime-base"),
    "libacl1": ("access control list library (base/runtime)", True, "runtime-base"),
    "libattr1": ("extended attribute library (base/runtime)", True, "runtime-base"),
    "libseccomp2": ("seccomp library (base/runtime)", True, "runtime-base"),
    "libgcc-s1": ("GCC support library (base/runtime)", True, "runtime-base"),
    "libstdc++6": ("GCC C++ standard library (base/runtime)", True, "runtime-base"),
    "libffi8": ("FFI library (base/runtime)", True, "runtime-base"),
    "libncurses6": ("terminal handling library (base/runtime)", True, "runtime-base"),
    "libreadline8": ("line editing library (base/runtime)", True, "runtime-base"),
    "libpcre2-8-0": ("PCRE2 regex library (base/runtime)", True, "runtime-base"),
}

# Boundary-safe family patterns: (compiled regex, purpose, runtime_base, family).
# Anchored, so a family token cannot capture a sibling package (libcap != libcapstone).
FAMILY_PACKAGE_CLASS: List[Tuple[re.Pattern, str, bool, str]] = [
    (re.compile(r"^libcapstone[0-9][0-9a-z.-]*$"),
     "capstone disassembly engine (used by angr/radare2 disassembly)", False, "capstone"),
    (re.compile(r"^libcap2(-bin|-dev)?$"),
     "Linux capabilities library (base/runtime)", True, "runtime-base"),
    (re.compile(r"^libc6(-dev|-bin)?$"),
     "C standard library (base/runtime)", True, "runtime-base"),
    (re.compile(r"^zlib1g[0-9a-z.-]*$"),
     "compression library (zlib, base/runtime)", True, "runtime-base"),
    (re.compile(r"^libglib2\.0-[0-9a-z.-]*$"),
     "GLib base library (base/runtime)", True, "runtime-base"),
    (re.compile(r"^libsqlite3-[0-9a-z.-]*$"),
     "embedded SQL database (SQLite, base/runtime)", True, "runtime-base"),
    (re.compile(r"^libxml2[0-9a-z.-]*$"),
     "XML parser (libxml2, base/runtime)", True, "runtime-base"),
    (re.compile(r"^perl(-[0-9a-z.-]+)?$"),
     "Perl runtime (base/toolchain)", True, "runtime-base"),
    (re.compile(r"^libcurl[0-9a-z.-]*$"),
     "HTTP transfer library (base/toolchain)", True, "runtime-base"),
    (re.compile(r"^libexpat1[0-9a-z.-]*$"),
     "XML parser (expat, base/runtime)", True, "runtime-base"),
    (re.compile(r"^libssl3?[0-9a-z.-]*$"),
     "TLS/crypto library (OpenSSL, base/runtime)", True, "runtime-base"),
]


def classify_package(package: str) -> Tuple[str, bool, str]:
    """Return ``(purpose, runtime_base, family)``.

    Exact normalized name lookup first, then anchored boundary-safe family
    patterns, then a default. Never unrestricted substring matching.
    """
    name = (package or "").strip().lower()
    if name in EXACT_PACKAGE_CLASS:
        return EXACT_PACKAGE_CLASS[name]
    for pattern, purpose, runtime_base, family in FAMILY_PACKAGE_CLASS:
        if pattern.match(name):
            return purpose, runtime_base, family
    return "base OS / toolchain dependency", True, "other"


def classify_purpose(package: str) -> str:
    return classify_package(package)[0]


def is_runtime_base(package: str) -> bool:
    return classify_package(package)[1]


# --------------------------------------------------------------------------- policy

POLICY_REQUIRED = (
    "advisory_id", "package", "ecosystem", "installed_version", "decision",
    "rationale", "package_necessity", "functionality_exercised",
    "mitigating_controls", "review_date", "review_condition",
)

ALLOWED_DECISIONS = ("remove", "isolate", "split", "retain")

DEFAULT_POLICY_PATH = os.path.join("containers", "re-runner", "vulnerability-acceptance.json")


def policy_key(entry: Dict[str, Any]) -> Tuple[str, str, str, str]:
    return (
        str(entry.get("advisory_id") or ""),
        str(entry.get("package") or ""),
        str(entry.get("ecosystem") or ""),
        str(entry.get("installed_version") or ""),
    )


def scan_key(record: Dict[str, Any]) -> Tuple[str, str, str, str]:
    return (
        str(record.get("id") or ""),
        str(record.get("package_name") or ""),
        str(record.get("ecosystem") or ""),
        str(record.get("installed_version") or ""),
    )


def policy_entry_complete(entry: Dict[str, Any]) -> bool:
    if entry.get("decision") not in ALLOWED_DECISIONS:
        return False
    for key in POLICY_REQUIRED:
        value = entry.get(key)
        if not isinstance(value, str) or not value.strip():
            return False
    return True


def load_policy(source: Any) -> List[Dict[str, Any]]:
    """Accept a list of entries, a dict with an ``entries`` array, a single
    entry dict, or a path to a JSON file with either shape."""
    if source is None:
        return []
    if isinstance(source, list):
        return list(source)
    if isinstance(source, dict):
        if "entries" in source:
            return list(source["entries"])
        return [source]
    # Treat as a path.
    path = str(source)
    with open(path, "r", encoding="utf-8") as handle:
        data = json.load(handle)
    if isinstance(data, list):
        return list(data)
    if isinstance(data, dict) and "entries" in data:
        return list(data["entries"])
    raise ValueError(f"unsupported policy file shape in {path}")


def generate_recommendation(record: Dict[str, Any]) -> Dict[str, Any]:
    """Non-gating generated suggestion. Never satisfies the acceptance gate."""
    package = record.get("package_name") or ""
    purpose = record.get("purpose") or ""
    return {
        "decision": "retain (generated suggestion — NOT an accepted policy decision)",
        "rationale": (
            f"Generated default for {package} ({purpose}); the finding is unfixed in "
            "the current snapshot. Add an explicit policy entry before acceptance."
        ),
    }


def _partial_match_reason(record: Dict[str, Any], entries: List[Dict[str, Any]]) -> Optional[str]:
    """Return a reason when a policy entry partially matches (same advisory but a
    mismatched package/ecosystem/version), so the failure is actionable."""
    for entry in entries:
        if str(entry.get("advisory_id") or "") != str(record.get("id") or ""):
            continue
        if str(entry.get("package") or "") != str(record.get("package_name") or ""):
            return f"policy package {entry.get('package')!r} != scan package {record.get('package_name')!r}"
        if str(entry.get("ecosystem") or "") != str(record.get("ecosystem") or ""):
            return f"policy ecosystem {entry.get('ecosystem')!r} != scan ecosystem {record.get('ecosystem')!r}"
        if str(entry.get("installed_version") or "") != str(record.get("installed_version") or ""):
            return f"policy installed version {entry.get('installed_version')!r} != scan version {record.get('installed_version')!r}"
    return None


def evaluate_policy(
    unfixed_criticals: List[Dict[str, Any]],
    fixable_criticals: List[Dict[str, Any]],
    policy_entries: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """Attach explicit policy decisions to every unfixed CRITICAL and compute the
    gate result. An exact (advisory, package, ecosystem, installed version) match
    is required; generated recommendations are non-gating."""
    index = {policy_key(e): e for e in policy_entries}
    failures: List[Dict[str, Any]] = []
    for record in unfixed_criticals:
        key = scan_key(record)
        entry = index.get(key)
        if entry is None:
            partial = _partial_match_reason(record, policy_entries)
            if partial:
                record["policy"] = {
                    "matched": False,
                    "match_kind": "mismatch",
                    "reason": partial,
                    "decision": None,
                    "recommendation": generate_recommendation(record),
                }
                failures.append({
                    "id": record["id"], "package": record["package_name"],
                    "ecosystem": record["ecosystem"], "installed_version": record["installed_version"],
                    "reason": partial,
                })
            else:
                record["policy"] = {
                    "matched": False,
                    "match_kind": "missing",
                    "reason": "no explicit policy entry for this advisory/package/ecosystem/version",
                    "decision": None,
                    "recommendation": generate_recommendation(record),
                }
                failures.append({
                    "id": record["id"], "package": record["package_name"],
                    "ecosystem": record["ecosystem"], "installed_version": record["installed_version"],
                    "reason": "missing policy entry",
                })
            continue
        if not policy_entry_complete(entry):
            record["policy"] = {
                "matched": False,
                "match_kind": "incomplete",
                "reason": "policy entry is missing required fields",
                "decision": None,
                "recommendation": generate_recommendation(record),
            }
            failures.append({
                "id": record["id"], "package": record["package_name"],
                "ecosystem": record["ecosystem"], "installed_version": record["installed_version"],
                "reason": "incomplete policy entry",
            })
            continue
        record["policy"] = {
            "matched": True,
            "match_kind": "exact",
            "reason": "explicit policy entry matched advisory/package/ecosystem/installed version",
            "decision": {k: entry[k] for k in POLICY_REQUIRED},
        }

    # Stale / orphaned / newly-fixable policy entries.
    used_keys = {scan_key(r) for r in unfixed_criticals}
    fixable_by_identity = {
        (r["id"], r["package_name"], r["ecosystem"]) for r in fixable_criticals
    }
    stale: List[Dict[str, Any]] = []
    newly_fixable: List[Dict[str, Any]] = []
    for entry in policy_entries:
        key = policy_key(entry)
        if key in used_keys:
            continue
        identity = (entry.get("advisory_id"), entry.get("package"), entry.get("ecosystem"))
        if identity in fixable_by_identity:
            newly_fixable.append(
                {"advisory_id": entry["advisory_id"], "package": entry["package"],
                 "ecosystem": entry["ecosystem"], "installed_version": entry["installed_version"]}
            )
        else:
            stale.append(
                {"advisory_id": entry["advisory_id"], "package": entry["package"],
                 "ecosystem": entry["ecosystem"], "installed_version": entry["installed_version"]}
            )

    all_matched = len(failures) == 0
    return {
        "all_unfixed_critical_policy_matched": all_matched,
        "unfixed_critical_policy_failures": failures,
        "stale_policy_entries": stale,
        "newly_fixable_accepted": newly_fixable,
    }


# --------------------------------------------------------------------------- records


def vendor_status(vuln: Dict[str, Any]) -> Dict[str, Any]:
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


EXECUTION_MODEL_CONTROLS = (
    "Hardened execution model: non-root analyst user; network_mode none; "
    "read-only root filesystem; all Linux capabilities dropped; "
    "no-new-privileges; no Docker socket; evidence and vendor mounts read-only."
)


def reachability_assessment(record: Dict[str, Any]) -> str:
    """Package-specific reachability/exposure assessment driven by the
    boundary-safe family classification."""
    family = record.get("family") or classify_package(record.get("package_name") or "")[2]
    purpose = record.get("purpose") or ""
    if family == "capstone":
        return (
            f"Package is the Capstone disassembly engine ({purpose}). It executes "
            "only when angr/radare2 disassemble mounted evidence offline. " +
            EXECUTION_MODEL_CONTROLS +
            " The underlying vulnerability is not eliminated by the execution model."
        )
    if family == "angr":
        return (
            f"Package is part of the angr analysis stack ({purpose}). It executes "
            "only when an analysis run loads and processes mounted evidence "
            "offline. " + EXECUTION_MODEL_CONTROLS +
            " The underlying vulnerability is not eliminated by the execution model."
        )
    if family == "runtime-base" or is_runtime_base(record.get("package_name") or ""):
        return (
            f"Package is a base/runtime library ({purpose}). It is loaded at "
            "container startup or during ordinary analysis operations (tool "
            "initialization, archive/XML/SQLite handling), so it is reachable "
            "beyond the offline evidence mounts. " + EXECUTION_MODEL_CONTROLS +
            " The underlying vulnerability is not eliminated by the execution model."
        )
    return (
        f"Package ({purpose}) is exercised during toolchain startup or analysis "
        "of mounted evidence. " + EXECUTION_MODEL_CONTROLS +
        " The underlying vulnerability is not eliminated by the execution model."
    )


def build_record(vuln: Dict[str, Any], result: Dict[str, Any]) -> Dict[str, Any]:
    fixed = vuln.get("FixedVersion") or ""
    pkg = vuln.get("PkgName") or ""
    purpose, _runtime, family = classify_package(pkg)
    record = {
        "id": vuln.get("VulnerabilityID"),
        "severity": (vuln.get("Severity") or "UNKNOWN").upper(),
        "package_name": pkg,
        "ecosystem": result.get("Type", "unknown"),
        "installed_version": vuln.get("InstalledVersion"),
        "fixed_version": fixed or None,
        "fixed_status": fixed_status(fixed),
        "vendor_status": vendor_status(vuln),
        "dependency_path": dependency_path(vuln),
        "source_layer": source_layer(vuln, result),
        "present_in_final_runtime_image": True,  # Trivy scanned the final image
        "purpose": purpose,
        "family": family,
        "reachability": reachability_assessment({"package_name": pkg, "purpose": purpose, "family": family}),
    }
    return record


def summarize(
    data: Dict[str, Any],
    policy: Optional[Any] = None,
) -> Dict[str, Any]:
    records: List[Dict[str, Any]] = []
    for result in data.get("Results", []):
        vulns = result.get("Vulnerabilities") or []
        for vuln in vulns:
            severity = (vuln.get("Severity") or "UNKNOWN").upper()
            if severity not in ("CRITICAL", "HIGH"):
                continue
            records.append(build_record(vuln, result))

    criticals = [r for r in records if r["severity"] == "CRITICAL"]
    highs = [r for r in records if r["severity"] == "HIGH"]
    fixable_criticals = [r for r in criticals if r["fixed_status"] == "fixed"]
    unfixed_criticals = [r for r in criticals if r["fixed_status"] == "unfixed"]
    fixable_highs = [r for r in highs if r["fixed_status"] == "fixed"]

    policy_entries = load_policy(policy) if policy is not None else []
    policy_result = evaluate_policy(unfixed_criticals, fixable_criticals, policy_entries)

    gate_ok = (
        len(fixable_criticals) == 0
        and policy_result["all_unfixed_critical_policy_matched"]
        and len(policy_result["stale_policy_entries"]) == 0
        and len(policy_result["newly_fixable_accepted"]) == 0
    )

    return {
        "schema_version": 3,
        "summary": {
            "criticals_total": len(criticals),
            "criticals_fixable": len(fixable_criticals),
            "criticals_unfixed": len(unfixed_criticals),
            "highs_total": len(highs),
            "highs_fixable": len(fixable_highs),
            "highs_unfixed": len(highs) - len(fixable_highs),
        },
        "gate": {
            "ok": gate_ok,
            "zero_fixable_criticals": len(fixable_criticals) == 0,
            "fixable_critical_ids": [r["id"] for r in fixable_criticals],
            "all_unfixed_critical_policy_matched": policy_result["all_unfixed_critical_policy_matched"],
            "unfixed_critical_policy_failures": policy_result["unfixed_critical_policy_failures"],
            "stale_policy_entries": policy_result["stale_policy_entries"],
            "newly_fixable_accepted": policy_result["newly_fixable_accepted"],
            "fixable_high_ids": [r["id"] for r in fixable_highs],
            "fixable_high_count": len(fixable_highs),
        },
        "policy": {
            "source": "explicit policy file" if policy_entries else "none",
            "entry_count": len(policy_entries),
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


# --------------------------------------------------------------------------- markdown


def _render_decision(lines: List[str], decision: Dict[str, Any]) -> None:
    lines.append(f"- Decision: {decision.get('decision')}")
    lines.append(f"- Rationale: {decision.get('rationale')}")
    lines.append(f"- Package necessity: {decision.get('package_necessity')}")
    lines.append(f"- Functionality exercised: {decision.get('functionality_exercised')}")
    lines.append(f"- Mitigating controls: {decision.get('mitigating_controls')}")
    lines.append(f"- Review date: {decision.get('review_date')}")
    lines.append(f"- Review condition: {decision.get('review_condition')}")


def _render_policy(lines: List[str], policy: Dict[str, Any]) -> None:
    lines.append(f"- Policy match: {policy.get('match_kind')} ({policy.get('reason')})")
    if policy.get("decision"):
        _render_decision(lines, policy["decision"])
    elif policy.get("recommendation"):
        rec = policy["recommendation"]
        lines.append(f"- Recommendation (non-gating): {rec.get('decision')} — {rec.get('rationale')}")


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
    lines.append(f"- Policy source: {summary['policy']['source']} ({summary['policy']['entry_count']} entries)")
    lines.append(f"- Gate overall: {'PASS' if g['ok'] else 'FAIL'}")
    lines.append(f"  - zero-fixable-CRITICAL: {'PASS' if g['zero_fixable_criticals'] else 'FAIL'}")
    lines.append(
        f"  - unfixed-CRITICAL policy matched: "
        f"{'PASS' if g['all_unfixed_critical_policy_matched'] else 'FAIL'}"
    )
    lines.append(f"  - stale policy entries: {len(g['stale_policy_entries'])}")
    lines.append(f"  - newly-fixable accepted: {len(g['newly_fixable_accepted'])}")
    lines.append(f"  - fixable HIGH: {g['fixable_high_count']} ({', '.join(g['fixable_high_ids']) or 'none'})")
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
        if "policy" in r:
            _render_policy(lines, r["policy"])
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


# --------------------------------------------------------------------------- CLI


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, help="full Trivy JSON")
    parser.add_argument("--output", required=True, help="sanitized JSON output")
    parser.add_argument("--markdown", required=True, help="sanitized Markdown output")
    parser.add_argument(
        "--policy",
        default=None,
        help="explicit vulnerability-acceptance policy JSON (default: "
             f"{DEFAULT_POLICY_PATH} relative to the repo root)",
    )
    parser.add_argument("--gate", action="store_true", help="fail unless the explicit-policy gate passes")
    args = parser.parse_args(argv)

    if not args.policy:
        repo_root = pathlib.Path(__file__).resolve().parents[2]
        args.policy = str(repo_root / DEFAULT_POLICY_PATH)

    with open(args.input, "r", encoding="utf-8") as handle:
        data = json.load(handle)
    summary = summarize(data, policy=args.policy)

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
        f"{s['highs_fixable']}) | gate={'PASS' if g['ok'] else 'FAIL'}"
    )
    if args.gate and not g["ok"]:
        print("Gate FAILED:", file=sys.stderr)
        if not g["zero_fixable_criticals"]:
            print(f"  fixable CRITICAL: {g['fixable_critical_ids']}", file=sys.stderr)
        if not g["all_unfixed_critical_policy_matched"]:
            print(f"  unfixed CRITICAL policy failures: {g['unfixed_critical_policy_failures']}", file=sys.stderr)
        if g["stale_policy_entries"]:
            print(f"  stale policy entries: {g['stale_policy_entries']}", file=sys.stderr)
        if g["newly_fixable_accepted"]:
            print(f"  previously accepted now-fixable: {g['newly_fixable_accepted']}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
