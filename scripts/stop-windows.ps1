# Windows: stops what scripts\start-windows.ps1 started (and nothing else), and waits until each has exited (#40).
#   -Keep dashboard   everything but the dashboard (putting her to sleep from its own page, #187)
param([string]$Keep = "")
$KH = if ($env:KINDRED_HOME) { $env:KINDRED_HOME } else { Join-Path $env:USERPROFILE ".kindred-spirit" }
$Run = if ($env:KINDRED_RUN_DIR) { $env:KINDRED_RUN_DIR } else { Join-Path $KH "run" }
$stopped = @()
foreach ($f in Get-ChildItem -Path $Run -Filter "*.pid" -ErrorAction SilentlyContinue) {
  $name = $f.BaseName
  if ($Keep -and $name -eq $Keep) { continue }
  $p = Get-Process -Id ([int](Get-Content $f.FullName)) -ErrorAction SilentlyContinue
  if ($p) { Stop-Process -Id $p.Id -Force -ErrorAction SilentlyContinue; Write-Host "stopped $name"; $stopped += $p }
  Remove-Item -Force $f.FullName
}
foreach ($p in $stopped) { try { $p.WaitForExit(5000) | Out-Null } catch {} } # (their ports free again for a restart)
exit 0
