#!/usr/bin/env python3
"""Remote branch-ownership claim/lease preflight helpers.

A branch is owned by exactly one actor at a time. ``START`` establishes an
exclusive claim with a unique claim_id, actor, branch, expected remote head,
claim timestamp, and lease expiry. ``CHECKPOINT`` may renew the same claim by
extending its expiry. ``HANDOFF`` must release the claim or transfer it to a
named next actor with the exact branch and head SHA.

This module is pure and deterministic: it takes plain dicts and a clock, so the
entire claim lifecycle is unit-testable with fixtures and no GitHub access.
Authenticated remote state (issue comments, branch head) is the caller's
responsibility to fetch and pass in.
"""

from __future__ import annotations

import datetime as dt
from typing import Any, Optional

# A claim may never be indefinite. 4 hours is the documented default lease;
# renewal extends the expiry but never makes it permanent.
DEFAULT_LEASE_SECONDS = 4 * 60 * 60
MAX_LEASE_SECONDS = 7 * 24 * 60 * 60  # one week absolute ceiling for renewal

CLAIM_STATES = ("active", "renewed", "released", "transferred", "expired")

CLAIM_REQUIRED_FIELDS = (
    "claim_id",
    "claim_state",
    "actor",
    "repository",
    "issue",
    "branch",
    "pull_request",
    "expected_remote_head",
    "claimed_at_utc",
    "lease_expires_utc",
    "assigned_slice",
)


def parse_iso(value: Optional[str]) -> Optional[dt.datetime]:
    if not value:
        return None
    try:
        return dt.datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None


def validate_claim_identity(claim: dict[str, Any]) -> list[str]:
    """Return a list of missing or invalid required identity fields.

    Fails on missing identity and on indefinite (missing/invalid) expiry.
    """
    errors: list[str] = []
    for field in CLAIM_REQUIRED_FIELDS:
        value = claim.get(field)
        if value is None or (isinstance(value, str) and not value.strip()):
            errors.append(f"missing required claim field: {field}")
    # Branch and head are the portable coordination identity; a worktree path
    # may be present as optional diagnostic context but is never required.
    branch = claim.get("branch")
    head = claim.get("expected_remote_head")
    if branch and not str(branch).strip():
        errors.append("branch must not be empty")
    if head and not str(head).strip():
        errors.append("expected_remote_head must not be empty")

    claimed = parse_iso(claim.get("claimed_at_utc"))
    expires = parse_iso(claim.get("lease_expires_utc"))
    if claimed is None:
        errors.append("claimed_at_utc must be a valid ISO-8601 timestamp")
    if expires is None:
        errors.append("lease_expires_utc must be a valid ISO-8601 timestamp")
    if claimed is not None and expires is not None:
        if expires <= claimed:
            errors.append("lease_expires_utc must be after claimed_at_utc")
        duration = (expires - claimed).total_seconds()
        if duration <= 0:
            errors.append("lease duration must be positive")
        if duration > MAX_LEASE_SECONDS:
            errors.append(
                f"lease duration {int(duration)}s exceeds the {MAX_LEASE_SECONDS}s ceiling; "
                "indefinite or over-long leases are rejected"
            )

    state = claim.get("claim_state")
    if state is not None and state not in CLAIM_STATES:
        errors.append(f"claim_state must be one of {sorted(CLAIM_STATES)}")
    return errors


def claim_is_active(claim: dict[str, Any], now_utc: Optional[dt.datetime] = None) -> bool:
    """True only when the claim state is active/renewed AND the lease has not
    expired. A released/transferred/expired claim, or an expired lease, is not
    an active claim."""
    state = claim.get("claim_state")
    if state not in ("active", "renewed"):
        return False
    now = now_utc or dt.datetime.now(dt.timezone.utc)
    expires = parse_iso(claim.get("lease_expires_utc"))
    if expires is None:
        return False
    return now < expires


