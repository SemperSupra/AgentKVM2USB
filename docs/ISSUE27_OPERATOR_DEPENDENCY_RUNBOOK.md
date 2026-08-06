# Issue #27 Operator Dependency Runbook

PR #28 integrated this workflow into `recovery/agentkvm2usb-app-capabilities` at merge commit `5a398ac529d1e050101a6f078153f3935498d6d2`.

Issue #27 remains open only for operator prerequisites and external Package Foundry gates. Read `docs/EXECUTION_CHECKPOINT.md` before execution. Do not reuse the merged `issue-27-operator-dependencies` branch.

This runbook never authorizes capture, target input, recabling, firmware, FPGA, EDID, flash, or automatic reboot.

## Dependency dispositions

| Dependency | Disposition | Required path |
|---|---|---|
| Wireshark / TShark | Existing public WinGet | Exact `WiresharkFoundation.Wireshark` from source `winget`, through the shared human-gated UAC helper. |
| USBPcap | Foundry candidate | Block until `SemperSupra/windows-package-foundry#1` classifies it eligible and #2 provides a reviewed package/source. No fallback. |
| Total Phase Beagle API / Data Center / driver | Manual vendor staging | Human acquires from the authenticated vendor portal. Automation may only verify and stage the supplied local file. |
| Epiphan KVM2USB application / driver | Manual vendor staging / license review | Human acquires and accepts terms. Elevation requires valid Epiphan Authenticode and provenance binding. |

## Shared elevation trust gate

The workflow reuses:

```text
SupraCraft/minecraft-infra/scripts/local/Invoke-Elevated.ps1
```

Expected checkout layouts:

```text
C:\Users\Mark\Projects\minecraft-infra
C:\Users\Mark\Projects\SupraCraft\minecraft-infra
```

Before import, the script requires one unambiguous helper that is:

- inside the expected repository root;
- tracked by Git;
- unstaged and unmodified;
- from the expected GitHub origin;
- on a commit contained in an `origin/*` ref.

Any missing, dirty, untracked, ambiguous, or non-origin-backed helper fails closed.

The helper preserves visible action disclosure, timed default-deny consent, ordinary Windows UAC, and auto/AFK refusal. No flag, environment variable, or agent instruction implies consent.

## Stage 1 — Plan

```powershell
pwsh -NoProfile -File .\scripts\prepare_issue22_dependencies.ps1 -Plan
```

The command writes sanitized ignored evidence to:

```text
.work/evidence/issue-27-operator-dependencies/plan.json
```

Plan mode does not elevate, install, launch a vendor installer, capture, send input, recable, or reboot.

If `pending_reboot` is true, stop. The operator must restart Windows manually. Begin a fresh claim after restart and rerun `-Plan`.

## Stage 2 — Wireshark

With the operator present:

```powershell
pwsh -NoProfile -File .\scripts\prepare_issue22_dependencies.ps1 -Install Wireshark
```

The elevated child may invoke only the exact WinGet ID/source with agreement flags. Success requires independent verification of both `Wireshark.exe` and `tshark.exe`; a zero process exit alone is insufficient. The workflow reports reboot state but never reboots.

## Stage 3 — USBPcap remains blocked

```powershell
pwsh -NoProfile -File .\scripts\prepare_issue22_dependencies.ps1 -Install USBPcap
```

Until Package Foundry #1/#2 complete, this command must return a nonzero fail-closed result. Do not use a direct release installer, browser download, Chocolatey, Scoop, an old package ID, or an arbitrary local executable.

## Stage 4 — Total Phase staging

The human performs authenticated acquisition and accepts terms.

```powershell
pwsh -NoProfile -File .\scripts\prepare_issue22_dependencies.ps1 `
  -StageVendorArtifact TotalPhaseBeagleApi `
  -Path '<operator-supplied-file>' `
  -SourcePage '<https-authoritative-vendor-page>' `
  -AcquiredUtc '<ISO-8601-UTC>'
```

Destination: ignored `.work/vendor/totalphase/`.

The script records size, SHA-256, signature information where applicable, HTTPS source page, and acquisition UTC. It records no credentials, cookies, tokens, browser profile, personalized URL, or proprietary bytes in Git. Portable API staging never requests UAC or starts capture.

## Stage 5 — Epiphan staging

```powershell
pwsh -NoProfile -File .\scripts\prepare_issue22_dependencies.ps1 `
  -StageVendorArtifact EpiphanKvmApp `
  -Path '<operator-supplied-installer-or-archive>' `
  -SourcePage '<https-authoritative-vendor-page>' `
  -AcquiredUtc '<ISO-8601-UTC>'
```

Destination: ignored `.work/vendor/epiphan/`.

Before any EXE/MSI elevation, the workflow rechecks:

- current file hash matches provenance;
- Authenticode status is `Valid`;
- signer identifies Epiphan;
- current signer thumbprint matches staged provenance.

Failure of any check blocks execution. The operator remains responsible for every interactive installer and license decision.

## Stage 6 — Verification and handoff

After each approved action:

```powershell
pwsh -NoProfile -File .\scripts\prepare_issue22_dependencies.ps1 -Plan
```

Record exact installed paths/versions, drivers, hashes, signatures, provenance, and reboot state in ignored evidence and sanitized GitHub comments.

Issue #27 is ready to hand off to issue #22 only when all issue #22 entry-gate items pass. Finish every slice with `CHECKPOINT` as needed, `HANDOFF`, claim release, and clean worktrees.
