# Kindred Spirit for a friend's Windows PC: gets the latest version, builds the mod, installs it.
# Run it after every update the host pushes (or double-click scripts\update-pip-windows.cmd).
#
#   powershell -ExecutionPolicy Bypass -File scripts\update-pip-windows.ps1
#
# Needs: Git (signed in to GitHub), Java 21 (Temurin), Minecraft 1.21.1 with Fabric installed once.
# Close Minecraft first: a running game keeps the old mod.

$ErrorActionPreference = "Stop"
$repo = Split-Path -Parent $PSScriptRoot
Set-Location $repo

Write-Host "1/4  Getting the latest version..." -ForegroundColor Cyan
git pull --ff-only
if ($LASTEXITCODE -ne 0) { throw "git pull failed (are you signed in to GitHub? did you change files in the repository?)" }

Write-Host "2/4  Building the mod (the first time takes a few minutes)..." -ForegroundColor Cyan
Push-Location mod
& .\gradlew.bat build -x test --quiet
if ($LASTEXITCODE -ne 0) { Pop-Location; throw "The build failed: is Java 21 installed? (java -version)" }
Pop-Location
$jar = Get-ChildItem "mod\build\libs\kindred-spirit-*.jar" | Where-Object { $_.Name -notlike "*-sources*" } |
    Sort-Object LastWriteTime -Descending | Select-Object -First 1
if (-not $jar) { throw "No mod file was built." }

Write-Host "3/4  Installing it in Minecraft's mods folder..." -ForegroundColor Cyan
$mods = Join-Path $env:APPDATA ".minecraft\mods"
New-Item -ItemType Directory -Force $mods | Out-Null
Get-ChildItem $mods -Filter "kindred-spirit-*.jar" -ErrorAction SilentlyContinue | Remove-Item -Force
Copy-Item $jar.FullName $mods

Write-Host "4/4  Checking Fabric API..." -ForegroundColor Cyan
$want = (Select-String -Path "mod\gradle.properties" -Pattern "^fabric_version=(.+)$").Matches[0].Groups[1].Value.Trim()
$have = Get-ChildItem $mods -Filter "fabric-api-*.jar" -ErrorAction SilentlyContinue
if (-not ($have | Where-Object { $_.Name -like "*+1.21.1.jar" })) {
    $versions = Invoke-RestMethod 'https://api.modrinth.com/v2/project/fabric-api/version?game_versions=%5B%221.21.1%22%5D&loaders=%5B%22fabric%22%5D'
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
Write-Host "Start the 'fabric-loader-1.21.1' installation in the Minecraft Launcher and join the LAN world."
