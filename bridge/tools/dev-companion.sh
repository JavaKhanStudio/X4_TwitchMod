#!/usr/bin/env bash
# Dev helper (assistant-managed): (re)start the companion from the REPO (latest
# code) detached on :17564, so the dashboard always runs current code. Keep your
# browser tab open and just refresh after a restart.
cd "$(dirname "$0")/.." || exit 1
pkill -f 'm twitch_bridge' 2>/dev/null; sleep 0.6
PY="$(command -v python3 || command -v python)"
PYTHONPATH=. setsid nohup "$PY" -m twitch_bridge --source twitch --no-launcher \
  >/tmp/companion-dev.log 2>&1 &
disown 2>/dev/null || true
sleep 1.8
echo "companion (repo, latest code) running on http://127.0.0.1:17564/"
echo "--- startup log ---"; grep -iE 'dashboard at|bridge up|authenticated|connect|error' /tmp/companion-dev.log | tail -5
