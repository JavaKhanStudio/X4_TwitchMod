#!/usr/bin/env bash
# From WSL: start the companion on Windows the way the Start Menu entry does
# ("Start Companion.cmd" -> run-companion.ps1 -> py -m twitch_bridge), check the
# dashboard answers 200 on 127.0.0.1:17564, optionally screenshot it with headless
# Edge, then stop it. Nothing shows on screen: --no-launcher, and BROWSER points at
# a program that does not exist so the script's built-in --open fails quietly.
#
#   bash bridge/tools/win_start_check.sh [C:\path\to\shot.png]
#
# Killing cmd.exe from WSL does NOT stop the python.exe under it, so the stop is
# done by command line from PowerShell. Exit 0 = dashboard answered 200.
set -u
cd "$(dirname "$0")/.." || exit 1
shot="${1:-}"
log="$(mktemp)"
winbridge="$(wslpath -w "$PWD")"

export BROWSER=no_browser_win_start_check WSLENV="${WSLENV:+$WSLENV:}BROWSER/u"
cmd.exe /c "$winbridge\\Start Companion.cmd" --no-launcher >"$log" 2>&1 </dev/null &

probe='try{(Invoke-WebRequest -UseBasicParsing http://127.0.0.1:17564/ -TimeoutSec 3).StatusCode}catch{0}'
code=0
for _ in $(seq 15); do
  sleep 1
  code="$(powershell.exe -NoProfile -Command "$probe" | tr -d '\r')"
  [ "$code" = 200 ] && break
done
echo "dashboard: $code"

if [ "$code" = 200 ] && [ -n "$shot" ]; then
  edge="/mnt/c/Program Files (x86)/Microsoft/Edge/Application/msedge.exe"
  timeout 40 "$edge" --headless=new --disable-gpu --window-size=1280,1000 \
    --virtual-time-budget=4000 --screenshot="$shot" http://127.0.0.1:17564/ 2>/dev/null
  echo "screenshot: $shot"
fi

powershell.exe -NoProfile -Command 'Get-CimInstance Win32_Process | ? {$_.CommandLine -like "*-m twitch_bridge*" -and $_.Name -ne "powershell.exe"} | % { Stop-Process -Id $_.ProcessId -Force -EA SilentlyContinue }'
echo "--- companion output"; head -20 "$log"; rm -f "$log"
[ "$code" = 200 ]
