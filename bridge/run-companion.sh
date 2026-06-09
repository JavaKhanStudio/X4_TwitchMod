#!/usr/bin/env bash
# Manual start for the X4 ⇄ Twitch companion, with its status dashboard opened
# in your browser. This is the "start it yourself" option; the other is a Steam
# launch-option wrapper that co-launches it with X4 (see docs/09).
#
#   ./run-companion.sh                  # default source (stdin, for testing)
#   ./run-companion.sh --source twitch  # real Twitch (needs TWITCH_* env / config)
#
# The dashboard URL is printed on startup; with --open it also opens the browser.
cd "$(dirname "$0")" || exit 1

PY="$(command -v python3 || command -v python)"
if [ -z "$PY" ]; then
  echo "error: python3 not found on PATH" >&2
  exit 1
fi

echo "Starting companion… dashboard will be at http://127.0.0.1:17564/"
# Default to the twitch source so the dashboard shows the Connect-to-Twitch panel.
# It starts IDLE (no creds needed up front); you connect from the dashboard button.
# A trailing --source stdin in your args overrides this for testing.
exec "$PY" -m twitch_bridge --open --source twitch "$@"
