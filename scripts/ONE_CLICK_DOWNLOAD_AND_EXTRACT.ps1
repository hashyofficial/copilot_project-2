# ONE CLICK FINAL FIRMWARE DOWNLOADER
# GitHub Releases limits individual assets to 2 GiB; full firmware.zip exceeds that.
# Download this ONE script and run it in PowerShell. The script downloads each
# part automatically, validates both segment and combined ZIP SHA256, extracts
# a complete Xiaomi fastboot firmware directory and verifies all six files.
# IMPORTANT: this script NEVER flashes, formats, or changes the tablet.
param([switch]$KeepParts)
$ErrorActionPreference = "Stop"
$base = "https://github.com/hashyofficial/copilot_project-2/releases/download/v1.0.0"
$root = $PSScriptRoot
$zipName = "firmware.zip"
$zipPath = Join-Path $root $zipName
$partFile = "PARTS_SHA256.txt"
$zipHashFile = "ZIP_SHA256.txt"
$imageHashFile = "FASTBOOT_IMAGE_SHA256.txt"
$verifyScript = "VERIFY_FINAL_FASTBOOT.ps1"

function Get-ReleaseFile([string]$Name) {
    $target = Join-Path $root $Name
    if (Test-Path -LiteralPath $target -PathType Leaf) { return }
    $url = "$base/$Name"
    Write-Host "Downloading $Name ..."
    $partial = "$target.download"
    & curl.exe -fL --retry 5 --retry-delay 3 --retry-all-errors -C - --output $partial $url
    if ($LASTEXITCODE -ne 0 -or -not (Test-Path -LiteralPath $partial -PathType Leaf)) {
        throw "Download failed: $Name. Internet connection or GitHub asset may be unavailable."
    }
    Move-Item -LiteralPath $partial -Destination $target -Force
}
function Verify-Sha256([string]$Name,[string]$Expected) {
    $local = Join-Path $root $Name
    if (-not (Test-Path -LiteralPath $local -PathType Leaf)) { throw "Missing: $Name" }
    $got=(Get-FileHash -LiteralPath $local -Algorithm SHA256).Hash.ToLowerInvariant()
    if ($got -ne $Expected.ToLowerInvariant()) { throw "SHA256 MISMATCH for $Name. Do not use this firmware." }
    Write-Host "VERIFIED SHA256: $Name"
}

Get-ReleaseFile $partFile
Get-ReleaseFile $zipHashFile
Get-ReleaseFile $imageHashFile
Get-ReleaseFile $verifyScript
$parts = @()
foreach ($line in Get-Content -LiteralPath (Join-Path $root $partFile)) {
    if ($line -notmatch '^([a-fA-F0-9]{64})  (firmware\.zip\.part[0-9]{3})$') {
        throw "Unexpected part checksum entry: $line"
    }
    $parts += [PSCustomObject]@{Name=$Matches[2];SHA=$Matches[1]}
}
if ($parts.Count -lt 2 -or $parts.Count -gt 10) { throw "Missing or extra firmware parts" }
$parts = @($parts | Sort-Object Name)
for ($i=0;$i -lt $parts.Count;$i++) {
    $num = [int]($parts[$i].Name.Substring($parts[$i].Name.Length-3))
    if ($num -ne ($i+1)) { throw "Firmware part number is missing or out of sequence" }
}
foreach ($part in $parts) {
    $p=Join-Path $root $part.Name
    if ((Test-Path -LiteralPath $p -PathType Leaf) -and ((Get-FileHash -LiteralPath $p -Algorithm SHA256).Hash -ine $part.SHA)) {
        Remove-Item -LiteralPath $p -Force
    }
    Get-ReleaseFile $part.Name
    Verify-Sha256 $part.Name $part.SHA
}
$line=(Get-Content -LiteralPath (Join-Path $root $zipHashFile) | Select-Object -First 1)
if ($line -notmatch '^([a-fA-F0-9]{64})  firmware\.zip$') { throw "Invalid complete ZIP checksum manifest" }
$expectedZip=$Matches[1]
if (Test-Path -LiteralPath $zipPath -PathType Leaf) {
    Verify-Sha256 $zipName $expectedZip
} else {
    Write-Host "Creating firmware.zip from verified parts (automatic, no manual merging)..."
    $out=[System.IO.File]::Create($zipPath)
    try {
        foreach($part in $parts) {
            $src=[System.IO.File]::OpenRead((Join-Path $root $part.Name))
            try { $src.CopyTo($out) } finally { $src.Dispose() }
        }
    } finally { $out.Dispose() }
    Verify-Sha256 $zipName $expectedZip
}
$folder=Join-Path $root "FINAL_FIRMWARE_EXTRACTED"
if (Test-Path -LiteralPath $folder) {
    throw "Extraction folder already exists: $folder. Rename or delete it before a new extraction to prevent mixing images."
}
Write-Host "Extracting full firmware.zip..."
Add-Type -AssemblyName System.IO.Compression.FileSystem
[System.IO.Compression.ZipFile]::ExtractToDirectory($zipPath,$folder)
$fw=Join-Path $folder "yunluo_global_images_OS1.0.9.0.ULYMIXM_14.0"
if (-not (Test-Path -LiteralPath (Join-Path $fw "flash_all.bat") -PathType Leaf)) {
    throw "Firmware extraction did not produce expected original Xiaomi flash_all.bat"
}
Write-Host "Verifying extracted super, KernelSU Next boot, vbmeta, CRC lists and flash_all.bat..."
& powershell.exe -NoProfile -ExecutionPolicy Bypass -File (Join-Path $root $verifyScript) -FirmwareDir $fw
if ($LASTEXITCODE -ne 0) { throw "Extracted firmware SHA256 verification failed! Do not flash." }
Write-Host ""
Write-Host "PASS: complete firmware.zip reassembled and verified. No flashing was performed."
Write-Host "READY: $fw"
Write-Host "Bootloader must remain unlocked. Original flash_all.bat may erase data."
if (-not $KeepParts) {
    Write-Host "All parts retained for reproducibility. Delete *.partNNN manually ONLY after verified extraction if you need disk space."
}
