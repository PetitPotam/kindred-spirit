# Kindred Spirit for a friend's Windows PC: gets the latest version, builds the mod, installs it.
# Run it after every update the host pushes (or double-click scripts\update-pip-windows.cmd).
#
#   powershell -ExecutionPolicy Bypass -File scripts\update-pip-windows.ps1
#   powershell -ExecutionPolicy Bypass -File scripts\update-pip-windows.ps1 -Minecraft 26.3   (switch versions)
#
# Needs: Git (signed in to GitHub), Java 25 (Temurin, to build), Minecraft with Fabric installed once, the same
# Minecraft version as the host's. Without -Minecraft it keeps the version of the Kindred jar already installed
# (the newest one the first time). Close Minecraft first: a running game keeps the old mod.
#
# For tests (.github/workflows/platforms.yml): -Here installs this copy as it is, without getting the latest
# version, and $env:APPDATA can point to a throwaway folder.

param([string]$Minecraft = "", [switch]$Here)
$ErrorActionPreference = "Stop"
$repo = Split-Path -Parent $PSScriptRoot
Set-Location $repo

if ($Here) {
    Write-Host "1/4  Using this copy as it is (-Here)." -ForegroundColor Cyan
} else {
    Write-Host "1/4  Getting the latest version..." -ForegroundColor Cyan
    # (fetch and match GitHub exactly, rather than pull: this copy is only for playing, and it keeps working
    #  even when the history on GitHub has been rewritten)
    git fetch origin
    if ($LASTEXITCODE -ne 0) { throw "Getting the latest version failed: are you signed in to GitHub?" }
    git reset --hard origin/main
    if ($LASTEXITCODE -ne 0) { throw "git reset failed" }
}

# Which Minecraft: the one asked for, else the one the installed Kindred jar is for, else the newest the mod supports
$mods = Join-Path $env:APPDATA ".minecraft\mods"
$supported = Get-ChildItem "mod\versions" -Directory | ForEach-Object { $_.Name } | Sort-Object { [version]$_ }
if (-not $Minecraft) {
    $installed = Get-ChildItem $mods -Filter "kindred-spirit-*.jar" -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($installed -and $installed.Name -match '\+([0-9.]+)\.jar$' -and $supported -contains $Matches[1]) { $Minecraft = $Matches[1] }
    else { $Minecraft = $supported | Select-Object -Last 1 }
}
if ($supported -notcontains $Minecraft) {
    throw "Kindred Spirit isn't made for Minecraft $Minecraft. It is for: $($supported -join ', ')."
}
Write-Host "     For Minecraft $Minecraft (another one: add -Minecraft <version>; this mod has $($supported -join ', '))."

Write-Host "2/4  Building the mod (the first time takes a few minutes)..." -ForegroundColor Cyan
Push-Location mod
& .\gradlew.bat ":${Minecraft}:build" -x test --quiet
if ($LASTEXITCODE -ne 0) { Pop-Location; throw "The build failed: is Java 25 installed? (java -version)" }
Pop-Location
$jar = Get-ChildItem "mod\build\libs\kindred-spirit-*+$Minecraft.jar" | Sort-Object LastWriteTime -Descending | Select-Object -First 1
if (-not $jar) { throw "No mod file was built." }

Write-Host "3/4  Installing it in Minecraft's mods folder..." -ForegroundColor Cyan
New-Item -ItemType Directory -Force $mods | Out-Null
Get-ChildItem $mods -Filter "kindred-spirit-*.jar" -ErrorAction SilentlyContinue | Remove-Item -Force
Copy-Item $jar.FullName $mods

Write-Host "4/4  Checking Fabric API..." -ForegroundColor Cyan
$want = (Select-String -Path "mod\versions\$Minecraft\gradle.properties" -Pattern "^fabric_version=(.+)$").Matches[0].Groups[1].Value.Trim()
$have = Get-ChildItem $mods -Filter "fabric-api-*.jar" -ErrorAction SilentlyContinue
if (-not ($have | Where-Object { $_.Name -like "*+$Minecraft.jar" })) {
    $versions = Invoke-RestMethod "https://api.modrinth.com/v2/project/fabric-api/version?game_versions=%5B%22$Minecraft%22%5D&loaders=%5B%22fabric%22%5D"
    $v = ($versions | Where-Object { $_.version_number -eq $want } | Select-Object -First 1)
    if (-not $v) { $v = $versions | Select-Object -First 1 }
    $file = $v.files | Where-Object { $_.primary } | Select-Object -First 1
    if (-not $file) { $file = $v.files | Select-Object -First 1 }
    $have | Remove-Item -Force -ErrorAction SilentlyContinue  # (a Fabric API for another Minecraft version)
    Invoke-WebRequest $file.url -OutFile (Join-Path $mods $file.filename)
    Write-Host "     Downloaded $($file.filename) from Modrinth."
}

Write-Host ""
Write-Host "Done: $($jar.Name) is installed." -ForegroundColor Green
Write-Host "Start the 'fabric-loader-$Minecraft' installation in the Minecraft Launcher and join the LAN world."
