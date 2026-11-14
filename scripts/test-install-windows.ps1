# Windows: does hosting her work on a clean PC? (#40; .github/workflows/platforms.yml runs it on GitHub's Windows
# machines.) Like scripts/test-install.sh brain on a Mac: install her brain with scripts\setup-windows.ps1 into a
# throwaway home, check whisper.cpp's Windows build (downloaded, SHA-256 checked, it runs), start everything with
# scripts\start-windows.ps1 on the test's ports with a stand-in AI (brain\tools\fake_ai.py), and check that the
# gateway, her brain and her dashboard answer, that a pretend game (brain\tools\fake_game.py) chats with her, that
# her dashboard puts her to sleep and wakes her up, and that scripts\stop-windows.ps1 stops it all. No keys, no models.
# (Continue: in Windows PowerShell 5.1 a native command's stderr, redirected, would stop the script at once; every
# check here says itself what failed)
$ErrorActionPreference = "Continue"
$ProgressPreference = "SilentlyContinue"
$Root = Split-Path -Parent $PSScriptRoot
$GW = 11537; $DASH = 11540; $BRAIN = 47911; $AI = 11599
$script:Failed = $false
function Ok($t) { Write-Host "  ok   $t" -ForegroundColor Green }
function Bad($t) { Write-Host "  FAIL $t" -ForegroundColor Red; $script:Failed = $true; if ($env:GITHUB_ACTIONS) { Write-Host "::error::$t" } }
function Up($url) {
  try { Invoke-WebRequest -UseBasicParsing -TimeoutSec 3 -Uri $url | Out-Null; return $true }
  catch { return $null -ne $_.Exception.Response }
}
function Get-Text($url, $method = "GET") {
  try { return (Invoke-WebRequest -UseBasicParsing -TimeoutSec 90 -Method $method -Uri $url).Content } catch { return "" }
}
function Listening($port) {
  $c = New-Object Net.Sockets.TcpClient
  try { $c.Connect("127.0.0.1", [int]$port); return $true } catch { return $false } finally { $c.Close() }
}

$work = Join-Path ([IO.Path]::GetTempPath()) ("kindred-test-" + [guid]::NewGuid().ToString("N").Substring(0, 8))
$home_ = Join-Path $work "home"; $KH = Join-Path $home_ ".kindred-spirit"
New-Item -ItemType Directory -Force -Path $KH | Out-Null
$env:USERPROFILE = $home_; $env:HOME = $home_; $env:KINDRED_HOME = $KH
$env:KINDRED_GATEWAY_PORT = "$GW"; $env:KINDRED_DASHBOARD_PORT = "$DASH"
Set-Content -Encoding ascii -Path (Join-Path $KH "brain.toml") -Value "[server]`nport = $BRAIN`n`n[gateway]`nurl = `"http://127.0.0.1:$GW/v1`"`n"
Set-Content -Encoding ascii -Path (Join-Path $KH "gateway.json") -Value ('{"upstream": "fake", "upstreams": {"fake": {"base": "http://127.0.0.1:' + $AI + '/v1", "key": "", "model": "fake"}}, "stt": {"use": "none"}, "tts": {"use": "none"}, "embeddings": {"use": "none"}}')

Write-Host "== Her brain on Windows ($([Environment]::OSVersion.VersionString))"
powershell -NoProfile -ExecutionPolicy Bypass -File (Join-Path $Root "scripts\setup-windows.ps1") -NoVoice *> (Join-Path $work "setup.log")
if ($LASTEXITCODE -eq 0) { Ok "scripts\setup-windows.ps1 -NoVoice" } else { Bad "setup-windows.ps1 failed:"; Get-Content (Join-Path $work "setup.log") -Tail 30 }
if (Test-Path (Join-Path $KH "secrets.env")) { Ok "secrets.env made" } else { Bad "no secrets.env" }
powershell -NoProfile -ExecutionPolicy Bypass -File (Join-Path $Root "scripts\setup-windows.ps1") -Only whisper -NoModels *> (Join-Path $work "whisper.log")
$ws = Get-ChildItem -Path (Join-Path $KH "whisper\bin") -Recurse -Filter "whisper-server.exe" -ErrorAction SilentlyContinue | Select-Object -First 1
if ($LASTEXITCODE -eq 0 -and $ws) {
  $help = & $ws.FullName --help 2>&1 | Out-String
  if ($help -match "inference-path") { Ok "her hearing: whisper.cpp's Windows build, checked and running ($($ws.Name))" }
  else { Bad "whisper-server.exe doesn't run: $($help.Substring(0, [Math]::Min(300, $help.Length)))" }
} else { Bad "whisper.cpp's Windows build wasn't installed:"; Get-Content (Join-Path $work "whisper.log") -Tail 20 }

