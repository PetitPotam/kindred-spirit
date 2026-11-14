# Windows: start her (#40), like scripts/start.sh on a Mac: the helpers that aren't running yet (hearing, voice,
# memory's embeddings, the gateway, the dashboard), then her brain. Set up first with scripts\setup-windows.ps1.
#
#   powershell -ExecutionPolicy Bypass -File scripts\start-windows.ps1              her brain in this window (Ctrl+C)
#   powershell -ExecutionPolicy Bypass -File scripts\start-windows.ps1 -Background  everything in the background
#   scripts\stop-windows.ps1 stops what this started.
#
#   :8083 whisper (hearing)  :8885 kokoro (voice)  :8891 embeddings  :11437 gateway  :11440 dashboard  :47811 her brain
param([switch]$Background)
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
$KH = if ($env:KINDRED_HOME) { $env:KINDRED_HOME } else { Join-Path $env:USERPROFILE ".kindred-spirit" }
$Logs = Join-Path $KH "logs"
$Run = if ($env:KINDRED_RUN_DIR) { $env:KINDRED_RUN_DIR } else { Join-Path $KH "run" }
New-Item -ItemType Directory -Force -Path $Logs, $Run | Out-Null
Remove-Item -Force -ErrorAction SilentlyContinue (Join-Path $KH "asleep") # (started again, however: she's awake, #187)
$Py = if ($env:KINDRED_PYTHON) { $env:KINDRED_PYTHON } else { Join-Path $Root "brain\.venv\Scripts\python.exe" }
if (-not (Test-Path $Py)) { Write-Host "Run scripts\setup-windows.ps1 first."; exit 1 }
$GwPort = if ($env:KINDRED_GATEWAY_PORT) { $env:KINDRED_GATEWAY_PORT } else { "11437" }
$DashPort = if ($env:KINDRED_DASHBOARD_PORT) { $env:KINDRED_DASHBOARD_PORT } else { "11440" }
$Brain = Join-Path $Root "brain"
Push-Location $Brain
try {
  $BrainPort = try { & $Py -c "from kindred import config; print(config.load()['server']['port'])" 2>$null } catch { $null }
  if (-not $BrainPort) { $BrainPort = "47811" }
  # this PC's profile: the Whisper model and thread counts (python -m kindred.hardware)
  & $Py -m kindred.hardware --env | ForEach-Object { if ($_ -match '^(\w+)=(.*)$') { Set-Item -Path "env:$($Matches[1])" -Value $Matches[2] } }
} finally { Pop-Location }

