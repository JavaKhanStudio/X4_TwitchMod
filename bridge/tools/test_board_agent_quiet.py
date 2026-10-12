#!/usr/bin/env python3
"""A companion started by a board agent (ATELIER_AGENT set) installs no menu
launcher and opens no browser, whatever its flags say (board r2).

Nothing real is touched: webbrowser.open and the launcher's script lookup are
replaced by recorders. Run: python3 bridge/tools/test_board_agent_quiet.py
"""
import os
import sys
import webbrowser
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from twitch_bridge import app, launcher  # noqa: E402

opened, looked = [], []
webbrowser.open = lambda url, *a, **k: opened.append(url)
launcher.companion_script = lambda: looked.append(1)   # returns None: nothing is written
fails = 0


def check(ok, what):
    global fails
    print(("PASS " if ok else "FAIL ") + what)
    fails += not ok


os.environ["ATELIER_AGENT"] = "test-agent"
launcher.ensure_launcher()
app._open_browser("http://127.0.0.1:1/")
check(not looked, "board agent: the launcher is not even looked for")
check(not opened, "board agent: no browser is opened")

del os.environ["ATELIER_AGENT"]
launcher.ensure_launcher()
app._open_browser("http://127.0.0.1:1/")
check(looked == [1], "a person: the launcher is installed as before")
check(opened == ["http://127.0.0.1:1/"], "a person: --open still opens the browser")
sys.exit(1 if fails else 0)
