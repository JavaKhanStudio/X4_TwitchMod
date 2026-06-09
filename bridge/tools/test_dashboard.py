#!/usr/bin/env python3
"""Unit test: Status accounting + the dashboard HTTP endpoints. Stdlib only."""
import json
import sys
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from twitch_bridge.dashboard import Dashboard  # noqa: E402
from twitch_bridge.status import Status, describe  # noqa: E402

ok = True


def check(cond, msg):
    global ok
    print(("PASS: " if cond else "FAIL: ") + msg)
    ok = ok and cond


# --- Status accounting ---
s = Status(source="stdin", channel="mychan", socket_path="/tmp/twitch.xml")
s.set_x4(True)
s.record_event({"t": "chat", "user": "viewer42", "msg": "!ping"})
s.record_command({"t": "cmd", "id": "ping", "by": "viewer42"})
s.record_action({"t": "say", "msg": "pong"})
snap = s.snapshot()
check(snap["events_in"] == 1, "events_in counted")
check(snap["commands_fired"] == 1, "commands_fired counted")
check(snap["actions_out"] == 1, "actions_out counted")
check(snap["x4_connected"] is True, "x4_connected reflected")
check(snap["channel"] == "mychan", "channel carried")
check(len(snap["recent"]) >= 4, "recent feed populated")
check(snap["recent"][0]["dir"] == "out", "newest-first ordering (say is newest)")

# --- describe() labels ---
check(describe({"t": "raid", "user": "big", "viewers": 50}) == "big raided with 50 viewers",
      "describe(raid)")
check("redeemed" in describe({"t": "redeem", "user": "v", "reward": "Pirate Attack"}),
      "describe(redeem)")

# --- Dashboard HTTP ---
d = Dashboard(s, port=17599).start()
try:
    api = urllib.request.urlopen(d.url + "api/status", timeout=3)
    body = json.loads(api.read())
    check(api.status == 200, "GET /api/status -> 200")
    check(body["commands_fired"] == 1, "/api/status JSON reflects live state")
    page = urllib.request.urlopen(d.url, timeout=3)
    html = page.read().decode()
    check(page.status == 200 and "X4 ⇄ Twitch Companion" in html, "GET / serves the dashboard page")
    check("/api/status" in html, "page polls the status endpoint")
finally:
    d.stop()

print("\n" + ("ALL PASS" if ok else "SOME FAILED"))
sys.exit(0 if ok else 1)