def renewal_expiry(
    claim: dict[str, Any],
    *,
    now_utc: Optional[dt.datetime] = None,
    extension_seconds: int = DEFAULT_LEASE_SECONDS,
) -> str:
    """Return a new lease_expires_utc for renewing the same claim.

    Renewal extends from ``now`` (never from the stale prior expiry) by the
    requested extension, capped at the absolute ceiling. Returns an ISO-8601
    string. Raises if the claim is not an active/renewed claim or if the
    extension would exceed the ceiling from now.
    """
    state = claim.get("claim_state")
    if state not in ("active", "renewed"):
        raise ValueError(f"cannot renew a claim in state {state!r}")
    now = now_utc or dt.datetime.now(dt.timezone.utc)
    new_expiry = now + dt.timedelta(seconds=extension_seconds)
    ceiling = now + dt.timedelta(seconds=MAX_LEASE_SECONDS)
    if new_expiry > ceiling:
        raise ValueError(
            f"renewal would exceed the {MAX_LEASE_SECONDS}s ceiling from now"
        )
    return new_expiry.isoformat()


def preflight_before_work(
    *,
    existing_claims: list[dict[str, Any]],
    branch: str,
    now_utc: Optional[dt.datetime] = None,
) -> dict[str, Any]:
    """Determine whether a new actor may claim the branch before material work.

    Rules:
    - if any unexpired active/renewed claim for the branch exists, fail closed
      (a conflicting claim blocks a new owner);
    - otherwise a new claim is permitted.
    Returns a report dict with ``allowed`` and a reason.
    """
    now = now_utc or dt.datetime.now(dt.timezone.utc)
    for claim in existing_claims:
        if claim.get("branch") != branch:
            continue
        if claim_is_active(claim, now):
            return {
                "allowed": False,
                "reason": (
                    f"an unexpired claim ({claim.get('claim_id')}) is active on "
                    f"branch {branch!r} until {claim.get('lease_expires_utc')}"
                ),
                "conflicting_claim": claim,
            }
    return {"allowed": True, "reason": "no unexpired conflicting claim", "conflicting_claim": None}


def preflight_before_push(
    *,
    claim: dict[str, Any],
    actual_remote_head: str,
    expected_remote_head: str,
    now_utc: Optional[dt.datetime] = None,
) -> dict[str, Any]:
    """Fail closed if the remote head moved unexpectedly before a push.

    A normal non-force push is only safe when the actual remote head still
    equals the claim's expected head (i.e. the local branch is based on it).
    """
    errors: list[str] = []
    if not claim_is_active(claim, now_utc):
        errors.append("claim is not active; renew or re-establish before pushing")
    if str(actual_remote_head) != str(expected_remote_head):
        errors.append(
            f"remote head changed unexpectedly: expected {expected_remote_head}, "
            f"actual {actual_remote_head}; do not push"
        )
    return {
        "allowed": not errors,
        "errors": errors,
        "actual_remote_head": actual_remote_head,
        "expected_remote_head": expected_remote_head,
    }


def build_claim(
    *,
    claim_id: str,
    actor: str,
    repository: str,
    issue: int,
    branch: str,
    pull_request: int,
    expected_remote_head: str,
    claimed_at_utc: str,
    lease_expires_utc: str,
    assigned_slice: str,
    environment: Optional[str] = None,
    worktree_path: Optional[str] = None,
) -> dict[str, Any]:
    """Build a well-formed claim dict. A worktree path is optional diagnostic
    context and is explicitly non-authoritative."""
    claim: dict[str, Any] = {
        "claim_id": claim_id,
        "claim_state": "active",
        "actor": {
            "name": actor,
            "environment": environment or "unstated",
        },
        "repository": repository,
        "issue": issue,
        "branch": branch,
        "pull_request": pull_request,
        "expected_remote_head": expected_remote_head,
        "claimed_at_utc": claimed_at_utc,
        "lease_expires_utc": lease_expires_utc,
        "assigned_slice": assigned_slice,
    }
    if worktree_path:
        # Optional diagnostic context only; never authoritative and never
        # required for another machine to resume work.
        claim["worktree_path"] = {
            "value": worktree_path,
            "authoritative": False,
            "note": "machine-local diagnostic context only",
        }
    return claim
