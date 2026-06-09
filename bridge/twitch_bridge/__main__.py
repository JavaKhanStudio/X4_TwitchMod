"""Entrypoint: `python -m twitch_bridge [--socket PATH] [--source stdin|twitch]`."""

from __future__ import annotations

import argparse
import asyncio
import logging

from .app import main
from .config import Config


def _parse_args() -> Config:
    cfg = Config()
    p = argparse.ArgumentParser(prog="twitch_bridge", description="X4 <-> Twitch bridge")
    p.add_argument("--socket", default=cfg.socket_path, help="Unix socket X4 hosts (default: %(default)s)")
    p.add_argument("--source", default=cfg.source, choices=["stdin", "twitch"], help="event source")
    p.add_argument("--no-dashboard", action="store_true", help="disable the companion status UI")
    p.add_argument("--dashboard-port", type=int, default=cfg.dashboard_port, help="dashboard port (default: %(default)s)")
    p.add_argument("--open", action="store_true", help="open the dashboard in your browser on start")
    p.add_argument("--no-economy", action="store_true", help="disable the coin wallet + !buy store")
    p.add_argument("--no-launcher", action="store_true", help="do not (re)install the app-menu launcher")
    p.add_argument("--wallet", default=cfg.wallet_path, help="viewer wallet file (default: %(default)s)")
    p.add_argument("-v", "--verbose", action="store_true", help="debug logging")
    a = p.parse_args()
    cfg.socket_path = a.socket
    cfg.source = a.source
    cfg.dashboard = not a.no_dashboard
    cfg.dashboard_port = a.dashboard_port
    cfg.open_browser = a.open
    cfg.economy = not a.no_economy
    cfg.launcher = not a.no_launcher
    cfg.wallet_path = a.wallet
    logging.basicConfig(
        level=logging.DEBUG if a.verbose else logging.INFO,
        format="%(asctime)s %(levelname)-7s %(name)-12s %(message)s",
    )
    return cfg


if __name__ == "__main__":
    try:
        asyncio.run(main(_parse_args()))
    except KeyboardInterrupt:
        pass
