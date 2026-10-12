#!/usr/bin/env python3
"""Render docs/catalog/index.html at given widths with Windows Edge headless (r30).

Serves docs/catalog/ over HTTP (the page fetches catalog.json, which file:// blocks)
and has msedge.exe screenshot it; WSL forwards localhost to Windows, so Edge reaches it.
Headless Edge will not make a window narrower than ~492px, so `--window-size=390,...`
silently renders at 492 (r30). Each width is therefore an IFRAME that wide inside a
wider window: media queries see the iframe's width. The PNG keeps the window's width;
the page is its left `W` pixels.

    python3 tools/render_catalog.py [--site DIR] OUTDIR [WIDTHxHEIGHT ...]
                                    # default 1280x1400 390x2400; DIR defaults to docs/catalog
"""
import functools
import http.server
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

EDGE = "/mnt/c/Program Files (x86)/Microsoft/Edge/Application/msedge.exe"
SITE = Path(__file__).resolve().parents[1] / "docs" / "catalog"


class Quiet(http.server.SimpleHTTPRequestHandler):
    """docs/catalog/ plus /__frame/W/H: the page in a W x H iframe (same origin;
    Edge blocks a data: page from framing http)."""
    def do_GET(self):
        if not self.path.startswith("/__frame/"):
            return super().do_GET()
        w, h = (int(v) for v in self.path.split("/")[2:4])
        body = (f'<body style="margin:0;background:#000"><iframe src="/index.html" '
                f'style="border:0;display:block;width:{w}px;height:{h}px"></iframe>').encode()
        self.send_response(200)
        self.send_header("Content-Type", "text/html")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *a):
        pass


def winpath(p):
    return subprocess.check_output(["wslpath", "-w", str(p)], text=True).strip()


def shoot(base, w, h, png):
    """One headless Edge, own profile, screenshot of the page in a w x h frame."""
    png.unlink(missing_ok=True)
    for _ in range(4):   # WSL forwards a new port to Windows only after a moment
        with tempfile.TemporaryDirectory(dir=png.parent) as profile:
            subprocess.run([EDGE, "--headless=new", "--disable-gpu", "--hide-scrollbars",
                            f"--user-data-dir={winpath(profile)}",
                            f"--window-size={max(w, 500)},{h}", "--virtual-time-budget=3000",
                            f"--screenshot={winpath(png)}", f"{base}/__frame/{w}/{h}"],
                           timeout=60, capture_output=True)
        if png.exists():
            return True
        time.sleep(1.5)
    return False


def main():
    args = sys.argv[1:]
    site = SITE
    if args[:1] == ["--site"]:        # e.g. HEAD's index.html + catalog.json, to compare
        site, args = Path(args[1]), args[2:]
    out = Path(args[0]).resolve()
    out.mkdir(parents=True, exist_ok=True)
    sizes = args[1:] or ["1280x1400", "390x2400"]
    srv = http.server.ThreadingHTTPServer(
        ("127.0.0.1", 0), functools.partial(Quiet, directory=str(site)))
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    base = f"http://localhost:{srv.server_address[1]}"
    for size in sizes:
        w, h = (int(v) for v in size.split("x"))
        png = out / f"catalog-{w}.png"
        png.unlink(missing_ok=True)
        if not shoot(base, w, h, png):
            sys.exit(f"no screenshot written for {size}")
        print(png)
    srv.shutdown()


if __name__ == "__main__":
    main()
