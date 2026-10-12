#!/usr/bin/env python3
"""Capture companion screenshots for the README via Playwright (reproducible).

Writes docs/img/{oauth-setup,dashboard,catalog}.png. Uses a neutral socket path
and no real credentials, so the images contain no personal data.

    python tools/make_screenshots.py
"""
import http.client
import os
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]          # bridge/
IMG = ROOT.parent / "docs" / "img"
IMG.mkdir(parents=True, exist_ok=True)
PORT = 17620
BASE = f"http://127.0.0.1:{PORT}/"


def wait_up(url, tries=80):
    for _ in range(tries):
        try:
            urllib.request.urlopen(url, timeout=0.5)
            return True
        except (OSError, http.client.HTTPException):   # not up yet / mid-start
            time.sleep(0.2)
    return False


# Point at an empty, isolated setup file so the bridge can NEVER read the real
# ~/.config setup.json — screenshots must show a clean, empty panel (no real
# client-id / channel). (HOME must stay real, or pip --user packages vanish.)
SHOT_SETUP = tempfile.mktemp(suffix="-empty-setup.json")
proc = subprocess.Popen(
    [sys.executable, "-m", "twitch_bridge", "--source", "twitch", "--dashboard-port", str(PORT),
     "--socket", "/tmp/x4-twitch.sock", "--wallet", "/tmp/shot_wallet.json", "--no-launcher"],
    cwd=str(ROOT), stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
    env={**os.environ, "PYTHONPATH": ".", "X4_TWITCH_SETUP": SHOT_SETUP,
         "TWITCH_CLIENT_ID": "", "TWITCH_CLIENT_SECRET": "", "TWITCH_CHANNEL": ""},
)
try:
    if not wait_up(BASE + "api/status"):
        print("bridge did not start"); proc.kill(); sys.exit(1)
    from playwright.sync_api import sync_playwright
    with sync_playwright() as pw:
        b = pw.chromium.launch()
        pg = b.new_page(viewport={"width": 900, "height": 900}, device_scale_factor=2)
        pg.goto(BASE, wait_until="networkidle")
        pg.wait_for_timeout(1200)
        pg.locator("#setup").screenshot(path=str(IMG / "oauth-setup.png"))
        pg.screenshot(path=str(IMG / "dashboard.png"), full_page=True)
        pg.goto(BASE + "catalog", wait_until="networkidle")
        pg.wait_for_timeout(800)
        pg.screenshot(path=str(IMG / "catalog.png"), full_page=True)
        b.close()
    print("wrote:", ", ".join(sorted(p.name for p in IMG.glob("*.png"))))
finally:
    proc.terminate()
    try:
        proc.wait(timeout=3)
    except subprocess.TimeoutExpired:
        proc.kill()
    Path("/tmp/shot_wallet.json").unlink(missing_ok=True)
    Path(SHOT_SETUP).unlink(missing_ok=True)
