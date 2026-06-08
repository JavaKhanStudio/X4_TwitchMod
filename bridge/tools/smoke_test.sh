#!/usr/bin/env bash
# End-to-end smoke test of the bridge <-> X4 plumbing, using mock_x4 in place of
# the game. Exercises BOTH directions over the Unix socket. No deps beyond python3.
set -u
cd "$(dirname "$0")/.."   # bridge/

SOCK="$(mktemp -u /tmp/x4_twitch_smoke.XXXXXX.sock)"
MOCK_OUT="$(mktemp)"
BRIDGE_OUT="$(mktemp)"
PY="${PYTHON:-python3}"

cleanup() { kill "${MOCK_PID:-}" "${BRIDGE_PID:-}" 2>/dev/null; rm -f "$SOCK" "$MOCK_OUT" "$BRIDGE_OUT"; }
trap cleanup EXIT

# mock X4: host the socket; after the bridge connects, send a 'say' back into it.
( sleep 1.8; echo "say hello-from-x4"; sleep 2.0 ) | \
  "$PY" tools/mock_x4.py --socket "$SOCK" >"$MOCK_OUT" 2>&1 &
MOCK_PID=$!

sleep 0.6   # let the socket come up

# bridge: connect and emit two Twitch events, then stay alive to receive the 'say'.
( sleep 0.6; echo "chat alice !spawn fighter"; echo "raid bob 250"; sleep 3.0 ) | \
  "$PY" -m twitch_bridge --socket "$SOCK" >"$BRIDGE_OUT" 2>&1 &
BRIDGE_PID=$!

sleep 5

fail=0
check() { # <file> <pattern> <label>
  if grep -qF "$2" "$1"; then echo "PASS: $3"; else echo "FAIL: $3"; fail=1; fi
}

# Note: mock_x4 prints the decoded message via default json.dumps (spaces after
# ':' and ','), whereas the wire format is compact. Assert against the printed form.
echo "--- assertions ---"
check "$BRIDGE_OUT" "connected to X4"            "bridge connected to the socket"
check "$MOCK_OUT"   '"t": "chat"'                "chat event reached X4 (bridge -> X4)"
check "$MOCK_OUT"   '"user": "alice"'            "chat carried the username"
check "$MOCK_OUT"   '"t": "raid"'                "raid event reached X4"
check "$BRIDGE_OUT" "would post to chat"         "X4 'say' reached the bridge (X4 -> bridge)"
check "$BRIDGE_OUT" "hello-from-x4"              "X4 'say' payload delivered"

if [ "$fail" -ne 0 ]; then
  echo; echo "=== mock_x4 output ==="; cat "$MOCK_OUT"
  echo; echo "=== bridge output ==="; cat "$BRIDGE_OUT"
fi
exit "$fail"
