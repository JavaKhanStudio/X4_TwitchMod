# One-step install for the X4 Twitch integration on Windows (mirror of install.sh):
#   1. installs the mod into X4's extensions folder,
#   2. bundles the companion (the Python bridge) INSIDE the mod so it travels
#      with the mod and is found wherever X4's mods are,
#   3. adds a Start Menu shortcut that runs the bundled companion.
#
# Re-run after code changes to redeploy. Override X4 detection with -X4Dir.
#
#   .\install.ps1
#   .\install.ps1 -X4Dir 'E:\steam\steamapps\common\X4 Foundations'
[CmdletBinding()]
param(
  [string]$X4Dir = $env:X4_DIR
)
$ErrorActionPreference = "Stop"
$Repo = $PSScriptRoot

# --- 1. locate X4 -----------------------------------------------------------
function Find-X4 {
  $candidates = @(
    'E:\steam\steamapps\common\X4 Foundations',
    'C:\Program Files (x86)\Steam\steamapps\common\X4 Foundations',
    "$env:ProgramFiles\Steam\steamapps\common\X4 Foundations",
    'D:\SteamLibrary\steamapps\common\X4 Foundations',
    'E:\SteamLibrary\steamapps\common\X4 Foundations'
  )
  foreach ($d in $candidates) { if (Test-Path (Join-Path $d 'extensions')) { return $d } }
  return $null
}
if (-not $X4Dir) { $X4Dir = Find-X4 }
if (-not $X4Dir -or -not (Test-Path (Join-Path $X4Dir 'extensions'))) {
  Write-Error "Could not find X4. Re-run with:  .\install.ps1 -X4Dir 'C:\path\to\X4 Foundations'"
  exit 1
}
$Ext = Join-Path $X4Dir 'extensions\twitch_integration'
Write-Host "X4 found at: $X4Dir"

# --- 2. install the mod(s) --------------------------------------------------
New-Item -ItemType Directory -Force -Path $Ext | Out-Null
Copy-Item -Recurse -Force (Join-Path $Repo 'extensions\twitch_integration\*') $Ext
Write-Host "[ok] mod installed:       $Ext"

# The world-affecting arena mod is a SEPARATE extension (save="true"; needs a new
# game). Installed too, but it does nothing until you enable it + start a new game.
$Arena = Join-Path $X4Dir 'extensions\twitch_arena'
if (Test-Path (Join-Path $Repo 'extensions\twitch_arena')) {
  New-Item -ItemType Directory -Force -Path $Arena | Out-Null
  Copy-Item -Recurse -Force (Join-Path $Repo 'extensions\twitch_arena\*') $Arena
  Write-Host "[ok] arena mod installed: $Arena"
}

# --- 3. bundle the companion inside the mod ---------------------------------
$Comp = Join-Path $Ext 'companion'
if (Test-Path $Comp) { Remove-Item -Recurse -Force $Comp }
New-Item -ItemType Directory -Force -Path $Comp | Out-Null
Copy-Item -Recurse -Force (Join-Path $Repo 'bridge\twitch_bridge') $Comp
Copy-Item -Force (Join-Path $Repo 'bridge\run-companion.ps1') $Comp
Copy-Item -Force (Join-Path $Repo 'bridge\Start Companion.cmd') $Comp
if (Test-Path (Join-Path $Repo 'bridge\requirements.txt')) {
  Copy-Item -Force (Join-Path $Repo 'bridge\requirements.txt') $Comp
}
Get-ChildItem -Recurse -Directory -Filter '__pycache__' $Comp | Remove-Item -Recurse -Force -ErrorAction SilentlyContinue
Write-Host "[ok] companion bundled in: $Comp"

# --- 4. Start Menu shortcut -> the bundled companion ------------------------
# Points at the .cmd (a .ps1 is not double-clickable). Per-user Programs folder,
# so no admin rights are needed. Never fatal: the mod is installed either way.
$Cmd = Join-Path $Comp 'Start Companion.cmd'
$Lnk = Join-Path $env:APPDATA 'Microsoft\Windows\Start Menu\Programs\X4 Twitch Companion.lnk'
try {
  New-Item -ItemType Directory -Force -Path (Split-Path $Lnk) | Out-Null
  $sc = (New-Object -ComObject WScript.Shell).CreateShortcut($Lnk)
  $sc.TargetPath = $Cmd
  $sc.WorkingDirectory = $Comp
  $sc.Description = 'Start the X4 Twitch companion + dashboard'
  $sc.Save()
  Write-Host "[ok] launcher installed:  'X4 Twitch Companion' in your Start Menu"
} catch {
  Write-Warning "could not create the Start Menu shortcut ($_) - double-click '$Cmd' instead"
}

Write-Host ""
Write-Host "Done. One-time Python deps:"
Write-Host "    py -m pip install -r `"$Comp\requirements.txt`"   # (twitchAPI)"
Write-Host ""
Write-Host "Then start the companion + dashboard from the Start Menu ('X4 Twitch"
Write-Host "Companion'), or by double-clicking:"
Write-Host "    $Cmd"
Write-Host ""
Write-Host "Then in X4: Settings -> Extensions -> enable 'Twitch Integration'"
Write-Host "(and 'SirNukes Mod Support APIs'), turn OFF Protected UI Mode, and load a save."
