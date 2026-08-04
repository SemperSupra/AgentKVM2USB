[CmdletBinding()]
param(
    [string]$SourceDirectory = 'C:\Users\Mark\Downloads\TotalPhase',
    [string]$DestinationDirectory = (Join-Path (Split-Path -Parent (Split-Path -Parent $PSScriptRoot)) '.work\vendor\totalphase'),
    [switch]$Force
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

function Get-RepoRoot {
    return (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
}

if (-not (Test-Path -LiteralPath $SourceDirectory -PathType Container)) {
    throw "Total Phase download directory was not found: $SourceDirectory"
}

$repoRoot = Get-RepoRoot
if (-not [System.IO.Path]::IsPathRooted($DestinationDirectory)) {
    $DestinationDirectory = Join-Path $repoRoot $DestinationDirectory
}

$sourceRoot = (Resolve-Path -LiteralPath $SourceDirectory).Path
$stageRoot = [System.IO.Path]::GetFullPath($DestinationDirectory)
$filesRoot = Join-Path $stageRoot 'files'
$extractRoot = Join-Path $stageRoot 'extracted'

if ($Force -and (Test-Path -LiteralPath $stageRoot)) {
    Remove-Item -LiteralPath $stageRoot -Recurse -Force
}
New-Item -ItemType Directory -Force -Path $filesRoot, $extractRoot | Out-Null

$inventory = [System.Collections.Generic.List[object]]::new()
$sourceFiles = @(Get-ChildItem -LiteralPath $sourceRoot -File -Recurse | Sort-Object FullName)
if ($sourceFiles.Count -eq 0) {
    throw "No files were found under $sourceRoot"
}

foreach ($file in $sourceFiles) {
    $relative = $file.FullName.Substring($sourceRoot.Length).TrimStart([char[]]@('\','/'))
    $safeRelative = $relative -replace '[:*?"<>|]', '_'
    $target = Join-Path $filesRoot $safeRelative
    New-Item -ItemType Directory -Force -Path (Split-Path -Parent $target) | Out-Null
    Copy-Item -LiteralPath $file.FullName -Destination $target -Force

    $hash = Get-FileHash -LiteralPath $target -Algorithm SHA256
    $kind = 'other'
    $lower = $file.Name.ToLowerInvariant()
    if ($lower -match 'beagle.*api|api.*beagle') { $kind = 'beagle-api' }
    elseif ($lower -match 'data.?center') { $kind = 'data-center' }
    elseif ($lower -match 'driver|usb.*(win|linux)') { $kind = 'usb-driver' }

    $inventory.Add([pscustomobject]@{
        relative_path = $safeRelative.Replace('\','/')
        original_path = $file.FullName
        file_name = $file.Name
        length = $file.Length
        sha256 = $hash.Hash.ToLowerInvariant()
        classified_as = $kind
    })
}

$archives = Get-ChildItem -LiteralPath $filesRoot -File -Recurse | Where-Object {
    $_.Extension -in '.zip', '.7z', '.tar', '.gz', '.tgz', '.xz' -or $_.Name -match '\.tar\.(gz|xz)$'
}
foreach ($archive in $archives) {
    $archiveHash = (Get-FileHash -LiteralPath $archive.FullName -Algorithm SHA256).Hash.ToLowerInvariant()
    $outDir = Join-Path $extractRoot $archiveHash.Substring(0,16)
    if (Test-Path -LiteralPath $outDir) { continue }
    New-Item -ItemType Directory -Force -Path $outDir | Out-Null
    try {
        if ($archive.Extension -eq '.zip') {
            Expand-Archive -LiteralPath $archive.FullName -DestinationPath $outDir -Force
        } elseif (Get-Command tar.exe -ErrorAction SilentlyContinue) {
            & tar.exe -xf $archive.FullName -C $outDir
            if ($LASTEXITCODE -ne 0) { throw "tar exited with $LASTEXITCODE" }
        } elseif (Get-Command 7z.exe -ErrorAction SilentlyContinue) {
            & 7z.exe x '-y' "-o$outDir" $archive.FullName | Out-Null
            if ($LASTEXITCODE -ne 0) { throw "7z exited with $LASTEXITCODE" }
        } else {
            throw 'No extractor is available for this archive type.'
        }
    } catch {
        Set-Content -LiteralPath (Join-Path $outDir 'EXTRACTION_ERROR.txt') -Value $_.Exception.Message -Encoding UTF8
    }
}

$linuxCandidates = Get-ChildItem -LiteralPath $extractRoot -File -Recurse -ErrorAction SilentlyContinue | Where-Object {
    $_.Name -match '^(beagle\.so|libbeagle\.so.*)$'
} | ForEach-Object {
    [pscustomobject]@{
        relative_path = $_.FullName.Substring($stageRoot.Length).TrimStart([char[]]@('\','/')).Replace('\','/')
        file_name = $_.Name
        length = $_.Length
        sha256 = (Get-FileHash -LiteralPath $_.FullName -Algorithm SHA256).Hash.ToLowerInvariant()
    }
}

$windowsCandidates = Get-ChildItem -LiteralPath $extractRoot -File -Recurse -ErrorAction SilentlyContinue | Where-Object {
    $_.Name -match '^(beagle\.dll|beagle_py\.py|beagle\.h|beagle\.lib)$'
} | ForEach-Object {
    [pscustomobject]@{
        relative_path = $_.FullName.Substring($stageRoot.Length).TrimStart([char[]]@('\','/')).Replace('\','/')
        file_name = $_.Name
        length = $_.Length
        sha256 = (Get-FileHash -LiteralPath $_.FullName -Algorithm SHA256).Hash.ToLowerInvariant()
    }
}

$manifest = [ordered]@{
    schema_version = 1
    generated_utc = [DateTime]::UtcNow.ToString('o')
    source_directory = $sourceRoot
    staged_directory = $stageRoot
    source_file_count = $inventory.Count
    files = $inventory
    linux_beagle_api_candidates = @($linuxCandidates)
    windows_beagle_api_candidates = @($windowsCandidates)
    notes = @(
        'Vendor files are staged under .work and must remain outside Git.',
        'The Linux x86-64 Beagle API is preferred for containerized capture.',
        'The missing Linux Beagle API blocks only containerized live capture; a Windows host shim emits the same JSONL for container analysis.',
        'The Windows driver and Data Center application are retained only for differential testing when required.'
    )
}

$manifestPath = Join-Path $stageRoot 'inventory.json'
$manifest | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $manifestPath -Encoding UTF8
Write-Host "Staged $($inventory.Count) Total Phase files in $stageRoot"
Write-Host "Linux Beagle API candidates: $(@($linuxCandidates).Count)"
Write-Host "Windows Beagle API candidates: $(@($windowsCandidates).Count)"
Write-Host "Inventory: $manifestPath"
