"""Bridge configuration. Kept tiny; sourced from env vars with sane defaults."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path


def _default_socket() -> str:
    # The bekopharm linux-compat fork hosts the Unix socket in the X4 savegame
    # folder (the only dir X4 Lua can unlink). A `.xml` extension lets X4 clean
    # it up itself. See docs/06-ecosystem-survey.md.
    base = Path.home() / ".config" / "EgoSoft" / "X4" / "save"
    return str(base / "x4_twitch.xml")


@dataclass
class Config:
    # Path to the Unix domain socket that X4 HOSTS and the bridge connects to.
    socket_path: str = field(default_factory=lambda: os.environ.get("X4_TWITCH_SOCKET", _default_socket()))
    # Event source: "stdin" (fake, for testing) or "twitch" (real EventSub).
    source: str = field(default_factory=lambda: os.environ.get("X4_TWITCH_SOURCE", "stdin"))
    # Reconnect backoff to the X4 socket, seconds.
    reconnect_delay: float = 1.0

    # --- Twitch (only used by the real source; see sources/twitch.py) ---
    channel: str = field(default_factory=lambda: os.environ.get("TWITCH_CHANNEL", ""))
    client_id: str = field(default_factory=lambda: os.environ.get("TWITCH_CLIENT_ID", ""))
    client_secret: str = field(default_factory=lambda: os.environ.get("TWITCH_CLIENT_SECRET", ""))
    # Where the bridge stores OAuth tokens (NEVER inside the X4 extension).
    token_file: str = field(default_factory=lambda: os.environ.get(
        "TWITCH_TOKEN_FILE", str(Path.home() / ".config" / "x4-twitch-bridge" / "tokens.json")))
