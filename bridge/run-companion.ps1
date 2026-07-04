# Manual start for the X4 <-> Twitch companion on Windows, with its status
# dashboard opened in your browser. This is the "start it yourself" option.
#
#   .\run-companion.ps1                    # real Twitch source (shows Connect panel)
#   .\run-companion.ps1 --source stdin     # fake source, for testing without Twitch
#
# The dashboard URL is printed on startup; --open also opens the browser.
# Requires Python 3 (the 'py' launcher) and, for the real Twitch source,
#   py -m pip install -r requirements.txt
$ErrorActionPreference = "Stop"
Set-Location -Path $PSScriptRoot

# Prefer the 'py' launcher; fall back to python on PATH.
$py = (Get-Command py -ErrorAction SilentlyContinue)
if ($py) { $exe = "py" } else {
  $exe = (Get-Command python -ErrorAction SilentlyContinue)
  if (-not $exe) { Write-Error "Python not found. Install Python 3 from python.org."; exit 1 }
  $exe = "python"
}

Write-Host "Starting companion... dashboard will be at http://127.0.0.1:17564/"
# Default to the twitch source so the dashboard shows the Connect-to-Twitch panel.
# It starts IDLE (no creds needed up front); you connect from the dashboard button.
# A trailing '--source stdin' in your args overrides this for testing.
& $exe -m twitch_bridge --open --source twitch @args
