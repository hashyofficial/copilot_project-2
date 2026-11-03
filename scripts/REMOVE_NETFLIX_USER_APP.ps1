# Build 6 final post-flash Netflix cleanup for user-installed /data/app package.
# Stock Xiaomi super.img does not contain com.netflix.mediaclient.
# Requires Android fully booted, USB debugging enabled and authorized.
# Removes only Netflix via Android Package Manager; never touches partitions,
# root files or system apps. Android normally removes package APK folder and app data.

param([string]$Adb = "adb")
$ErrorActionPreference = "Stop"
Write-Host "Checking connected Android device..."
& $Adb devices
if ($LASTEXITCODE -ne 0) { throw "ADB is not available. Connect tablet, enable USB debugging and authorize PC." }
$serials = @(& $Adb devices | Select-String "^\S+\s+device\s*$")
if ($serials.Count -ne 1) { throw "Expected exactly one authorized Android device, got $($serials.Count). No uninstall performed." }
$paths = @(& $Adb shell pm path com.netflix.mediaclient)
if ($LASTEXITCODE -ne 0) { throw "Cannot query Netflix package location. No uninstall performed." }
if (-not ($paths -match "^package:")) {
    Write-Host "PASS: Netflix is not installed. No changes needed."
    exit 0
}
Write-Host "Found installed Netflix APK location(s):"
$paths | ForEach-Object { Write-Host $_ }
Write-Host "Uninstalling com.netflix.mediaclient using Android Package Manager..."
$result = @(& $Adb uninstall com.netflix.mediaclient)
if ($LASTEXITCODE -ne 0 -or -not ($result -match "^Success")) {
    throw "Netflix uninstall failed: $($result -join '; ')"
}
$after = @(& $Adb shell pm path com.netflix.mediaclient)
if ($LASTEXITCODE -ne 0) { throw "Could not verify package removal" }
if ($after -match "^package:") { throw "Netflix APK still present; check other device users or automatic restore" }
Write-Host "PASS: Netflix user-installed APK no longer found after uninstall."
Write-Host "Android removed the package through its package manager; no manual /data/app deletion attempted."