$py = Join-Path $Root "brain\.venv\Scripts\python.exe"
$fake = Start-Process -FilePath $py -ArgumentList @("-I", "`"$(Join-Path $Root 'brain\tools\fake_ai.py')`"", "--port", "$AI") -WindowStyle Hidden -PassThru `
  -RedirectStandardOutput (Join-Path $work "fake_ai.out") -RedirectStandardError (Join-Path $work "fake_ai.err")
powershell -NoProfile -ExecutionPolicy Bypass -File (Join-Path $Root "scripts\start-windows.ps1") -Background *> (Join-Path $work "start.log")
if ($LASTEXITCODE -eq 0) { Ok "scripts\start-windows.ps1 -Background" } else { Bad "start-windows.ps1 failed:"; Get-Content (Join-Path $work "start.log") }
for ($i = 0; $i -lt 120; $i++) {
  if ((Up "http://127.0.0.1:$GW/health") -and (Listening $BRAIN) -and (Up "http://127.0.0.1:$DASH/api/her")) { break }
  Start-Sleep -Milliseconds 500
}
if (Up "http://127.0.0.1:$GW/health") { Ok "gateway answers (:$GW)" } else { Bad "gateway doesn't answer" }
if (Listening $BRAIN) { Ok "her brain listens (:$BRAIN)" } else { Bad "her brain isn't listening on :$BRAIN" }
foreach ($check in @(@("the page", "/", "Kindred Dashboard"), @("settings", "/api/settings", '"gateway"'), @("her state", "/api/her", '"awake"'))) {
  if ((Get-Text "http://127.0.0.1:$DASH$($check[1])").Contains($check[2])) { Ok "dashboard: $($check[0]) ($($check[1]))" }
  else { Bad "dashboard: $($check[0]) ($($check[1])) didn't answer as expected" }
}
Push-Location (Join-Path $Root "brain")
try { $said = & $py tools/fake_game.py chat "Hi Pip, are you there?" --quiet --wait 40 2>&1 | Out-String } finally { Pop-Location }
if ($said -match "SAY .*test answer") { Ok "she answered a pretend game: $(($said -split "`n" | Select-String 'SAY' | Select-Object -First 1))" }
else { Bad "no answer to a pretend game's chat:"; Write-Host $said }
Get-Text "http://127.0.0.1:$DASH/api/her/sleep" "POST" | Out-Null
$state = Get-Text "http://127.0.0.1:$DASH/api/her"
if ($state.Contains('"asleep"') -and -not (Listening $BRAIN)) { Ok "put to sleep from her dashboard (the dashboard stays)" } else { Bad "sleep: $state" }
Get-Text "http://127.0.0.1:$DASH/api/her/wake" "POST" | Out-Null
for ($i = 0; $i -lt 60 -and -not (Get-Text "http://127.0.0.1:$DASH/api/her").Contains('"awake"'); $i++) { Start-Sleep -Milliseconds 500 }
if ((Get-Text "http://127.0.0.1:$DASH/api/her").Contains('"awake"')) { Ok "woken up from her dashboard" } else { Bad "she didn't wake up" }
if ($script:Failed) {
  foreach ($f in "gateway", "brain", "dashboard") {
    foreach ($ext in "out", "err", "log") {
      $p = Join-Path $KH "logs\$f.$ext"; if (Test-Path $p) { Write-Host "--- $f.$ext"; Get-Content $p -Tail 25 }
    }
  }
}
powershell -NoProfile -ExecutionPolicy Bypass -File (Join-Path $Root "scripts\stop-windows.ps1") | Out-Null
Start-Sleep -Seconds 1
if (-not (Listening $BRAIN) -and -not (Up "http://127.0.0.1:$DASH/api/her")) { Ok "scripts\stop-windows.ps1 stopped everything" } else { Bad "something still runs after stop-windows.ps1" }
Stop-Process -Id $fake.Id -Force -ErrorAction SilentlyContinue
if ($script:Failed) { Write-Host "  (kept for a look: $work)"; exit 1 }
Remove-Item -Recurse -Force $work -ErrorAction SilentlyContinue
exit 0
