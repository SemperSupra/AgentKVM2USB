# Issue #22 Readiness and USBPcap Mapping Runbook

Issue #22 begins after issue #27 has prepared the operator dependency path and the required dependencies are actually present. It owns readiness evidence, USBPcap root-hub mapping, topology confirmation, and no-live preflight.

It does not acquire software and it does not authorize capture or target input.

## Dependency handoff

Use issue #27 and `docs/ISSUE27_OPERATOR_DEPENDENCY_RUNBOOK.md` for:

- the shared `minecraft-infra` human-gated UAC helper;
- exact WinGet installation of Wireshark/TShark;
- fail-closed USBPcap handling through Windows Package Foundry #1/#2;
- local ignored staging of Total Phase and Epiphan artifacts;
- operator-present invocation of an exact staged vendor installer;
- reboot detection without automatic reboot.

Do not recreate those mechanisms under issue #22.

## Entry gate

Resume issue #22 only when all applicable facts are true:

- Wireshark and TShark are independently verified;
- USBPcap has an approved installation path and `USBPcapCMD.exe` is present;
- the official Epiphan application and required driver state are verified;
- the Total Phase Beagle API is staged under ignored `.work/vendor/totalphase/` with hashes/provenance;
- any required reboot was separately approved, completed, and post-reboot health was checked;
- no conflicting issue #22 claim exists.

If an entry-gate item is missing, return to issue #27 or the relevant Package Foundry issue instead of improvising.

## Branch and coordination

The original `issue-22-workstation-capture-deps` branch and PR #26 supplied the merged readiness framework. Do not resume new work on that merged branch.

For the completion slice, create a fresh branch from the current integration head after claim preflight, preferably:

```text
issue-22-readiness-completion
```

Use one isolated worktree, an early draft PR, a finite `START` claim, `CHECKPOINT` renewals, and a final `HANDOFF` with claim release.

## Stage 1 — Read-only inventory

Run without elevation:

```powershell
pwsh -NoProfile -File .\scripts\prepare_issue22_dependencies.ps1 -Plan
pwsh -NoProfile -File .\scripts\collect_issue22_readiness.ps1 `
  -BeagleApiDir .\.work\vendor\totalphase `
  -Pretty
```

Review:

```text
.work/evidence/issue-27-operator-dependencies/plan.json
.work/evidence/issue-22-workstation-capture-deps/readiness.json
```

Confirm both outputs are ignored. Stop if device identity differs from the expected KVM2USB or Beagle, the output path is not ignored, or a dependency has regressed.

## Stage 2 — Read-only USBPcap enumeration

Locate and record the exact installed `USBPcapCMD.exe` path and version, then run enumeration only:

```powershell
Get-Command USBPcapCMD.exe -ErrorAction Stop | Format-List Source,Version
& (Get-Command USBPcapCMD.exe).Source -d
```

Do not pass an output filename, capture filter, buffer size, or any option that begins capture.

## Stage 3 — Prove the interface-to-root-hub mapping

A valid mapping binds all of these:

1. exact KVM2USB PnP instance;
2. serial/device suffix and PnP ContainerId when available;
3. MI_00, MI_01, and MI_03 interfaces;
4. parent composite device;
5. VIA hub, root controller, and port/location path;
6. an interface actually reported by `USBPcapCMD.exe -d`;
7. the exact selected interface represented in the preflight JSON.

Collect PnP evidence:

```powershell
$kvm = Get-PnpDevice -PresentOnly | Where-Object InstanceId -Match 'VID_2B77&PID_3661'
$kvm | Format-Table Status,Class,FriendlyName,InstanceId -AutoSize

foreach ($device in $kvm) {
    Get-PnpDeviceProperty -InstanceId $device.InstanceId |
      Where-Object KeyName -In @(
        'DEVPKEY_Device_Parent',
        'DEVPKEY_Device_ContainerId',
        'DEVPKEY_Device_LocationPaths',
        'DEVPKEY_Device_LocationInfo',
        'DEVPKEY_Device_DriverVersion',
        'DEVPKEY_Device_DriverProvider'
      ) | Format-Table KeyName,Data -AutoSize
}
```

Use the current CLI help and tests to build the exact `--interface-mapping` JSON schema. Do not copy a conceptual example or infer mapping merely because one interface is visible.

Fail closed when:

- no USBPcap interface is detected;
- the KVM2USB is globally present but not tied to the selected root hub;
- parent/location evidence conflicts;
- more than one mapping remains plausible;
- the mapping depends on an unverified physical assumption.

## Stage 4 — Physical topology and target state

The operator records:

- exact KVM2USB unit and device identity;
- host USB port and intermediate hub path;
- target-side USB cable path;
- Beagle identity, position, and orientation;
- target identity and current screen/state;
- confirmation that the target is harmless, non-sensitive, and suitable for a later bounded experiment.

Do not recable merely to complete the record. A topology change is a separate explicit operator action.

## Stage 5 — No-live preflight

Run only the no-live commands described by the current CLI:

```powershell
python .\scripts\official_app_baseline.py preflight --help
python .\scripts\official_app_baseline.py build-manifest --help
```

Then invoke them with complete verified evidence.

Issue #22 is complete when:

- preflight reports `ok: true`;
- `live_disabled` remains true;
- the selected USBPcap interface is positively mapped;
- tools, APIs, applications, drivers, topology, target state, output root, and disk gates pass;
- a valid manifest is generated;
- no capture or target input occurs;
- sanitized results are recorded in GitHub and ignored `.work` storage.

## Stage 6 — Handoff to issue #14

Do not start the experiment.

Issue #14 requires a new GitHub-backed authorization containing:

- exact experiment ID;
- exact target and KVM2USB unit;
- exact harmless allowed input sequence;
- exact USBPcap interface and Beagle placement;
- private output root;
- operator/authority;
- issued and expiry UTC;
- stop conditions and forbidden actions.

## Safety

- No dependency acquisition outside issue #27.
- No vendor login, cookies, tokens, personalized downloads, or automatic license acceptance.
- No capture, target input, recabling, automatic reboot, vendor OUT, firmware, FPGA, EDID, flash, or persistent-device writes.
- No proprietary binaries, raw captures, credentials, or private evidence in Git.
- PR #13 remains untouched.
