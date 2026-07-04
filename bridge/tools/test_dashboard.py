#!/usr/bin/env python3
"""Unit test: Status accounting + the dashboard HTTP endpoints. Stdlib only."""
import json
import sys
import tempfile
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from twitch_bridge.dashboard import Dashboard  # noqa: E402
from twitch_bridge.runtime import Runtime  # noqa: E402
from twitch_bridge.status import Status, describe  # noqa: E402
from twitch_bridge.wallet import Wallet  # noqa: E402

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
    check("/api/admin" in html and "Moderation" in html, "page has the moderation panel")
    check('id="restart"' in html and "/api/restart" in html, "page has the restart button")
    check('id="cdtoggle"' in html, "page has the disable-cooldowns checkbox")
    check('id="capstoggle"' in html, "page has the disable-purchase-limits checkbox")
finally:
    d.stop()


# --- Moderation endpoints (/api/admin, /api/viewers) ---
# A synchronous on_admin backed by a real Wallet (in the app it hops onto the loop;
# here we run it inline — the endpoint wiring is what we're testing).
w = Wallet(tempfile.mktemp(suffix=".json"))
rt = Runtime()


def on_admin(body):
    action = body.get("action")
    target = (body.get("user") or "").lstrip("@").lower()
    if action == "cooldowns":
        rt.cooldowns_enabled = bool(body.get("value"))
        return {"ok": True, "cooldowns_enabled": rt.cooldowns_enabled}
    if action == "caps":
        rt.caps_enabled = bool(body.get("value"))
        return {"ok": True, "caps_enabled": rt.caps_enabled}
    if action == "list":
        return {"ok": True, "viewers": w.viewer_list()}
    if action == "give":
        return {"ok": True, "user": target, "coins": w.give_coins(target, int(body.get("amount", 0)))}
    if action == "giveall":
        for v in list(w.viewers.values()):
            w.give_coins(v.username, int(body.get("amount", 0)))
        return {"ok": True, "count": len(w.viewers)}
    if action in ("ban", "unban"):
        return {"ok": True, "user": target, "banned": w.set_banned(target, action == "ban").banned}
    return {"ok": False, "error": "unknown"}


def post(url, payload):
    req = urllib.request.Request(url, data=json.dumps(payload).encode(),
                                 headers={"Content-Type": "application/json"}, method="POST")
    return json.loads(urllib.request.urlopen(req, timeout=3).read())


restarted = []
s2 = Status(source="stdin")
d2 = Dashboard(s2, port=17598, on_admin=on_admin, on_restart=lambda: restarted.append(True)).start()
try:
    r = post(d2.url + "api/admin", {"action": "give", "user": "@Bob", "amount": 250})
    check(r["ok"] and r["user"] == "bob" and r["coins"] == w.s.starting_balance + 250,
          "POST /api/admin give credits coins (name lower-cased, @ stripped)")
    r = post(d2.url + "api/admin", {"action": "ban", "user": "bob"})
    check(r["ok"] and r["banned"] is True, "POST /api/admin ban blocks the viewer")
    vlist = json.loads(urllib.request.urlopen(d2.url + "api/viewers", timeout=3).read())
    check(vlist["ok"] and any(v["username"] == "bob" and v["banned"] for v in vlist["viewers"]),
          "GET /api/viewers lists the blocked viewer")
    r = post(d2.url + "api/admin", {"action": "unban", "user": "bob"})
    check(r["ok"] and r["banned"] is False, "POST /api/admin unban clears the block")
    r = post(d2.url + "api/restart", {})
    check(r["ok"] and restarted == [True], "POST /api/restart fires the on_restart callback")
    r = post(d2.url + "api/admin", {"action": "cooldowns", "value": False})
    check(r["ok"] and r["cooldowns_enabled"] is False and rt.cooldowns_enabled is False,
          "POST /api/admin cooldowns=off disables cooldowns")
    r = post(d2.url + "api/admin", {"action": "cooldowns", "value": True})
    check(r["cooldowns_enabled"] is True and rt.cooldowns_enabled is True,
          "POST /api/admin cooldowns=on re-enables them")
    r = post(d2.url + "api/admin", {"action": "caps", "value": False})
    check(r["ok"] and r["caps_enabled"] is False and rt.caps_enabled is False,
          "POST /api/admin caps=off disables purchase limits")
    r = post(d2.url + "api/admin", {"action": "caps", "value": True})
    check(r["caps_enabled"] is True and rt.caps_enabled is True,
          "POST /api/admin caps=on re-enables them")
finally:
    d2.stop()

print("\n" + ("ALL PASS" if ok else "SOME FAILED"))
sys.exit(0 if ok else 1)
