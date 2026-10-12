#!/usr/bin/env python3
"""Capture companion screenshots for the README via Playwright (reproducible).

Writes docs/img/{oauth-setup,dashboard,catalog}.png, each under push-check's 1 MB
(Pillow quantizes one that is over). Uses a neutral socket path
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
# push-check refuses a file over 1 MB; the 2x full-page catalog shot is ~1.3 MB.
MAX_BYTES = 1_000_000


def wait_up(url, tries=80):
    for _ in range(tries):
        try:
            urllib.request.urlopen(url, timeout=0.5)
            return True
        except (OSError, http.client.HTTPException):   # not up yet / mid-start
            time.sleep(0.2)
    return False


def fit_push_limit(path):
    """Quantize `path` to 256 colours if it is over MAX_BYTES: it keeps its 2x
    sharpness and looks the same (1.3 MB -> ~500 KB for catalog.png)."""
    if path.stat().st_size <= MAX_BYTES:
        return
    from PIL import Image
    with Image.open(path) as im:
        small = im.convert("RGB").quantize(256, method=Image.Quantize.MEDIANCUT)
    small.save(path, optimize=True)
    print(f"quantized {path.name}: {path.stat().st_size // 1024} KB")


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
    for shot in ("oauth-setup.png", "dashboard.png", "catalog.png"):
        fit_push_limit(IMG / shot)
    print("wrote:", ", ".join(sorted(p.name for p in IMG.glob("*.png"))))
finally:
    proc.terminate()
    try:
        proc.wait(timeout=3)
    except subprocess.TimeoutExpired:
        proc.kill()
    Path("/tmp/shot_wallet.json").unlink(missing_ok=True)
    Path(SHOT_SETUP).unlink(missing_ok=True)
