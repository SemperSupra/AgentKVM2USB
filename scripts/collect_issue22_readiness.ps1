[CmdletBinding()]
param(
    [string]$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path,
    [string]$OutputPath,
    [string]$BeagleApiDir,
    [switch]$Pretty
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Get-UtcTimestamp {
    return [DateTime]::UtcNow.ToString("o")
}

function Get-ObjectPropertyValue {
    param(
        [Parameter(Mandatory)]$InputObject,
        [Parameter(Mandatory)][string]$Name
    )

    $property = $InputObject.PSObject.Properties[$Name]
    if ($null -eq $property) {
        return $null
    }
    return $property.Value
}

function Get-CommandRecord {
    param([Parameter(Mandatory)][string]$Name)

    $command = Get-Command $Name -ErrorAction SilentlyContinue | Select-Object -First 1
    if (-not $command) {
        return [ordered]@{
            name = $Name
            present = $false
            path = $null
            version = $null
        }
    }

    $path = Get-ObjectPropertyValue -InputObject $command -Name "Source"
    if (-not $path) {
        $path = Get-ObjectPropertyValue -InputObject $command -Name "Path"
    }

    $version = $null
    try {
        $commandVersion = Get-ObjectPropertyValue -InputObject $command -Name "Version"
        if ($commandVersion) {
            $version = $commandVersion.ToString()
        } elseif ($path -and (Test-Path -LiteralPath $path)) {
            $version = (Get-Item -LiteralPath $path).VersionInfo.FileVersion
        }
    } catch {
        $version = $null
    }

    return [ordered]@{
        name = $Name
        present = $true
        path = $path
        version = $version
    }
}

function Invoke-ReadOnlyCommand {
    param(
        [Parameter(Mandatory)][string]$FilePath,
        [string[]]$ArgumentList = @()
    )

    try {
        $startInfo = [System.Diagnostics.ProcessStartInfo]::new()
        $startInfo.FileName = $FilePath
        $startInfo.UseShellExecute = $false
        $startInfo.CreateNoWindow = $true
        $startInfo.RedirectStandardOutput = $true
        $startInfo.RedirectStandardError = $true
        foreach ($argument in $ArgumentList) {
            [void]$startInfo.ArgumentList.Add($argument)
        }

        $process = [System.Diagnostics.Process]::new()
        $process.StartInfo = $startInfo
        [void]$process.Start()
        $stdout = $process.StandardOutput.ReadToEnd()
        $stderr = $process.StandardError.ReadToEnd()
        $process.WaitForExit()

        return [ordered]@{
            executable = $FilePath
            arguments = @($ArgumentList)
            return_code = $process.ExitCode
            stdout = $stdout
            stderr = $stderr
        }
    } catch {
        return [ordered]@{
            executable = $FilePath
            arguments = @($ArgumentList)
            return_code = $null
            stdout = ""
            stderr = $_.Exception.Message
        }
    }
}

function Get-PnpPropertyValue {
    param(
        [Parameter(Mandatory)][string]$InstanceId,
        [Parameter(Mandatory)][string]$KeyName
    )

    try {
        $property = Get-PnpDeviceProperty -InstanceId $InstanceId -KeyName $KeyName -ErrorAction Stop
        return $property.Data
    } catch {
        return $null
    }
}

function Get-UsbDeviceRecords {
    param([Parameter(Mandatory)][string]$Pattern)

    if (-not (Get-Command Get-PnpDevice -ErrorAction SilentlyContinue)) {
        return @()
    }

    $records = @()
    $devices = Get-PnpDevice -PresentOnly -ErrorAction SilentlyContinue |
        Where-Object { $_.InstanceId -match $Pattern }

    foreach ($device in $devices) {
        $records += [ordered]@{
            status = $device.Status
            class = $device.Class
            friendly_name = $device.FriendlyName
            instance_id = $device.InstanceId
            parent = Get-PnpPropertyValue -InstanceId $device.InstanceId -KeyName "DEVPKEY_Device_Parent"
            container_id = Get-PnpPropertyValue -InstanceId $device.InstanceId -KeyName "DEVPKEY_Device_ContainerId"
            location_paths = @(Get-PnpPropertyValue -InstanceId $device.InstanceId -KeyName "DEVPKEY_Device_LocationPaths")
            location_info = Get-PnpPropertyValue -InstanceId $device.InstanceId -KeyName "DEVPKEY_Device_LocationInfo"
            driver_provider = Get-PnpPropertyValue -InstanceId $device.InstanceId -KeyName "DEVPKEY_Device_DriverProvider"
            driver_version = Get-PnpPropertyValue -InstanceId $device.InstanceId -KeyName "DEVPKEY_Device_DriverVersion"
        }
    }

    return @($records)
}

function Get-InstalledApplicationRecords {
    param([Parameter(Mandatory)][string]$Pattern)

    $paths = @(
        "HKLM:\Software\Microsoft\Windows\CurrentVersion\Uninstall\*",
        "HKLM:\Software\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall\*",
        "HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall\*"
    )

    $records = @()
    foreach ($path in $paths) {
        foreach ($item in (Get-ItemProperty $path -ErrorAction SilentlyContinue)) {
            $displayName = Get-ObjectPropertyValue -InputObject $item -Name "DisplayName"
            if ($displayName -and $displayName -match $Pattern) {
                $records += [ordered]@{
                    display_name = $displayName
                    display_version = Get-ObjectPropertyValue -InputObject $item -Name "DisplayVersion"
                    publisher = Get-ObjectPropertyValue -InputObject $item -Name "Publisher"
                    install_location = Get-ObjectPropertyValue -InputObject $item -Name "InstallLocation"
                    uninstall_string = Get-ObjectPropertyValue -InputObject $item -Name "UninstallString"
                    registry_path = Get-ObjectPropertyValue -InputObject $item -Name "PSPath"
                }
            }
        }
    }
    return @($records)
}

function Get-FileInventory {
    param([string]$Root)

    if (-not $Root) {
        return [ordered]@{ configured = $false; exists = $false; root = $null; files = @() }
    }

    $fullRoot = if ([IO.Path]::IsPathRooted($Root)) {
        [IO.Path]::GetFullPath($Root)
    } else {
        [IO.Path]::GetFullPath((Join-Path $RepoRoot $Root))
    }

    if (-not (Test-Path -LiteralPath $fullRoot)) {
        return [ordered]@{ configured = $true; exists = $false; root = $fullRoot; files = @() }
    }

    $files = @()
    foreach ($file in (Get-ChildItem -LiteralPath $fullRoot -Recurse -File -ErrorAction SilentlyContinue)) {
        $files += [ordered]@{
            path = $file.FullName
            length = $file.Length
            sha256 = (Get-FileHash -Algorithm SHA256 -LiteralPath $file.FullName).Hash.ToLowerInvariant()
        }
    }

    return [ordered]@{ configured = $true; exists = $true; root = $fullRoot; files = @($files) }
}

function Get-TrimmedOutput {
    param([Parameter(Mandatory)]$CommandRecord)

    if ($null -eq $CommandRecord.stdout) {
        return ""
    }
    return ([string]$CommandRecord.stdout).Trim()
}

$repoFull = [IO.Path]::GetFullPath($RepoRoot)
if (-not (Test-Path -LiteralPath (Join-Path $repoFull ".git"))) {
    throw "RepoRoot is not a Git worktree: $repoFull"
}

if (-not $OutputPath) {
    $OutputPath = Join-Path $repoFull ".work\evidence\issue-22-workstation-capture-deps\readiness.json"
} elseif (-not [IO.Path]::IsPathRooted($OutputPath)) {
    $OutputPath = Join-Path $repoFull $OutputPath
}

$outputFull = [IO.Path]::GetFullPath($OutputPath)
$repoPrefix = $repoFull.TrimEnd([IO.Path]::DirectorySeparatorChar) + [IO.Path]::DirectorySeparatorChar
if (-not $outputFull.StartsWith($repoPrefix, [StringComparison]::OrdinalIgnoreCase)) {
    throw "OutputPath must remain inside the repository: $outputFull"
}

$relativeOutput = [IO.Path]::GetRelativePath($repoFull, $outputFull)
& git -C $repoFull check-ignore --quiet -- $relativeOutput
if ($LASTEXITCODE -ne 0) {
    throw "OutputPath is not Git-ignored: $relativeOutput"
}

$outputDirectory = Split-Path -Parent $outputFull
New-Item -ItemType Directory -Force -Path $outputDirectory | Out-Null

$usbPcap = Get-CommandRecord -Name "USBPcapCMD.exe"
$tshark = Get-CommandRecord -Name "tshark.exe"
$wireshark = Get-CommandRecord -Name "Wireshark.exe"
$python = Get-CommandRecord -Name "python.exe"
$pwsh = Get-CommandRecord -Name "pwsh.exe"
$git = Get-CommandRecord -Name "git.exe"
if (-not $git.present -or -not $git.path) {
    throw "git.exe was not found."
}

$usbPcapEnumeration = $null
if ($usbPcap.present -and $usbPcap.path) {
    $usbPcapEnumeration = Invoke-ReadOnlyCommand -FilePath $usbPcap.path -ArgumentList @("-d")
}

$gitStatus = Invoke-ReadOnlyCommand -FilePath $git.path -ArgumentList @("-C", $repoFull, "status", "--short", "--branch")
$gitHead = Invoke-ReadOnlyCommand -FilePath $git.path -ArgumentList @("-C", $repoFull, "rev-parse", "HEAD")
$gitBranch = Invoke-ReadOnlyCommand -FilePath $git.path -ArgumentList @("-C", $repoFull, "branch", "--show-current")
$gitRemoteHead = Invoke-ReadOnlyCommand -FilePath $git.path -ArgumentList @("-C", $repoFull, "rev-parse", "origin/issue-22-workstation-capture-deps")

$driveName = [IO.Path]::GetPathRoot($outputFull).TrimEnd('\').TrimEnd(':')
$drive = Get-PSDrive -Name $driveName -ErrorAction SilentlyContinue
$disk = if ($drive) {
    [ordered]@{
        root = $drive.Root
        free_bytes = [int64]$drive.Free
        free_gib = [Math]::Round($drive.Free / 1GB, 3)
        two_gib_gate_passes = ($drive.Free -ge 2GB)
    }
} else {
    [ordered]@{ root = [IO.Path]::GetPathRoot($outputFull); free_bytes = $null; free_gib = $null; two_gib_gate_passes = $false }
}

$kvmDevices = Get-UsbDeviceRecords -Pattern "VID_2B77&PID_3661"
$beagleDevices = Get-UsbDeviceRecords -Pattern "VID_1679&PID_2001"
$hubDevices = Get-UsbDeviceRecords -Pattern "VID_2109&PID_0817"
$epiphanApps = Get-InstalledApplicationRecords -Pattern "Epiphan|KVM2USB"
$beagleApi = Get-FileInventory -Root $BeagleApiDir

$humanActions = @()
if (-not $usbPcap.present) { $humanActions += "Install USBPcap with explicit operator elevation; verify USBPcapCMD.exe and enumerate with -d." }
if (-not $tshark.present) { $humanActions += "Install Wireshark/TShark with explicit operator elevation; verify tshark --version." }
if (-not $wireshark.present) { $humanActions += "Verify the Wireshark GUI installation path and signed version." }
if ($epiphanApps.Count -eq 0) { $humanActions += "Install or verify the official signed Epiphan KVM2USB application and driver with explicit operator elevation." }
if (-not $beagleApi.exists) { $humanActions += "Stage the authorized Total Phase Windows Beagle API under ignored .work/vendor/totalphase and record hashes/provenance." }
if ($kvmDevices.Count -eq 0) { $humanActions += "Connect and verify the intended KVM2USB unit before any later experiment." }
if ($beagleDevices.Count -eq 0) { $humanActions += "Connect and verify the intended Total Phase Beagle device and driver." }
$humanActions += "Prove the exact USBPcap interface-to-KVM2USB root-hub mapping from PnP parent/location evidence and USBPcapCMD.exe -d output."
$humanActions += "Record the physical cable path, Beagle position, exact target identity, and harmless non-sensitive target state."

$record = [ordered]@{
    schema_version = 1
    generated_utc = Get-UtcTimestamp
    repository = "SemperSupra/AgentKVM2USB"
    issue = 22
    branch = Get-TrimmedOutput -CommandRecord $gitBranch
    head = Get-TrimmedOutput -CommandRecord $gitHead
    remote_branch_head = Get-TrimmedOutput -CommandRecord $gitRemoteHead
    live_disabled = $true
    collector_safety = [ordered]@{
        installs_software = $false
        elevates_privileges = $false
        starts_capture = $false
        sends_target_input = $false
        changes_hardware_topology = $false
        writes_only_ignored_readiness_json = $true
    }
    git = [ordered]@{
        status = $gitStatus
        output_path = $relativeOutput
        output_is_ignored = $true
    }
    tools = [ordered]@{
        usbpcap = $usbPcap
        tshark = $tshark
        wireshark = $wireshark
        python = $python
        pwsh = $pwsh
        usbpcap_enumeration = $usbPcapEnumeration
    }
    installed_epiphan_applications = @($epiphanApps)
    devices = [ordered]@{
        kvm2usb = @($kvmDevices)
        beagle = @($beagleDevices)
        via_vl817 = @($hubDevices)
    }
    beagle_api = $beagleApi
    disk = $disk
    mapping = [ordered]@{
        status = "unproven"
        selected_interface = $null
        reason = "The collector records enumeration and PnP evidence but never infers a root-hub mapping."
    }
    topology = [ordered]@{
        cable_path_confirmed = $false
        beagle_position_confirmed = $false
        target_identity_confirmed = $false
        harmless_target_state_confirmed = $false
    }
    human_actions = @($humanActions)
}

$json = if ($Pretty) { $record | ConvertTo-Json -Depth 12 } else { $record | ConvertTo-Json -Depth 12 -Compress }
Set-Content -LiteralPath $outputFull -Value $json -Encoding utf8

Write-Output $json
