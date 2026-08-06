[CmdletBinding(DefaultParameterSetName = "Plan", SupportsShouldProcess = $true)]
param(
    [Parameter(ParameterSetName = "Plan")]
    [switch]$Plan,

    [Parameter(Mandatory = $true, ParameterSetName = "Install")]
    [ValidateSet("Wireshark", "USBPcap")]
    [string]$Install,

    [Parameter(Mandatory = $true, ParameterSetName = "Stage")]
    [ValidateSet("TotalPhaseBeagleApi", "EpiphanKvmApp")]
    [string]$StageVendorArtifact,

    [Parameter(Mandatory = $true, ParameterSetName = "Stage")]
    [string]$Path,

    [Parameter(Mandatory = $true, ParameterSetName = "Stage")]
    [string]$SourcePage,

    [Parameter(Mandatory = $true, ParameterSetName = "Stage")]
    [string]$AcquiredUtc,

    [Parameter(Mandatory = $true, ParameterSetName = "InstallVendor")]
    [ValidateSet("EpiphanKvmApp")]
    [string]$InstallStagedVendorArtifact,

    [Parameter(Mandatory = $true, ParameterSetName = "InstallVendor")]
    [string]$StagedPath,

    [Parameter(DontShow = $true)]
    [switch]$ElevatedChild,

    [string]$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path,
    [string]$OutputPath
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$RepositoryName = "SemperSupra/AgentKVM2USB"
$WiresharkPackageId = "WiresharkFoundation.Wireshark"
$WiresharkPackageSource = "winget"
$UsbPcapPolicyIssue = "SemperSupra/windows-package-foundry#1"
$UsbPcapPackageIssue = "SemperSupra/windows-package-foundry#2"
$ExpectedHelperRepository = "SupraCraft/minecraft-infra"
$HelperRelativePath = "scripts\local\Invoke-Elevated.ps1"
$TotalPhaseStagingRoot = ".work\vendor\totalphase"
$EpiphanStagingRoot = ".work\vendor\epiphan"

function Get-UtcTimestamp {
    return [DateTime]::UtcNow.ToString("o")
}

function Get-PropertyValue {
    param(
        [Parameter(Mandatory = $true)]$InputObject,
        [Parameter(Mandatory = $true)][string]$Name
    )

    if ($null -eq $InputObject) { return $null }
    $property = $InputObject.PSObject.Properties[$Name]
    if ($null -eq $property) { return $null }
    return $property.Value
}

function Test-IsAdministrator {
    $identity = [Security.Principal.WindowsIdentity]::GetCurrent()
    $principal = New-Object Security.Principal.WindowsPrincipal($identity)
    return $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
}

function Get-RelativePath {
    param(
        [Parameter(Mandatory = $true)][string]$BasePath,
        [Parameter(Mandatory = $true)][string]$TargetPath
    )

    $baseFull = [IO.Path]::GetFullPath($BasePath).TrimEnd('\') + '\'
    $targetFull = [IO.Path]::GetFullPath($TargetPath)
    $baseUri = New-Object System.Uri($baseFull)
    $targetUri = New-Object System.Uri($targetFull)
    return [Uri]::UnescapeDataString($baseUri.MakeRelativeUri($targetUri).ToString()).Replace('/', '\')
}

function Test-IsInsidePath {
    param(
        [Parameter(Mandatory = $true)][string]$ParentPath,
        [Parameter(Mandatory = $true)][string]$CandidatePath
    )

    $parentFull = [IO.Path]::GetFullPath($ParentPath).TrimEnd('\') + '\'
    $candidateFull = [IO.Path]::GetFullPath($CandidatePath)
    return $candidateFull.StartsWith($parentFull, [StringComparison]::OrdinalIgnoreCase)
}

function Assert-GitIgnoredPath {
    param(
        [Parameter(Mandatory = $true)][string]$RepositoryRoot,
        [Parameter(Mandatory = $true)][string]$CandidatePath
    )

    if (-not (Test-IsInsidePath -ParentPath $RepositoryRoot -CandidatePath $CandidatePath)) {
        throw "Path must remain inside the repository: $CandidatePath"
    }

    $relative = Get-RelativePath -BasePath $RepositoryRoot -TargetPath $CandidatePath
    & git -C $RepositoryRoot check-ignore --quiet -- $relative
    if ($LASTEXITCODE -ne 0) {
        throw "Path is not Git-ignored: $relative"
    }
    return $relative
}

function Get-CommandRecord {
    param([Parameter(Mandatory = $true)][string]$Name)

    $command = Get-Command $Name -ErrorAction SilentlyContinue | Select-Object -First 1
    if (-not $command) {
        return [ordered]@{ name = $Name; present = $false; path = $null; version = $null }
    }

    $commandPath = Get-PropertyValue -InputObject $command -Name "Source"
    if (-not $commandPath) { $commandPath = Get-PropertyValue -InputObject $command -Name "Path" }

    $version = $null
    try {
        $commandVersion = Get-PropertyValue -InputObject $command -Name "Version"
        if ($commandVersion) {
            $version = $commandVersion.ToString()
        } elseif ($commandPath -and (Test-Path -LiteralPath $commandPath)) {
            $version = (Get-Item -LiteralPath $commandPath).VersionInfo.FileVersion
        }
    } catch {}

    return [ordered]@{ name = $Name; present = $true; path = $commandPath; version = $version }
}

function Get-ExecutableRecord {
    param(
        [Parameter(Mandatory = $true)][string]$Name,
        [string[]]$KnownPaths = @()
    )

    $record = Get-CommandRecord -Name $Name
    if ($record.present) { return $record }

    foreach ($knownPath in $KnownPaths) {
        if ($knownPath -and (Test-Path -LiteralPath $knownPath -PathType Leaf)) {
            $item = Get-Item -LiteralPath $knownPath
            return [ordered]@{
                name = $Name
                present = $true
                path = $item.FullName
                version = $item.VersionInfo.FileVersion
            }
        }
    }
    return $record
}

function Invoke-ExternalCommand {
    param(
        [Parameter(Mandatory = $true)][string]$FilePath,
        [string[]]$ArgumentList = @()
    )

    $output = & $FilePath @ArgumentList 2>&1 | Out-String
    return [ordered]@{
        executable = $FilePath
        arguments = @($ArgumentList)
        return_code = $LASTEXITCODE
        output = $output.Trim()
    }
}

function Get-InstalledApplicationRecords {
    param([Parameter(Mandatory = $true)][string]$Pattern)

    $registryPaths = @(
        "HKLM:\Software\Microsoft\Windows\CurrentVersion\Uninstall\*",
        "HKLM:\Software\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall\*",
        "HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall\*"
    )

    $records = @()
    foreach ($registryPath in $registryPaths) {
        foreach ($item in @(Get-ItemProperty $registryPath -ErrorAction SilentlyContinue)) {
            $displayName = Get-PropertyValue -InputObject $item -Name "DisplayName"
            if ($displayName -and $displayName -match $Pattern) {
                $records += [ordered]@{
                    display_name = $displayName
                    display_version = Get-PropertyValue -InputObject $item -Name "DisplayVersion"
                    publisher = Get-PropertyValue -InputObject $item -Name "Publisher"
                    install_location = Get-PropertyValue -InputObject $item -Name "InstallLocation"
                    registry_path = Get-PropertyValue -InputObject $item -Name "PSPath"
                }
            }
        }
    }
    return @($records)
}

function Get-PnpRecords {
    param([Parameter(Mandatory = $true)][string]$Pattern)

    if (-not (Get-Command Get-PnpDevice -ErrorAction SilentlyContinue)) { return @() }

    $records = @()
    foreach ($device in @(Get-PnpDevice -PresentOnly -ErrorAction SilentlyContinue | Where-Object { $_.InstanceId -match $Pattern })) {
        $provider = $null
        $version = $null
        try { $provider = (Get-PnpDeviceProperty -InstanceId $device.InstanceId -KeyName "DEVPKEY_Device_DriverProvider" -ErrorAction Stop).Data } catch {}
        try { $version = (Get-PnpDeviceProperty -InstanceId $device.InstanceId -KeyName "DEVPKEY_Device_DriverVersion" -ErrorAction Stop).Data } catch {}
        $records += [ordered]@{
            status = $device.Status
            class = $device.Class
            friendly_name = $device.FriendlyName
            instance_id = $device.InstanceId
            driver_provider = $provider
            driver_version = $version
        }
    }
    return @($records)
}

function Get-PendingRebootRecord {
    $componentServicing = Test-Path "HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Component Based Servicing\RebootPending"
    $windowsUpdate = Test-Path "HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\WindowsUpdate\Auto Update\RebootRequired"
    $pendingRename = $false
    try {
        $value = (Get-ItemProperty "HKLM:\SYSTEM\CurrentControlSet\Control\Session Manager" -Name PendingFileRenameOperations -ErrorAction Stop).PendingFileRenameOperations
        $pendingRename = [bool]$value
    } catch {}

    return [ordered]@{
        pending = ($componentServicing -or $windowsUpdate -or $pendingRename)
        component_based_servicing = $componentServicing
        windows_update = $windowsUpdate
        pending_file_rename = $pendingRename
        reboot_initiated_by_script = $false
    }
}

function Get-TrustedUacHelper {
    $candidateRoots = @(
        (Join-Path $env:USERPROFILE "Projects\minecraft-infra"),
        (Join-Path $env:USERPROFILE "Projects\SupraCraft\minecraft-infra")
    )

    $candidates = @()
    foreach ($candidateRoot in $candidateRoots) {
        $helperPath = Join-Path $candidateRoot $HelperRelativePath
        if (-not (Test-Path -LiteralPath $helperPath -PathType Leaf)) { continue }

        $topLevel = (& git -C $candidateRoot rev-parse --show-toplevel 2>$null | Out-String).Trim()
        $remote = (& git -C $candidateRoot config --get remote.origin.url 2>$null | Out-String).Trim()
        $headSha = (& git -C $candidateRoot rev-parse HEAD 2>$null | Out-String).Trim()
        $helperGitPath = $HelperRelativePath.Replace('\', '/')

        & git -C $candidateRoot ls-files --error-unmatch -- $helperGitPath *> $null
        $tracked = ($LASTEXITCODE -eq 0)

        & git -C $candidateRoot diff --quiet -- $helperGitPath
        $worktreeClean = ($LASTEXITCODE -eq 0)

        & git -C $candidateRoot diff --cached --quiet -- $helperGitPath
        $indexClean = ($LASTEXITCODE -eq 0)

        $originRefsContainingHead = @(
            & git -C $candidateRoot branch -r --contains HEAD 2>$null |
                ForEach-Object { $_.Trim() } |
                Where-Object { $_ -match '^origin/' -and $_ -notmatch ' -> ' }
        )
        $headOnOrigin = ($originRefsContainingHead.Count -gt 0)

        $resolvedCandidate = [IO.Path]::GetFullPath($candidateRoot).TrimEnd('\')
        $resolvedTopLevel = if ($topLevel) { [IO.Path]::GetFullPath($topLevel).TrimEnd('\') } else { $null }
        $rootMatches = [bool]($resolvedTopLevel -and $resolvedCandidate.Equals($resolvedTopLevel, [StringComparison]::OrdinalIgnoreCase))
        $originMatches = [bool]($remote -and ($remote -match "(?i)(github\.com[:/])SupraCraft/minecraft-infra(?:\.git)?$"))
        $trusted = [bool]($rootMatches -and $originMatches -and $tracked -and $worktreeClean -and $indexClean -and $headOnOrigin)

        $candidates += [ordered]@{
            root = $candidateRoot
            helper_path = $helperPath
            helper_git_path = $helperGitPath
            git_top_level = $topLevel
            origin = $remote
            head_sha = $headSha
            origin_refs_containing_head = @($originRefsContainingHead)
            expected_repository = $ExpectedHelperRepository
            root_matches = $rootMatches
            origin_matches = $originMatches
            tracked = $tracked
            worktree_clean = $worktreeClean
            index_clean = $indexClean
            head_on_origin = $headOnOrigin
            trusted = $trusted
            sha256 = (Get-FileHash -Algorithm SHA256 -LiteralPath $helperPath).Hash.ToLowerInvariant()
        }
    }

    $trustedCandidates = @($candidates | Where-Object { $_.trusted })
    if ($trustedCandidates.Count -gt 1) {
        throw "More than one trusted minecraft-infra helper checkout was found. Resolve the workspace ambiguity before elevation."
    }

    return [ordered]@{
        candidates = @($candidates)
        found = ($candidates.Count -gt 0)
        trusted = ($trustedCandidates.Count -eq 1)
        selected = if ($trustedCandidates.Count -eq 1) { $trustedCandidates[0] } else { $null }
    }
}

function Get-SanitizedSourcePage {
    param([Parameter(Mandatory = $true)][string]$Value)

    [Uri]$uri = $null
    if (-not [Uri]::TryCreate($Value, [UriKind]::Absolute, [ref]$uri)) {
        throw "SourcePage must be an absolute authoritative vendor page URL."
    }
    if ($uri.Scheme -ne "https") {
        throw "SourcePage must use HTTPS."
    }
    if ($uri.Query -or $uri.Fragment -or $uri.UserInfo) {
        throw "SourcePage must not contain a query, fragment, credentials, token, or personalized data."
    }
    return $uri.GetLeftPart([UriPartial]::Path)
}

function Get-NormalizedAcquiredUtc {
    param([Parameter(Mandatory = $true)][string]$Value)

    [DateTimeOffset]$parsed = [DateTimeOffset]::MinValue
    if (-not [DateTimeOffset]::TryParse($Value, [ref]$parsed)) {
        throw "AcquiredUtc must be a valid ISO-8601 timestamp."
    }
    return $parsed.ToUniversalTime().ToString("o")
}

function Get-AuthenticodeRecord {
    param([Parameter(Mandatory = $true)][string]$FilePath)

    try {
        $signature = Get-AuthenticodeSignature -LiteralPath $FilePath
        return [ordered]@{
            status = $signature.Status.ToString()
            status_message = $signature.StatusMessage
            signer_subject = if ($signature.SignerCertificate) { $signature.SignerCertificate.Subject } else { $null }
            signer_thumbprint = if ($signature.SignerCertificate) { $signature.SignerCertificate.Thumbprint } else { $null }
        }
    } catch {
        return [ordered]@{ status = "Unavailable"; status_message = $_.Exception.Message; signer_subject = $null; signer_thumbprint = $null }
    }
}

function Get-StagedArtifactRecords {
    param([Parameter(Mandatory = $true)][string]$RepositoryRoot)

    $records = @()
    $vendorRoots = [ordered]@{
        "totalphase" = $TotalPhaseStagingRoot
        "epiphan" = $EpiphanStagingRoot
    }
    foreach ($vendor in @($vendorRoots.Keys)) {
        $root = Join-Path $RepositoryRoot $vendorRoots[$vendor]
        if (-not (Test-Path -LiteralPath $root -PathType Container)) { continue }
        foreach ($metadataFile in @(Get-ChildItem -LiteralPath $root -Filter "*.provenance.json" -File -ErrorAction SilentlyContinue)) {
            try {
                $metadata = Get-Content -LiteralPath $metadataFile.FullName -Raw | ConvertFrom-Json
                $records += $metadata
            } catch {
                $records += [ordered]@{
                    vendor = $vendor
                    provenance_file = Get-RelativePath -BasePath $RepositoryRoot -TargetPath $metadataFile.FullName
                    valid = $false
                    error = $_.Exception.Message
                }
            }
        }
    }
    return @($records)
}

function Get-DependencyPlan {
    param([Parameter(Mandatory = $true)][string]$RepositoryRoot)

    $winget = Get-CommandRecord -Name "winget.exe"
    $wiresharkPaths = @()
    $tsharkPaths = @()
    if ($env:ProgramFiles) {
        $wiresharkPaths += (Join-Path $env:ProgramFiles "Wireshark\Wireshark.exe")
        $tsharkPaths += (Join-Path $env:ProgramFiles "Wireshark\tshark.exe")
    }
    if (${env:ProgramFiles(x86)}) {
        $wiresharkPaths += (Join-Path ${env:ProgramFiles(x86)} "Wireshark\Wireshark.exe")
        $tsharkPaths += (Join-Path ${env:ProgramFiles(x86)} "Wireshark\tshark.exe")
    }

    $helper = Get-TrustedUacHelper
    $usbPcap = Get-CommandRecord -Name "USBPcapCMD.exe"
    $wireshark = Get-ExecutableRecord -Name "Wireshark.exe" -KnownPaths $wiresharkPaths
    $tshark = Get-ExecutableRecord -Name "tshark.exe" -KnownPaths $tsharkPaths
    $epiphanApps = Get-InstalledApplicationRecords -Pattern "Epiphan|KVM2USB"
    $totalPhaseApps = Get-InstalledApplicationRecords -Pattern "Total Phase|Beagle"
    $kvmDevices = Get-PnpRecords -Pattern "VID_2B77&PID_3661"
    $beagleDevices = Get-PnpRecords -Pattern "VID_1679&PID_2001"
    $stagedArtifacts = Get-StagedArtifactRecords -RepositoryRoot $RepositoryRoot

    $hasTotalPhaseApi = @($stagedArtifacts | Where-Object { (Get-PropertyValue -InputObject $_ -Name "artifact_type") -eq "TotalPhaseBeagleApi" }).Count -gt 0
    $humanActions = @()
    if (-not $helper.trusted) { $humanActions += "Restore, fetch, or identify one clean tracked SupraCraft/minecraft-infra helper on an origin-backed commit before elevation." }
    if (-not $wireshark.present -or -not $tshark.present) { $humanActions += "Use the shared UAC helper to install exact package WiresharkFoundation.Wireshark from source winget." }
    if (-not $usbPcap.present) { $humanActions += "Complete windows-package-foundry #1/#2; USBPcap installation remains blocked with no fallback." }
    if (-not $hasTotalPhaseApi) { $humanActions += "Human downloads the authorized Total Phase artifact and stages it locally with provenance." }
    if (-not $epiphanApps) { $humanActions += "Human obtains and stages the authorized Epiphan installer; request shared-helper UAC only after its valid Epiphan signature is verified." }

    return [ordered]@{
        schema_version = 1
        generated_utc = Get-UtcTimestamp
        repository = $RepositoryName
        issue = 27
        live_disabled = $true
        safety = [ordered]@{
            plan_elevates = $false
            plan_installs = $false
            downloads_vendor_files = $false
            automates_vendor_login = $false
            starts_capture = $false
            sends_target_input = $false
            changes_topology = $false
            initiates_reboot = $false
        }
        shared_uac_helper = $helper
        tools = [ordered]@{
            winget = $winget
            wireshark = $wireshark
            tshark = $tshark
            usbpcap = $usbPcap
        }
        dispositions = @(
            [ordered]@{ dependency = "Wireshark/TShark"; disposition = "existing_winget"; package_id = $WiresharkPackageId; source = $WiresharkPackageSource; elevation = "shared_human_gated_uac" },
            [ordered]@{ dependency = "USBPcap"; disposition = "foundry_candidate_blocked"; policy_issue = $UsbPcapPolicyIssue; package_issue = $UsbPcapPackageIssue; direct_fallback = $false },
            [ordered]@{ dependency = "Total Phase Beagle software/API/driver"; disposition = "manual_vendor"; staging_root = ".work/vendor/totalphase" },
            [ordered]@{ dependency = "Epiphan KVM2USB application/driver"; disposition = "manual_vendor_license_review"; staging_root = ".work/vendor/epiphan" }
        )
        installed_applications = [ordered]@{
            epiphan = @($epiphanApps)
            total_phase = @($totalPhaseApps)
        }
        devices = [ordered]@{
            kvm2usb = @($kvmDevices)
            beagle = @($beagleDevices)
        }
        staged_artifacts = @($stagedArtifacts)
        pending_reboot = Get-PendingRebootRecord
        human_actions = @($humanActions)
    }
}

function Write-PlanEvidence {
    param(
        [Parameter(Mandatory = $true)][string]$RepositoryRoot,
        [Parameter(Mandatory = $true)]$Record,
        [string]$RequestedOutputPath
    )

    $path = $RequestedOutputPath
    if (-not $path) {
        $path = Join-Path $RepositoryRoot ".work\evidence\issue-27-operator-dependencies\plan.json"
    } elseif (-not [IO.Path]::IsPathRooted($path)) {
        $path = Join-Path $RepositoryRoot $path
    }

    $path = [IO.Path]::GetFullPath($path)
    [void](Assert-GitIgnoredPath -RepositoryRoot $RepositoryRoot -CandidatePath $path)
    New-Item -ItemType Directory -Force -Path (Split-Path -Parent $path) | Out-Null
    $json = $Record | ConvertTo-Json -Depth 12
    Set-Content -LiteralPath $path -Value $json -Encoding UTF8
    Write-Output $json
}

function Import-TrustedUacHelper {
    $helper = Get-TrustedUacHelper
    if (-not $helper.trusted -or -not $helper.selected) {
        throw "A single clean, tracked, origin-backed $ExpectedHelperRepository checkout with $HelperRelativePath is required."
    }

    $helperPath = $helper.selected.helper_path
    $module = New-Module -Name "AgentKvmMinecraftInfraUac" -ArgumentList $helperPath -ScriptBlock {
        param([string]$PathToHelper)
        . $PathToHelper
    }
    Import-Module $module -Force -ErrorAction Stop
    if (-not (Get-Command Invoke-Elevated -ErrorAction SilentlyContinue)) {
        throw "The trusted helper did not export Invoke-Elevated."
    }
    return $helper.selected
}

function Quote-ProcessArgument {
    param([Parameter(Mandatory = $true)][string]$Value)
    return '"' + $Value.Replace('"', '""') + '"'
}

function Assert-ElevatedChild {
    if (-not $ElevatedChild -or -not (Test-IsAdministrator)) {
        throw "This execution path requires the shared helper and an elevated child process."
    }
}

function Test-WiresharkInstallation {
    $planRecord = Get-DependencyPlan -RepositoryRoot $repoFull
    return ($planRecord.tools.wireshark.present -and $planRecord.tools.tshark.present)
}

function Install-WiresharkPackage {
    if ($ElevatedChild) {
        Assert-ElevatedChild
        $winget = Get-CommandRecord -Name "winget.exe"
        if (-not $winget.present -or -not $winget.path) { throw "winget.exe is required." }

        $arguments = @(
            "install",
            "--id", $WiresharkPackageId,
            "--exact",
            "--source", $WiresharkPackageSource,
            "--accept-package-agreements",
            "--accept-source-agreements",
            "--silent"
        )
        $result = Invoke-ExternalCommand -FilePath $winget.path -ArgumentList $arguments
        if ($result.return_code -ne 0) {
            throw "WinGet installation failed with return code $($result.return_code): $($result.output)"
        }
        if (-not (Test-WiresharkInstallation)) {
            throw "WinGet returned success, but Wireshark.exe and tshark.exe were not independently verified."
        }
        Write-Output ($result | ConvertTo-Json -Depth 6)
        return
    }

    [void](Import-TrustedUacHelper)
    $arguments = "-Install Wireshark -ElevatedChild -RepoRoot $(Quote-ProcessArgument -Value $repoFull)"
    [void](Invoke-Elevated `
        -Description "Install Wireshark and TShark for AgentKVM2USB issue #22" `
        -Actions @(
            "Install exact WinGet package $WiresharkPackageId from source $WiresharkPackageSource",
            "Write application files and registration that require administrator privileges",
            "Return for independent executable verification"
        ) `
        -ScriptPath $PSCommandPath `
        -Arguments $arguments `
        -EventId 1270)

    if (-not (Test-WiresharkInstallation)) {
        throw "Wireshark/TShark were not verified after the human-gated elevation attempt."
    }
    Write-Output "Wireshark and TShark verified. No capture was started."
}

function Stop-UsbPcapInstall {
    throw "USBPcap installation is blocked pending $UsbPcapPolicyIssue and $UsbPcapPackageIssue. No direct installer or alternate package-manager fallback is permitted."
}

function Stage-VendorArtifact {
    $sourceFull = [IO.Path]::GetFullPath((Resolve-Path -LiteralPath $Path).Path)
    if (-not (Test-Path -LiteralPath $sourceFull -PathType Leaf)) { throw "Vendor artifact is not a file: $sourceFull" }

    $sourcePageSanitized = Get-SanitizedSourcePage -Value $SourcePage
    $acquiredUtcNormalized = Get-NormalizedAcquiredUtc -Value $AcquiredUtc
    $vendor = if ($StageVendorArtifact -eq "TotalPhaseBeagleApi") { "totalphase" } else { "epiphan" }
    $stagingRoot = if ($StageVendorArtifact -eq "TotalPhaseBeagleApi") { $TotalPhaseStagingRoot } else { $EpiphanStagingRoot }
    $destinationRoot = Join-Path $repoFull $stagingRoot
    New-Item -ItemType Directory -Force -Path $destinationRoot | Out-Null
    [void](Assert-GitIgnoredPath -RepositoryRoot $repoFull -CandidatePath $destinationRoot)

    $destination = Join-Path $destinationRoot ([IO.Path]::GetFileName($sourceFull))
    $sourceHash = (Get-FileHash -Algorithm SHA256 -LiteralPath $sourceFull).Hash.ToLowerInvariant()

    if (Test-Path -LiteralPath $destination -PathType Leaf) {
        $destinationHash = (Get-FileHash -Algorithm SHA256 -LiteralPath $destination).Hash.ToLowerInvariant()
        if ($destinationHash -ne $sourceHash) {
            throw "A different artifact already uses the same staged filename. Resolve the collision without overwriting evidence."
        }
    } else {
        Copy-Item -LiteralPath $sourceFull -Destination $destination
    }

    $metadata = [ordered]@{
        schema_version = 1
        artifact_type = $StageVendorArtifact
        vendor = $vendor
        disposition = if ($vendor -eq "totalphase") { "manual_vendor" } else { "manual_vendor_license_review" }
        filename = [IO.Path]::GetFileName($destination)
        staged_path = Get-RelativePath -BasePath $repoFull -TargetPath $destination
        length = (Get-Item -LiteralPath $destination).Length
        sha256 = $sourceHash
        authenticode = Get-AuthenticodeRecord -FilePath $destination
        source_page = $sourcePageSanitized
        acquired_utc = $acquiredUtcNormalized
        staged_utc = Get-UtcTimestamp
        credentials_recorded = $false
        cookies_recorded = $false
        tokens_recorded = $false
        committed_to_git = $false
    }

    $metadataPath = $destination + ".provenance.json"
    $metadata | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $metadataPath -Encoding UTF8
    [void](Assert-GitIgnoredPath -RepositoryRoot $repoFull -CandidatePath $metadataPath)
    Write-Output ($metadata | ConvertTo-Json -Depth 8)
}

function Get-VerifiedStagedEpiphanInstaller {
    $epiphanRoot = Join-Path $repoFull $EpiphanStagingRoot
    $full = [IO.Path]::GetFullPath((Resolve-Path -LiteralPath $StagedPath).Path)
    if (-not (Test-IsInsidePath -ParentPath $epiphanRoot -CandidatePath $full)) {
        throw "Epiphan installer must be inside ignored .work/vendor/epiphan."
    }
    [void](Assert-GitIgnoredPath -RepositoryRoot $repoFull -CandidatePath $full)

    $extension = [IO.Path]::GetExtension($full).ToLowerInvariant()
    if ($extension -notin @(".exe", ".msi")) {
        throw "Only an explicitly staged .exe or .msi installer can be invoked. Archives remain stage-only."
    }

    $metadataPath = $full + ".provenance.json"
    if (-not (Test-Path -LiteralPath $metadataPath -PathType Leaf)) {
        throw "The staged installer is missing its provenance record."
    }
    $metadata = Get-Content -LiteralPath $metadataPath -Raw | ConvertFrom-Json
    if ((Get-PropertyValue -InputObject $metadata -Name "artifact_type") -ne "EpiphanKvmApp") {
        throw "The provenance record is not for EpiphanKvmApp."
    }

    $expectedHash = [string](Get-PropertyValue -InputObject $metadata -Name "sha256")
    $currentHash = (Get-FileHash -Algorithm SHA256 -LiteralPath $full).Hash.ToLowerInvariant()
    if (-not $expectedHash -or $currentHash -ne $expectedHash.ToLowerInvariant()) {
        throw "The staged installer hash no longer matches its provenance record."
    }

    $recordedAuthenticode = Get-PropertyValue -InputObject $metadata -Name "authenticode"
    $currentAuthenticode = Get-AuthenticodeRecord -FilePath $full
    if ($currentAuthenticode.status -ne "Valid") {
        throw "The staged Epiphan installer Authenticode signature is not valid."
    }
    if (-not $currentAuthenticode.signer_subject -or $currentAuthenticode.signer_subject -notmatch "(?i)Epiphan") {
        throw "The staged installer signer does not identify Epiphan."
    }
    if ($null -eq $recordedAuthenticode -or (Get-PropertyValue -InputObject $recordedAuthenticode -Name "status") -ne "Valid") {
        throw "The provenance record does not contain a valid Epiphan signature result."
    }
    $recordedThumbprint = [string](Get-PropertyValue -InputObject $recordedAuthenticode -Name "signer_thumbprint")
    if (-not $recordedThumbprint -or -not $currentAuthenticode.signer_thumbprint -or $recordedThumbprint -ne $currentAuthenticode.signer_thumbprint) {
        throw "The staged installer signer thumbprint no longer matches its provenance record."
    }

    return [ordered]@{
        path = $full
        metadata = $metadata
        extension = $extension
        authenticode = $currentAuthenticode
    }
}

function Install-StagedEpiphanArtifact {
    $verified = Get-VerifiedStagedEpiphanInstaller

    if ($ElevatedChild) {
        Assert-ElevatedChild
        $process = if ($verified.extension -eq ".msi") {
            $msiArguments = "/i `"$($verified.path)`""
            Start-Process -FilePath "msiexec.exe" -ArgumentList $msiArguments -Wait -PassThru
        } else {
            Start-Process -FilePath $verified.path -Wait -PassThru
        }
        if ($process.ExitCode -ne 0) {
            throw "The vendor installer exited with code $($process.ExitCode)."
        }
        $apps = Get-InstalledApplicationRecords -Pattern "Epiphan|KVM2USB"
        if (-not $apps) {
            throw "The vendor installer completed, but no Epiphan/KVM2USB installed-application record was verified."
        }
        Write-Output (@{ installed_applications = @($apps); pending_reboot = Get-PendingRebootRecord } | ConvertTo-Json -Depth 8)
        return
    }

    [void](Import-TrustedUacHelper)
    $filename = Get-PropertyValue -InputObject $verified.metadata -Name "filename"
    $sha256 = Get-PropertyValue -InputObject $verified.metadata -Name "sha256"
    $signer = Get-PropertyValue -InputObject $verified.authenticode -Name "signer_subject"
    $thumbprint = Get-PropertyValue -InputObject $verified.authenticode -Name "signer_thumbprint"
    $arguments = "-InstallStagedVendorArtifact EpiphanKvmApp -StagedPath $(Quote-ProcessArgument -Value $verified.path) -ElevatedChild -RepoRoot $(Quote-ProcessArgument -Value $repoFull)"
    [void](Invoke-Elevated `
        -Description "Run the exact staged Epiphan KVM2USB installer" `
        -Actions @(
            "Launch $filename with SHA-256 $sha256",
            "Require valid signer $signer with certificate thumbprint $thumbprint",
            "Allow the vendor installer to register its application and driver",
            "Require the operator to review and accept every interactive installer decision",
            "Return for independent application, driver, and reboot-state verification"
        ) `
        -ScriptPath $PSCommandPath `
        -Arguments $arguments `
        -EventId 1272)

    $apps = Get-InstalledApplicationRecords -Pattern "Epiphan|KVM2USB"
    if (-not $apps) {
        throw "No Epiphan/KVM2USB installed-application record was verified after the human-gated elevation attempt."
    }
    Write-Output (@{ installed_applications = @($apps); pending_reboot = Get-PendingRebootRecord } | ConvertTo-Json -Depth 8)
}

$repoFull = [IO.Path]::GetFullPath($RepoRoot)
if (-not (Test-Path -LiteralPath $repoFull -PathType Container)) { throw "RepoRoot does not exist: $repoFull" }
& git -C $repoFull rev-parse --is-inside-work-tree *> $null
if ($LASTEXITCODE -ne 0) { throw "RepoRoot is not a Git worktree: $repoFull" }

if ($WhatIfPreference -and $PSCmdlet.ParameterSetName -ne "Plan") {
    $preview = [ordered]@{
        what_if = $true
        requested_parameter_set = $PSCmdlet.ParameterSetName
        install = $Install
        stage_vendor_artifact = $StageVendorArtifact
        install_staged_vendor_artifact = $InstallStagedVendorArtifact
        elevated_child_started = $false
        installation_started = $false
        staging_started = $false
        vendor_installer_started = $false
        reboot_initiated = $false
    }
    Write-Output ($preview | ConvertTo-Json -Depth 4)
    return
}

switch ($PSCmdlet.ParameterSetName) {
    "Install" {
        if ($Install -eq "Wireshark") { Install-WiresharkPackage; break }
        if ($Install -eq "USBPcap") { Stop-UsbPcapInstall; break }
    }
    "Stage" {
        Stage-VendorArtifact
        break
    }
    "InstallVendor" {
        Install-StagedEpiphanArtifact
        break
    }
    default {
        $record = Get-DependencyPlan -RepositoryRoot $repoFull
        Write-PlanEvidence -RepositoryRoot $repoFull -Record $record -RequestedOutputPath $OutputPath
        break
    }
}