function Up($url) { # anything answers there (an error page counts: something is listening)
  try { Invoke-WebRequest -UseBasicParsing -TimeoutSec 2 -Uri $url | Out-Null; return $true }
  catch { return $null -ne $_.Exception.Response }
}
function Listening($port) {
  $c = New-Object Net.Sockets.TcpClient
  try { $c.Connect("127.0.0.1", [int]$port); return $true } catch { return $false } finally { $c.Close() }
}
function Alive($name) { # started by us and still alive (a helper loading its model doesn't answer yet)
  $f = Join-Path $Run "$name.pid"
  if (-not (Test-Path $f)) { return $false }
  return [bool](Get-Process -Id ([int](Get-Content $f)) -ErrorAction SilentlyContinue)
}
# (a helper inherits this window's open handles: whoever runs this script reads its output from a file or the
# console, never a pipe, or they wait as long as she runs; the dashboard and the tests do)
function Start-Helper($name, $exe, [string[]]$arguments, $dir = $Root) {
  $out = Join-Path $Logs "$name.out"
  if ((Test-Path $out) -and (Get-Item $out).Length -gt 5MB) { try { Move-Item -Force $out "$out.1" } catch {} } # (logs never fill the disk; one still open stays)
  $quoted = ($arguments | ForEach-Object { '"' + ($_ -replace '"', '\"') + '"' }) -join " "  # (paths with spaces)
  $p = Start-Process -FilePath $exe -ArgumentList $quoted -WorkingDirectory $dir -WindowStyle Hidden -PassThru `
    -RedirectStandardOutput $out -RedirectStandardError (Join-Path $Logs "$name.err")
  try { $p.PriorityClass = "BelowNormal" } catch {} # (Minecraft keeps the CPU when both want it)
  Set-Content -Path (Join-Path $Run "$name.pid") -Value $p.Id
}
function Uses($part, $default) { # what the gateway uses for a part (gateway.json), or its default
  $f = Join-Path $KH "gateway.json"
  if (Test-Path $f) { $s = Get-Content -Raw $f | ConvertFrom-Json; if ($s.$part -and $s.$part.use) { return $s.$part.use } }
  return $default
}

# hearing: whisper.cpp's whisper-server, the profile's model or any downloaded one
if ((Uses "stt" "local_whisper") -ne "local_whisper") { Write-Host "whisper: not used" }
elseif ((Up "http://127.0.0.1:8083/") -or (Alive "whisper")) { Write-Host "whisper: already running" }
else {
  $ws = Get-ChildItem -Path (Join-Path $KH "whisper\bin") -Recurse -Filter "whisper-server.exe" -ErrorAction SilentlyContinue | Select-Object -First 1
  $m = Join-Path $KH "whisper\$env:KINDRED_WHISPER_MODEL"
  if (-not (Test-Path $m)) { $m = (Get-ChildItem (Join-Path $KH "whisper") -Filter "ggml-*.bin" -ErrorAction SilentlyContinue | Where-Object { $_.Name -notlike "*silero*" } | Select-Object -First 1).FullName }
  if (-not $ws) { Write-Host "whisper: not installed (scripts\setup-windows.ps1); voice input off" }
  elseif (-not $m) { Write-Host "whisper: no model (scripts\setup-windows.ps1); voice input off" }
  else {
    $a = @("-m", $m, "--host", "127.0.0.1", "--port", "8083", "--inference-path", "/audio/transcriptions", "-l", "en",
           "-t", "$env:KINDRED_WHISPER_THREADS", "-ac", "768", "-sns")
    $vad = Join-Path $KH "whisper\ggml-silero-v5.1.2.bin"
    if (Test-Path $vad) { $a += @("--vad", "-vm", $vad) }
    Start-Helper "whisper" $ws.FullName $a $ws.DirectoryName
    Write-Host "whisper: started ($(Split-Path -Leaf $m))"
  }
}
# voice: Kokoro
$kpy = if ($env:KINDRED_KOKORO_PYTHON) { $env:KINDRED_KOKORO_PYTHON } else { Join-Path $KH "kokoro\venv\Scripts\python.exe" }
if ((Uses "tts" "local_kokoro") -ne "local_kokoro") { Write-Host "kokoro voice: not used" }
elseif ((Up "http://127.0.0.1:8885/health") -or (Alive "kokoro")) { Write-Host "kokoro voice: already running" }
elseif ((Test-Path $kpy) -and (Test-Path (Join-Path $KH "kokoro\voices-v1.0.bin"))) {
  Start-Helper "kokoro" $kpy @("-I", (Join-Path $Root "services\kokoro_server.py"), "--models", (Join-Path $KH "kokoro"))
  Write-Host "kokoro voice: starting"
} else { Write-Host "kokoro voice: not set up (scripts\setup-windows.ps1); subtitles only" }
# memory: local embeddings
$epy = if ($env:KINDRED_EMBED_PYTHON) { $env:KINDRED_EMBED_PYTHON } else { Join-Path $KH "embed\venv\Scripts\python.exe" }
if ((Uses "embeddings" "local") -ne "local") { Write-Host "embeddings: not local" }
elseif ((Up "http://127.0.0.1:8891/") -or (Alive "embed")) { Write-Host "embeddings: already running" }
elseif (Test-Path $epy) {
  $env:KINDRED_EMBED_THREADS = "1"
  Start-Helper "embed" $epy @("-I", (Join-Path $Root "services\embed_server.py"), "--cache", (Join-Path $KH "embed\models"))
  Write-Host "embeddings: starting"
} else { Write-Host "embeddings: not set up; memory uses keyword search" }
# the gateway and the dashboard
if ((Up "http://127.0.0.1:$GwPort/health") -or (Alive "gateway")) { Write-Host "gateway: already running" }
else { Start-Helper "gateway" $Py @("-I", (Join-Path $Root "services\kindred_gateway.py"), "serve"); Write-Host "gateway: started" }
for ($i = 0; $i -lt 40 -and -not (Up "http://127.0.0.1:$GwPort/health"); $i++) { Start-Sleep -Milliseconds 250 }
if ((Up "http://127.0.0.1:$DashPort/api/settings") -or (Alive "dashboard")) { Write-Host "dashboard: already running" }
else { Start-Helper "dashboard" $Py @("-I", (Join-Path $Root "services\dashboard.py")); Write-Host "dashboard: http://127.0.0.1:$DashPort" }
if (-not (Select-String -Quiet -Pattern '^GEMINI_API_KEY=.+' -Path (Join-Path $KH "secrets.env") -ErrorAction SilentlyContinue) -and -not $env:GEMINI_API_KEY) {
  Write-Host "note: no GEMINI_API_KEY in $KH\secrets.env (fine if you chose another AI on her dashboard)"
}
# her brain
if ($Background) {
  if ((Listening $BrainPort) -or (Alive "brain")) { Write-Host "brain: already running" }
  else { Start-Helper "brain" $Py @("-m", "kindred") $Brain; Write-Host "brain: started" }
} else {
  Write-Host "brain: running here (Ctrl+C to stop)"
  Push-Location $Brain
  try { & $Py -m kindred } finally { Pop-Location }
}
