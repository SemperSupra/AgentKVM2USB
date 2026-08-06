# Issue #22 Operator Runbook

This runbook prepares the Windows workstation for the later issue #14 official-app differential experiment. It does not authorize capture or target input.

## Rules

- The local agent may inspect and prepare commands but must not approve UAC or perform privileged installation.
- The operator performs every elevated or physical action explicitly.
- Stop after each action and verify the result before continuing.
- Do not start USB capture, Beagle capture, application-driven target input, or recabling under issue #22.
- Store vendor installers and APIs only under ignored/private paths. Record hashes and provenance; do not commit binaries.

## Expected device context

Last verified workstation facts:

- KVM2USB USB identity: `VID_2B77&PID_3661`;
- previously observed serial/device suffix: `332837`;
- parent hub: VIA Labs VL817, `VID_2109&PID_0817`;
- Beagle USB 12 identity: `VID_1679&PID_2001`;
- evidence volume previously had about 21.7 GiB free;
- the 2 GiB disk gate passed;
- the USBPcap-to-KVM2USB root-hub mapping remained unproven.

Treat these as values to verify, not assumptions.

## Stage 1 — Read-only inventory

Run without elevation:

```powershell
pwsh -NoProfile -File .\scripts\collect_issue22_readiness.ps1 -Pretty
```

Review:

```text
.work/evidence/issue-22-workstation-capture-deps/readiness.json
```

Confirm Git ignores it:

```powershell
git check-ignore -v .work/evidence/issue-22-workstation-capture-deps/readiness.json
```

Stop if the output path is not ignored or if device identity differs from the expected KVM2USB or Beagle.

## Stage 2 — USBPcap and Wireshark/TShark

### Operator action

Open an elevated PowerShell terminal only after reviewing the package source and version.

Preferred package commands recorded by issue #22:

```powershell
winget install --id WiresharkFoundation.USBPcap --exact --source winget
winget install --id WiresharkFoundation.Wireshark --exact --source winget
```

Package availability and IDs must be verified by the operator before installation:

```powershell
winget show --id WiresharkFoundation.USBPcap --exact --source winget
winget show --id WiresharkFoundation.Wireshark --exact --source winget
```

Do not accept unrelated packages or silently substitute another source.

### Verification

Run in a normal terminal:

```powershell
Get-Command USBPcapCMD.exe -ErrorAction Stop | Format-List Source,Version
Get-Command tshark.exe -ErrorAction Stop | Format-List Source,Version
& (Get-Command USBPcapCMD.exe).Source -d
& (Get-Command tshark.exe).Source --version
```

`USBPcapCMD.exe -d` is enumeration only. Do not pass an output file, buffer size, capture filter, or start-capture option.

### Rollback

Only when the operator decides rollback is required:

```powershell
winget uninstall --id WiresharkFoundation.USBPcap --exact
winget uninstall --id WiresharkFoundation.Wireshark --exact
```

A reboot may be required by USBPcap installation or removal. Record whether one occurred.

## Stage 3 — Official Epiphan application and driver

### Preparation

Locate the official vendor package already obtained through an authorized source. Record:

- source URL or account/download record;
- package filename;
- version;
- SHA-256;
- signer and signature status;
- acquisition UTC.

Example hash and signature inspection:

```powershell
Get-FileHash -Algorithm SHA256 -LiteralPath '<installer-path>'
Get-AuthenticodeSignature -LiteralPath '<installer-path>' | Format-List Status,StatusMessage,SignerCertificate
```

### Operator action

The operator runs the official signed installer interactively with elevation. Do not invent or use unattended installer switches unless vendor documentation explicitly supports them.

### Verification

```powershell
Get-PnpDevice -PresentOnly | Where-Object InstanceId -Match 'VID_2B77&PID_3661' |
  Format-Table Status,Class,FriendlyName,InstanceId -AutoSize
```

Also confirm the installed application path and version through its signed executable properties and the uninstall registry. Record driver provider, version, date, status, and device interface association.

### Rollback

Use the vendor-provided uninstaller or Windows Installed Apps. Record the exact uninstall entry discovered on this workstation; do not guess a command.

## Stage 4 — Total Phase Beagle Windows API

Stage the authorized Windows API package under:

```text
.work/vendor/totalphase/
```

Required records:

- source and acquisition UTC;
- archive filename and SHA-256;
- extraction directory;
- API/DLL versions;
- hashes of the exact libraries used;
- confirmation that the path is Git-ignored.

Verification:

```powershell
git check-ignore -v .work/vendor/totalphase
Get-ChildItem -Recurse .work/vendor/totalphase | Get-FileHash -Algorithm SHA256
Get-PnpDevice -PresentOnly | Where-Object InstanceId -Match 'VID_1679&PID_2001' |
  Format-Table Status,Class,FriendlyName,InstanceId -AutoSize
```

Do not call the Beagle capture API under issue #22.

## Stage 5 — Prove the USBPcap mapping

A valid mapping must bind all of the following:

1. exact KVM2USB PnP instance;
2. KVM2USB parent/composite and location path;
3. VIA hub and root-controller lineage;
4. an interface actually listed by `USBPcapCMD.exe -d`;
5. the selected interface used in the preflight JSON.

Collect PnP properties:

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

USBPcapCMD.exe -d
```

The mapping JSON supplied to `official_app_baseline.py` must use the exact schema shown by its CLI help and tests. A conceptual example is:

```json
{
  "\\\\.\\USBPcap1": {
    "contains_kvm2usb": true,
    "device_instance_id": "USB\\VID_2B77&PID_3661\\332837",
    "evidence": {
      "container_id": "<verified-container-guid>",
      "location_paths": ["<verified-location-path>"],
      "parent_chain": ["<verified-parent-chain>"],
      "usbpcap_enumeration": "<sanitized-enumeration-reference>"
    }
  }
}
```

Do not copy the conceptual example directly. Generate the shape accepted by the current code and populate only verified workstation values.

Fail the gate when:

- no USBPcap interface is detected;
- an interface is mapped only because it is the sole interface;
- the KVM2USB is globally present but not tied to that root hub;
- location or parent evidence conflicts;
- more than one mapping remains plausible.

## Stage 6 — Physical topology and target state

The operator must confirm and record:

- exact KVM2USB physical unit and serial/device instance;
- host USB port and any intermediate hub;
- KVM2USB target-side USB cable path;
- Beagle position and orientation;
- target identity;
- current target screen/state;
- confirmation that the target contains no sensitive data and can safely receive the later authorized harmless sequence.

No recabling is permitted merely to complete this record. If the current topology is unsuitable, stop and propose a separate operator action.

## Stage 7 — No-live preflight

After all evidence is complete, run only the no-live commands described by the current CLI:

```powershell
python .\scripts\official_app_baseline.py preflight --help
python .\scripts\official_app_baseline.py build-manifest --help
```

Then invoke each command with the complete evidence arguments.

Issue #22 is complete when:

- preflight reports `ok: true`;
- `live_disabled` remains true;
- the USBPcap mapping is positively proven;
- tools, APIs, drivers, topology, target state, output root, and disk gates pass;
- a valid manifest is generated;
- no capture or target input occurs.

## Stage 8 — Handoff to issue #14

Do not start the experiment.

Issue #14 still requires a new GitHub-backed, expiring authorization containing:

- exact experiment ID;
- exact target and KVM2USB unit;
- exact harmless allowed input sequence;
- USBPcap interface;
- Beagle placement;
- private output root;
- authority/operator;
- issued and expiry UTC;
- stop conditions and forbidden actions.
