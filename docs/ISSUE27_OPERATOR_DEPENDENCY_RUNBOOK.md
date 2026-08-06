# Issue #27 Operator Dependency Runbook

This runbook implements the operator-facing dependency path needed by issue #22. It allows an agent to prepare and verify actions while preserving human control over UAC, vendor licenses, and proprietary downloads.

It does not authorize capture, target input, recabling, firmware, FPGA, EDID, flash, or automatic reboot.

## Dependency dispositions

| Dependency | Disposition | Required path |
|---|---|---|
| Wireshark / TShark | Existing public WinGet | Exact package `WiresharkFoundation.Wireshark`, source `winget`, invoked only through the shared human-gated UAC helper. |
| USBPcap | Foundry candidate | Block until `SemperSupra/windows-package-foundry#1` classifies it eligible and #2 provides a reviewed package/source. No ad hoc installer fallback. |
| Total Phase Beagle API / Data Center / driver | Manual vendor staging | Human acquires from the authenticated vendor portal. Automation may hash, verify, stage, and optionally invoke a locally supplied installer after consent. Never automate login or publish the bytes. |
| Epiphan KVM2USB application / driver | Manual vendor staging / license review | Human acquires the authorized package. Automation may hash, verify, stage, and invoke the exact local installer after consent. Do not create a public package without permission or a license determination. |

## Shared elevation mechanism

Issue #27 must reuse:

```text
SupraCraft/minecraft-infra/scripts/local/Invoke-Elevated.ps1
```

Expected local repository locations:

```text
C:\Users\Mark\Projects\minecraft-infra
C:\Users\Mark\Projects\SupraCraft\minecraft-infra
```

The dependency script verifies the helper is inside a Git checkout whose `origin` identifies `SupraCraft/minecraft-infra`. It imports the helper rather than copying or reimplementing it.

The helper preserves:

- auto/AFK fail-closed behavior;
- visible description and exact privileged actions;
- timed default-deny consent;
- normal Windows UAC through `Start-Process -Verb RunAs -Wait`;
- no meaning of consent from `-Force`, environment state, or agent instructions.

## Stage 1 — Plan and inventory

Run without elevation:

```powershell
pwsh -NoProfile -File .\scripts\prepare_issue22_dependencies.ps1 -Plan
```

The command records sanitized evidence at:

```text
.work/evidence/issue-27-operator-dependencies/plan.json
```

Verify that Git ignores the file:

```powershell
git check-ignore -v .work/evidence/issue-27-operator-dependencies/plan.json
```

Review:

- WinGet presence and version;
- Wireshark/TShark installed paths and versions;
- USBPcap presence and blocked/approved state;
- Epiphan and Total Phase installed-application evidence;
- KVM2USB and Beagle driver/PnP state;
- shared UAC helper path, repository origin, and trust result;
- staged vendor-artifact inventory;
- pending reboot indicators;
- exact next human actions.

Plan mode must not elevate, install, launch a vendor installer, capture, or send input.

## Stage 2 — Wireshark through WinGet

Request installation:

```powershell
pwsh -NoProfile -File .\scripts\prepare_issue22_dependencies.ps1 -Install Wireshark
```

Expected sequence:

1. The script verifies the shared helper.
2. It displays the exact package ID, source, and privileged actions.
3. The shared helper waits for a human-present decision.
4. Windows displays its ordinary UAC prompt.
5. The elevated child invokes only:

```text
winget install --id WiresharkFoundation.Wireshark --exact --source winget
```

with explicit package/source agreement flags.

6. The script independently verifies WinGet inventory and the expected Wireshark/TShark executables.
7. It reports a possible reboot but never performs one.

A successful process exit is not sufficient without independent verification.

## Stage 3 — USBPcap remains fail-closed

The following command is intentionally blocked until the Package Foundry gates are complete:

```powershell
pwsh -NoProfile -File .\scripts\prepare_issue22_dependencies.ps1 -Install USBPcap
```

The script must identify these blockers:

