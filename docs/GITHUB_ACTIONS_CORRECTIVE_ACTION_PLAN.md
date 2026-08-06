# GitHub Actions Corrective Action Plan

## Scope

This document governs GitHub Actions for `SemperSupra/AgentKVM2USB`.
It covers hosted software validation only. It does not authorize hardware access,
USB capture, target input, elevation, vendor downloads, firmware writes, release
publication, or use of private evidence.

## Initial audit

Audit date: 2026-08-06.

The GitHub Actions API reported:

- zero registered workflows;
- zero workflow runs;
- zero historical warnings, errors, failures, or cancelled runs to diagnose;
- no Actions history or artifacts requiring deletion.

The root cause was therefore not a failing workflow. The repository had no hosted
CI at all. Local validation existed, but pull requests had no independent hosted
check that repository tests and the portable build remained healthy.

## Corrective action

The repository now defines `.github/workflows/ci.yml` with one bounded Windows job.

The workflow:

- runs for pull requests targeting `main` or
  `recovery/agentkvm2usb-app-capabilities`;
- runs for pushes to those two integration branches;
- supports an explicit manual dispatch;
- uses `windows-2025` and Python 3.12;
- grants the workflow token only `contents: read`;
- disables persisted checkout credentials;
- uses dependency caching from `requirements.txt`;
- cancels superseded runs for the same pull request or branch;
- has a 20-minute job timeout;
- compiles Python sources;
- runs the complete pytest suite;
- builds the portable archive twice and requires matching SHA-256 hashes;
- uploads no artifact and publishes no release.

The Windows runner is intentional. The project has Windows DirectShow,
`pygrabber`, PySide6, OpenCV, HID, and portable-PowerShell behavior. Linux-only CI
would not faithfully validate the supported host environment.

## Explicit exclusions

Hosted CI must not:

- enumerate or access KVM2USB, Beagle, camera, microphone, or USBPcap hardware;
- start packet, video, audio, screen, or analyzer capture;
- send keyboard, pointer, touch, macro, or system-control input;
- request UAC or administrator privileges;
- install drivers, USB filter components, Wireshark, USBPcap, Epiphan software, or
  Total Phase software;
- authenticate to vendor portals or use cookies, tokens, entitlements, or
  proprietary artifacts;
- write firmware, FPGA data, EDID, flash, or other persistent device state;
- create a GitHub release or upload a build artifact.

Hardware-in-the-loop and authorization-gated experiments remain local workflows
tracked by their respective GitHub issues.

## Warning, error, and failure triage

For every unsuccessful or warning-bearing run:

1. Identify the exact run, attempt, job, step, branch, SHA, and triggering event.
2. Read the complete failed-job log, not only the annotation summary.
3. Classify the finding as one of:
   - workflow syntax or configuration;
   - dependency resolution or cache;
   - compile failure;
   - deterministic test failure;
   - environmental or runner-image change;
   - portable-build reproducibility failure;
   - cancellation caused by concurrency;
   - GitHub service/transient infrastructure failure.
4. Preserve the failure until its cause is documented. Do not delete a run merely
   to make the history appear green.
5. Correct the smallest responsible scope and add or improve a deterministic test
   when possible.
6. Re-run only the failed job when the original successful work remains valid;
   otherwise create a new run through the corrected commit.
7. Confirm the corrected run is successful and review its log for warnings.
8. Record residual risk in the issue and pull request.

Dependency deprecation warnings, action-runtime warnings, cache failures, runner
image notices, and test warnings are actionable even when the job concludes
successfully.

## Action-version maintenance

The initial implementation uses the current supported major versions at the time
of the audit:

- `actions/checkout@v7`;
- `actions/setup-python@v7`.

Action upgrades require a normal issue or pull request, changelog review, and a
successful hosted run. Do not silently change major versions in unrelated work.
For higher assurance, a future hardening issue may pin actions to immutable commit
SHAs and use Dependabot to propose reviewed updates.

## Run-history policy

The goal is useful evidence, not a permanently green-looking timeline.

Keep:

- the latest successful run for each active pull request;
- runs that document a material failure or regression until the associated issue
  or pull request records the root cause and correction;
- integration-branch runs needed to establish release or merge provenance.

Eligible for deletion after resolution:

- duplicate manual-dispatch runs;
- superseded cancelled runs that contain no unique evidence;
- obsolete implementation experiments after their root causes and final successful
  replacements are documented;
- artifacts that were accidentally produced and are not required for provenance.

Deletion requires an authenticated human or automation identity with GitHub Actions
write permission. Use either:

```powershell
gh run delete <run-id> --repo SemperSupra/AgentKVM2USB
```

or the GitHub REST endpoint for deleting a workflow run. Never delete an unresolved
failure, and never claim history cleanup occurred when permissions or tooling did
not permit it.

The workflow uses concurrency cancellation to prevent avoidable duplicate history.
It intentionally uploads no artifacts, so artifact-retention cleanup is not part of
normal operation.

## Local equivalent

Run from a clean Windows checkout:

```powershell
python -m pip install --requirement requirements.txt
python -m compileall -q .
python -m pytest -q

python .\scripts\build_portable.py --version ci --dist-dir .\.work\ci-build-one
python .\scripts\build_portable.py --version ci --dist-dir .\.work\ci-build-two

$First = (Get-FileHash .\.work\ci-build-one\AgentKVM2USB-vci-windows-portable.zip -Algorithm SHA256).Hash
$Second = (Get-FileHash .\.work\ci-build-two\AgentKVM2USB-vci-windows-portable.zip -Algorithm SHA256).Hash
if ($First -ne $Second) { throw "Portable build is not reproducible." }
```

## Exit criteria

The corrective action is complete when:

- GitHub accepts the workflow syntax;
- the draft pull request produces a successful hosted run;
- all job steps and logs have been reviewed for warnings;
- the workflow remains within its permissions and safety boundaries;
- no duplicate or obsolete implementation runs remain without a documented reason;
- the correction issue and pull request contain the final run IDs and conclusions.
