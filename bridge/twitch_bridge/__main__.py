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
    p.add_argument("-v", "--verbose", action="store_true", help="debug logging")
    a = p.parse_args()
    cfg.socket_path = a.socket
    cfg.source = a.source
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
