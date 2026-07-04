# Windows deploy for the X4 Twitch mods. Mirrors BOTH extensions into X4's
# extensions folder. install.sh is Linux-only AND only ever deployed
# twitch_integration, so on Windows the arena silently ran stale — this fixes both.
#
#   Usage:  ./deploy.ps1                 # auto-detects X4
#           ./deploy.ps1 -X4 "D:\path\to\X4 Foundations"
#
# Re-run after any change under extensions/.
param([string]$X4)

$ErrorActionPreference = "Stop"
$repo = Split-Path -Parent $MyInvocation.MyCommand.Path

if (-not $X4) {
  $candidates = @(
    "E:\steam\steamapps\common\X4 Foundations",
    "C:\Program Files (x86)\Steam\steamapps\common\X4 Foundations",
    "C:\GOG Games\X4 Foundations",
    "D:\steam\steamapps\common\X4 Foundations"
  )
  $X4 = $candidates | Where-Object { Test-Path (Join-Path $_ "extensions") } | Select-Object -First 1
}
if (-not $X4 -or -not (Test-Path (Join-Path $X4 "extensions"))) {
  throw "Could not find X4. Re-run: ./deploy.ps1 -X4 'X:\path\to\X4 Foundations'"
}
Write-Host "X4 found at: $X4"
$extRoot = Join-Path $X4 "extensions"

function Deploy($name, $extraArgs) {
  $s = Join-Path $repo "extensions\$name"
  $d = Join-Path $extRoot $name
  robocopy $s $d /MIR /NFL /NDL /NJH /NP /R:1 /W:1 @extraArgs | Out-Null
  if ($LASTEXITCODE -ge 8) { throw "robocopy failed for $name (code $LASTEXITCODE)" }
  Write-Host ("  deployed {0} (robocopy code {1})" -f $name, $LASTEXITCODE)
}

# twitch_arena: clean mirror.
Deploy "twitch_arena" @()
# twitch_integration: mirror but PRESERVE the companion/ folder that the Python
# bridge install drops in (it is not in the repo; /XD keeps /MIR from deleting it).
Deploy "twitch_integration" @("/XD", (Join-Path $extRoot "twitch_integration\companion"))

Write-Host "Done. Start a NEW game (arena is save=true) to pick up gamestart changes."
