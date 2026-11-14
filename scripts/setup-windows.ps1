# Windows: set up her brain on this PC, to host your own Pip (#40, docs/HOSTING-WINDOWS.md). The same parts as
# scripts/setup.sh on a Mac: her brain (Python), her voice (Kokoro), her memory's embeddings and her hearing
# (whisper.cpp's whisper-server, CPU). Then scripts\start-windows.ps1 starts her.
#
#   powershell -ExecutionPolicy Bypass -File scripts\setup-windows.ps1              everything (about 1 GB)
#   powershell -ExecutionPolicy Bypass -File scripts\setup-windows.ps1 -NoVoice     her brain only (typing, subtitles)
#   ... -Only whisper | kokoro | embed      one part                 ... -NoModels   no model downloads (the tests)
param([switch]$NoVoice, [switch]$NoModels, [string]$Only = "")
$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue" # (the progress bar makes downloads much slower in Windows PowerShell)
$Root = Split-Path -Parent $PSScriptRoot
$KH = if ($env:KINDRED_HOME) { $env:KINDRED_HOME } else { Join-Path $env:USERPROFILE ".kindred-spirit" }
New-Item -ItemType Directory -Force -Path (Join-Path $KH "logs") | Out-Null

# whisper.cpp's Windows build (CPU, x64), pinned: the file and its SHA-256 from the release (v1.9.3, build b4938)
$WhisperZip = "https://github.com/ggml-org/whisper.cpp/releases/download/b4938/whisper-bin-x64.zip"
$WhisperSha = "c2a4b60edb11f7e11a9191ffb50929535527d4d91c9903dbe3e554583bbbc63d"

function Say($text) { Write-Host ""; Write-Host $text -ForegroundColor Cyan }
function Fetch($url, $dest) {
  if ((Test-Path $dest) -and (Get-Item $dest).Length -gt 0) { Write-Host "  have $(Split-Path -Leaf $dest)"; return }
  Write-Host "  downloading $(Split-Path -Leaf $dest)..."
  Invoke-WebRequest -UseBasicParsing -Uri $url -OutFile "$dest.part"
  Move-Item -Force "$dest.part" $dest
}
function Find-Python {
  foreach ($v in "3.13", "3.12", "3.11") {
    try { $p = & py "-$v" -c "import sys; print(sys.executable)" 2>$null; if ($LASTEXITCODE -eq 0 -and $p) { return "$p".Trim() } } catch {}
  }
  try {
    $p = & python -c "import sys; assert sys.version_info >= (3, 11); print(sys.executable)" 2>$null
    if ($LASTEXITCODE -eq 0 -and $p) { return "$p".Trim() }
  } catch {}
  return $null
}
function Venv($dir) { # a virtual environment; returns its python.exe
  $py = Join-Path $dir "Scripts\python.exe"
  if (-not (Test-Path $py)) { & $Python -m venv $dir; if ($LASTEXITCODE -ne 0) { throw "couldn't make $dir" } }
  & $py -m pip install -q --upgrade pip | Out-Null
  return $py
}
function Pip($py, [string[]]$what) { & $py -m pip install -q @what; if ($LASTEXITCODE -ne 0) { throw "pip install $what failed" } }

$Python = Find-Python
if (-not $Python) {
  Write-Host "Python 3.11 or newer is needed: winget install Python.Python.3.12 (then open a new PowerShell)"; exit 1
}

function Install-Brain {
  Say "Brain ($Python)"
  $py = Venv (Join-Path $Root "brain\.venv")
  Pip $py @("-r", (Join-Path $Root "brain\requirements.txt"))
  Push-Location (Join-Path $Root "brain"); try { & $py -m kindred.hardware } finally { Pop-Location }
  $secrets = Join-Path $KH "secrets.env"
  if (-not (Test-Path $secrets)) {
    Set-Content -Path $secrets -Value "GEMINI_API_KEY=" -Encoding ascii
    Write-Host "  made $secrets : put your Gemini key there (or choose another AI on her dashboard)"
  }
}
function Install-Kokoro {
  Say "Her voice: Kokoro"
  $dir = Join-Path $KH "kokoro"; New-Item -ItemType Directory -Force -Path $dir | Out-Null
  Pip (Venv (Join-Path $dir "venv")) @("kokoro-onnx", "soundfile")
  if (-not $NoModels) {
    $r = "https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0"
    Fetch "$r/kokoro-v1.0.int8.onnx" (Join-Path $dir "kokoro-v1.0.int8.onnx")
    Fetch "$r/voices-v1.0.bin" (Join-Path $dir "voices-v1.0.bin")
  }
}
function Install-Embed {
  Say "Her memory: local embeddings"
  $dir = Join-Path $KH "embed"; New-Item -ItemType Directory -Force -Path (Join-Path $dir "models") | Out-Null
  $py = Venv (Join-Path $dir "venv")
  Pip $py @("fastembed")
  if (-not $NoModels) {
    & $py -c "import sys; from fastembed import TextEmbedding; TextEmbedding('BAAI/bge-small-en-v1.5', cache_dir=sys.argv[1])" (Join-Path $dir "models")
  }
}
function Install-Whisper {
  Say "Her hearing: whisper.cpp"
  $dir = Join-Path $KH "whisper"; $bin = Join-Path $dir "bin"
  New-Item -ItemType Directory -Force -Path $dir | Out-Null
  if (-not (Get-ChildItem -Path $bin -Recurse -Filter "whisper-server.exe" -ErrorAction SilentlyContinue)) {
    $zip = Join-Path $dir "whisper-bin-x64.zip"
    Fetch $WhisperZip $zip
    $sha = (Get-FileHash -Algorithm SHA256 $zip).Hash.ToLower()
    if ($sha -ne $WhisperSha) { Remove-Item -Force $zip; throw "whisper-bin-x64.zip isn't the expected file (SHA-256 $sha)" }
    Expand-Archive -Force -Path $zip -DestinationPath $bin
    Remove-Item -Force $zip
  }
  $server = Get-ChildItem -Path $bin -Recurse -Filter "whisper-server.exe" | Select-Object -First 1
  if (-not $server) { throw "no whisper-server.exe in whisper.cpp's Windows build" }
  Write-Host "  $($server.FullName)"
  if (-not $NoModels) {
    $py = Join-Path $Root "brain\.venv\Scripts\python.exe"
    Push-Location (Join-Path $Root "brain")
    try { $model = (& $py -m kindred.hardware --env | Where-Object { $_ -like "KINDRED_WHISPER_MODEL=*" }) -replace "^KINDRED_WHISPER_MODEL=", "" }
    finally { Pop-Location }
    Fetch "https://huggingface.co/ggerganov/whisper.cpp/resolve/main/$model" (Join-Path $dir $model)
    Fetch "https://huggingface.co/ggml-org/whisper-vad/resolve/main/ggml-silero-v5.1.2.bin" (Join-Path $dir "ggml-silero-v5.1.2.bin")
  }
}

switch ($Only) {
  "kokoro" { Install-Kokoro }
  "embed" { Install-Embed }
  "whisper" { Install-Whisper }
  "brain" { Install-Brain }
  "" {
    Install-Brain
    if (-not $NoVoice) { Install-Kokoro; Install-Embed; Install-Whisper }
    Say "Done. Next: put your key in $KH\secrets.env, then: powershell -ExecutionPolicy Bypass -File scripts\start-windows.ps1"
  }
  default { Write-Host "install what? brain, kokoro, embed or whisper"; exit 2 }
}
