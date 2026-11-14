# Windows: start her brain from its Docker image, or update it (#128, docker/README.md). Needs Docker Desktop.
# Her settings and memories stay in your %USERPROFILE%\.kindred-spirit; the ports are published on 127.0.0.1 only.
#
#   powershell -ExecutionPolicy Bypass -File scripts\docker-run.ps1            the newest image (about 1 GB once)
#   powershell -ExecutionPolicy Bypass -File scripts\docker-run.ps1 -Version 0.4.0
#   powershell -ExecutionPolicy Bypass -File scripts\docker-run.ps1 -Stop      stop and remove it (your files stay)
param([string]$Version = "latest", [switch]$Stop, [string]$Image = "")
$ErrorActionPreference = "Stop"
$name = "kindred-spirit"
if (-not $Image) { $Image = "ghcr.io/petitpotam/kindred-spirit-brain:$Version"; $pull = $true } else { $pull = $false }
if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
  Write-Host "Docker Desktop isn't installed: https://docs.docker.com/desktop/setup/install/windows-install/"; exit 1
}
try { docker rm -f $name 2>$null | Out-Null } catch {} # (none yet: fine)
if ($Stop) { Write-Host "Stopped."; exit 0 }
$kh = if ($env:KINDRED_HOME) { $env:KINDRED_HOME } else { Join-Path $env:USERPROFILE ".kindred-spirit" }
New-Item -ItemType Directory -Force -Path $kh | Out-Null
if ($pull) { docker pull -q $Image; if ($LASTEXITCODE -ne 0) { throw "couldn't download $Image" } }
docker run -d --name $name --restart unless-stopped -p 127.0.0.1:47811:47811 -p 127.0.0.1:11440:11440 `
  -v "${kh}:/home/pip/.kindred-spirit" $Image | Out-Null
if ($LASTEXITCODE -ne 0) { throw "docker run failed (is Docker Desktop running?)" }
Write-Host "Her brain is starting (the first time, it downloads her voice and hearing: a few minutes)."
Write-Host "Her dashboard: http://127.0.0.1:11440   Her log: docker logs -f $name"
