#!/usr/bin/env python3
"""setup_store persistence + the dashboard Connect (POST) plumbing (headless)."""
import json
import sys
import tempfile
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from twitch_bridge import setup_store  # noqa: E402
from twitch_bridge.dashboard import Dashboard  # noqa: E402
from twitch_bridge.status import Status  # noqa: E402

ok = True


def check(c, m):
    global ok
    print(("PASS: " if c else "FAIL: ") + m)
    ok = ok and c


# --- setup_store round-trip (and secret never logged in the repo) ---
p = tempfile.mktemp(suffix=".json")
setup_store.save({"client_id": "abc", "client_secret": "shh", "channel": "Me"}, p)
got = setup_store.load(p)
check(got == {"client_id": "abc", "client_secret": "shh", "channel": "Me"}, "setup_store round-trip")
import os, sys
if sys.platform == "win32":
    # POSIX mode bits don't apply on Windows (os.chmod only toggles read-only);
    # the secret is protected by the per-user profile's NTFS ACL instead.
    check(os.path.exists(p), "setup.json written (Windows: ACL-protected profile dir)")
else:
    check((os.stat(p).st_mode & 0o777) == 0o600, "setup.json is chmod 600 (owner-only)")
check(setup_store.load(tempfile.mktemp()) == {}, "missing setup file -> empty dict")

# --- dashboard POST /api/connect calls the callback with the body ---
captured = {}
st = Status(source="twitch")
st.set_twitch({"connected": False, "connecting": False, "login": None, "channel": "", "client_id": "", "error": None})
d = Dashboard(st, port=17611,
              on_connect=lambda body: captured.update(body),
              on_disconnect=lambda: captured.update({"disconnected": True})).start()
try:
    req = urllib.request.Request(d.url + "api/connect", method="POST",
                                 data=json.dumps({"client_id": "X", "client_secret": "Y",
                                                  "channel": "chan"}).encode(),
                                 headers={"Content-Type": "application/json"})
    r = urllib.request.urlopen(req, timeout=3)
    check(r.status == 200, "POST /api/connect -> 200")
    check(captured.get("client_id") == "X" and captured.get("client_secret") == "Y",
          "connect callback receives the credentials")
    # the page exposes the setup panel + connect button
    html = urllib.request.urlopen(d.url, timeout=3).read().decode()
    check('id="setup"' in html and 'id="connect"' in html, "dashboard page has the setup panel + Connect button")
    check("dev.twitch.tv/console" in html, "setup panel links to the Twitch app console")
    check("localhost:17563" in html, "setup panel states the redirect URL")
    # status exposes twitch state for the panel
    snap = json.loads(urllib.request.urlopen(d.url + "api/status", timeout=3).read())
    check("twitch" in snap, "/api/status carries twitch connection state")
finally:
    d.stop()

print("\n" + ("ALL PASS" if ok else "SOME FAILED"))
sys.exit(0 if ok else 1)
