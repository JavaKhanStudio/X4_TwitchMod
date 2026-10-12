#!/usr/bin/env python3
"""Drive a REAL browser (Playwright/Chromium) to the companion dashboard, assert
the page renders with live data, and screenshot it. Proves the UI end-to-end,
not just that curl gets a 200.

    python tools/playwright_check.py
"""
import http.client
import os
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

# A Windows console is cp1252: printing the page title (it has "\u21c4") would
# raise UnicodeEncodeError. Write UTF-8 whatever the console is.
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

ROOT = Path(__file__).resolve().parents[1]
PORT = 17605
URL = f"http://127.0.0.1:{PORT}/"
SHOT = "/tmp/dashboard_screenshot.png"


def wait_up(url, tries=60):
    for _ in range(tries):
        try:
            urllib.request.urlopen(url, timeout=0.5)
            return True
        except (OSError, http.client.HTTPException):   # not up yet / mid-start
            time.sleep(0.2)
    return False


# Start the real bridge. stdin=PIPE kept open so the stdin source stays "running".
proc = subprocess.Popen(
    [sys.executable, "-m", "twitch_bridge", "--source", "stdin",
     "--dashboard-port", str(PORT), "--socket","/tmp/pw_nope.xml","--no-launcher"],
    cwd=str(ROOT), stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
    env={**os.environ, "PYTHONPATH": "."},
)
ok = True
try:
    if not wait_up(URL + "api/status"):
        print("FAIL: bridge dashboard never bound", PORT)
        print((proc.stdout.read() or b"").decode()[:2000])
        proc.kill()
        sys.exit(1)

    # feed one event so the activity feed has content to render
    assert proc.stdin
    proc.stdin.write(b"chat viewer42 !ping\n")
    proc.stdin.flush()
    time.sleep(0.5)

    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 900, "height": 820})
        page.goto(URL, wait_until="networkidle")
        page.wait_for_timeout(1500)  # let the 1s status poll tick
        title = page.title()
        pill = page.inner_text("#bigt")
        source = page.inner_text("#source").strip()
        feed = page.inner_text("#feed")
        page.screenshot(path=SHOT, full_page=True)
        # the catalog item-list page
        page.goto(URL + "catalog", wait_until="networkidle")
        page.wait_for_timeout(600)
        rows = page.eval_on_selector_all("#rows tr", "els=>els.length")
        page.screenshot(path="/tmp/catalog_screenshot.png", full_page=True)
        browser.close()

    print("title       :", title)
    print("status pill :", pill)
    print("source card :", source)
    print("feed has ping:", "viewer42" in feed)
    print("catalog rows:", rows)
    ok = ("Companion" in title) and (source == "stdin") and rows >= 1
    print("screenshots :", SHOT, "/tmp/catalog_screenshot.png")
finally:
    proc.terminate()
    try:
        proc.wait(timeout=3)
    except subprocess.TimeoutExpired:
        proc.kill()

print("\nRESULT:", "PASS ✅" if ok else "FAIL")
sys.exit(0 if ok else 1)
