r"""The link to X4 — a small, transport-agnostic bridge <-> game connection.

Two mirror-image transports, selected at runtime, sharing one interface
(`connected` / `send` / `run` / `stop`, see `BaseX4Link`):

* **unix** (Linux): X4 hosts a Unix-domain socket; the bridge connects as CLIENT.
* **winpipe** (Windows): the bridge HOSTS `\\.\pipe\twitch`; X4 connects as CLIENT.

The rest of the app talks only to `make_x4_link()` and the base interface — it
never needs to know which platform/transport is in play.

Selection order: explicit `transport=` arg > `X4_TWITCH_TRANSPORT` env
("unix"/"winpipe") > platform default (winpipe on Windows, unix elsewhere).
"""

from __future__ import annotations

import os
import sys

from .base import BaseX4Link, OnMessage

__all__ = ["BaseX4Link", "OnMessage", "X4Link", "default_transport", "make_x4_link"]


def default_transport() -> str:
    env = os.environ.get("X4_TWITCH_TRANSPORT", "").strip().lower()
    if env:
        return env
    return "winpipe" if sys.platform == "win32" else "unix"


def make_x4_link(socket_path: str, on_message: OnMessage,
                 reconnect_delay: float = 1.0, *, transport: str | None = None) -> BaseX4Link:
    """Build the X4 link for this platform (or an explicitly chosen transport)."""
    t = (transport or default_transport()).lower()
    if t == "winpipe":
        from .winpipe import WinPipeX4Link
        return WinPipeX4Link(socket_path, on_message, reconnect_delay)
    if t == "unix":
        from .unixsocket import UnixSocketX4Link
        return UnixSocketX4Link(socket_path, on_message, reconnect_delay)
    raise ValueError(f"unknown X4 transport: {t!r} (use 'unix' or 'winpipe')")


# Back-compat: earlier code/tests did `from ..x4link import X4Link` and called it
# like a constructor. The factory has the same call shape, so keep the name.
X4Link = make_x4_link