- `SemperSupra/windows-package-foundry#1` — eligibility and exclusions;
- `SemperSupra/windows-package-foundry#2` — USBPcap package assessment and implementation.

Do not substitute a direct GitHub release installer, an old package ID, a browser download, Chocolatey, Scoop, or an arbitrary local executable.

After Package Foundry completes, a later reviewed change may configure the approved source and exact package ID. Until then, the expected behavior is a nonzero fail-closed result.

## Stage 4 — Stage Total Phase API

The human downloads the authorized artifact from the Total Phase portal and accepts any required terms personally.

Stage it without elevation:

```powershell
pwsh -NoProfile -File .\scripts\prepare_issue22_dependencies.ps1 `
  -StageVendorArtifact TotalPhaseBeagleApi `
  -Path '<operator-supplied-file>' `
  -SourcePage '<authoritative-vendor-page>' `
  -AcquiredUtc '<ISO-8601-UTC>'
```

The script copies only to:

```text
.work/vendor/totalphase/
```

It records filename, size, SHA-256, signature status/signer when applicable, source page, acquisition UTC, and disposition. It records no credentials, cookies, tokens, browser profile, personalized URL, or proprietary bytes in Git.

The Beagle API is portable staging. It must not request UAC or call the capture API.

## Stage 5 — Stage Epiphan application/driver

The human obtains the authorized package and reviews the vendor license.

Stage it without elevation:

```powershell
pwsh -NoProfile -File .\scripts\prepare_issue22_dependencies.ps1 `
  -StageVendorArtifact EpiphanKvmApp `
  -Path '<operator-supplied-installer-or-archive>' `
  -SourcePage '<authoritative-vendor-page>' `
  -AcquiredUtc '<ISO-8601-UTC>'
```

The destination is:

```text
.work/vendor/epiphan/
```

No package-manager publication is implied by local staging.

## Stage 6 — Install an explicitly staged Epiphan installer

Only after the operator reviews the exact staged file, its hash, signer, provenance record, and requested action:

```powershell
pwsh -NoProfile -File .\scripts\prepare_issue22_dependencies.ps1 `
  -InstallStagedVendorArtifact EpiphanKvmApp `
  -StagedPath '.\.work\vendor\epiphan\<exact-file>'
```

The script:

- refuses paths outside the ignored Epiphan staging directory;
- verifies the current hash against its provenance record;
- uses the shared UAC helper;
- launches the exact local vendor installer interactively;
- invents no silent switches and accepts no terms automatically;
- waits for completion;
- reruns application/driver inventory;
- reports but does not initiate a reboot.

The operator remains responsible for every interactive installer choice and license acceptance.

## Stage 7 — Re-run readiness

After dependency actions:

```powershell
pwsh -NoProfile -File .\scripts\prepare_issue22_dependencies.ps1 -Plan
pwsh -NoProfile -File .\scripts\collect_issue22_readiness.ps1 `
  -BeagleApiDir .\.work\vendor\totalphase `
  -Pretty
```

Then resume issue #22 for:

- read-only `USBPcapCMD.exe -d` enumeration when an approved USBPcap install exists;
- positive interface-to-root-hub mapping;
- physical topology and target-state confirmation;
- no-live preflight and manifest generation.

## Validation expected from the implementing agent

```powershell
python -m compileall -q scripts test_issue22_work_package.py test_issue27_work_package.py
python -m pytest -q
git diff --check
pwsh -NoProfile -File .\scripts\prepare_issue22_dependencies.ps1 -Plan
```

Any real privileged installation remains an operator action at the keyboard.

## Handoff

Issue #27 is ready for review when:

- plan mode is read-only and reproducible;
- the shared helper is discovered and trusted in both workspace layouts;
- Wireshark uses the exact public WinGet package and source;
- USBPcap fails closed behind Package Foundry #1/#2;
- Total Phase and Epiphan use manual local staging only;
- local vendor bytes and evidence paths are ignored;
- staging is idempotent and provenance-checked;
- reboot is detected but never initiated;
- tests and local Windows validation pass;
- no capture, target input, recabling, credential use, or proprietary publication occurs.
