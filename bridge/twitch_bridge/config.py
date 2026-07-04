"""Bridge configuration. Kept tiny; sourced from env vars with sane defaults."""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass, field
from pathlib import Path

# The MD pipe NAME (md/twitch_integration.xml uses "twitch"). On Windows the stock
# SirNukes Named Pipes API prefixes it with \\.\pipe\ ; on Linux the bekopharm fork
# maps it to <name>.xml in the savegame folder. Keep both in sync with the MD.
PIPE_NAME = "twitch"


def _default_socket() -> str:
    # Windows: X4's winpipe connects (as CLIENT) to \\.\pipe\<name>; the bridge
    # HOSTS that pipe (see x4link._run_win_server + docs/02 Path A).
    if sys.platform == "win32":
        return r"\\.\pipe\%s" % PIPE_NAME

    # Linux: the bekopharm linux-compat fork hosts the Unix socket in the X4
    # savegame folder (the only dir X4 Lua can unlink). A `.xml` extension lets X4
    # clean it up itself. See docs/06-ecosystem-survey.md.
    #
    # The filename is the MD pipe NAME + ".xml" — the fork strips any Windows pipe
    # path and uses <name>.xml. The save dir lives under a per-user numeric id
    # (e.g. .../X4/<id>/save), which the fork auto-detects via C.GetSaveFolderPath();
    # we glob for it so no hard-coded id.
    egosoft = Path.home() / ".config" / "EgoSoft" / "X4"
    candidates = sorted(
        (p for p in egosoft.glob("*/save") if p.is_dir()),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    base = candidates[0] if candidates else (egosoft / "save")
    return str(base / "twitch.xml")


@dataclass
class Config:
    # Path to the Unix domain socket that X4 HOSTS and the bridge connects to.
    socket_path: str = field(default_factory=lambda: os.environ.get("X4_TWITCH_SOCKET", _default_socket()))
    # Event source: "stdin" (fake, for testing) or "twitch" (real EventSub).
    source: str = field(default_factory=lambda: os.environ.get("X4_TWITCH_SOURCE", "stdin"))
    # Reconnect backoff to the X4 socket, seconds.
    reconnect_delay: float = 1.0

    # --- Companion dashboard (the cute status UI) ---
    dashboard: bool = field(default_factory=lambda: os.environ.get("X4_TWITCH_DASHBOARD", "1") != "0")
    dashboard_port: int = field(default_factory=lambda: int(os.environ.get("X4_TWITCH_DASHBOARD_PORT", "17564")))
    open_browser: bool = field(default_factory=lambda: os.environ.get("X4_TWITCH_OPEN", "0") == "1")

    # Best-effort: install an app-menu launcher on startup (so users never file-hunt).
    launcher: bool = field(default_factory=lambda: os.environ.get("X4_TWITCH_LAUNCHER", "1") != "0")

    # --- Viewer economy (wallet + karma + !buy store; doc 08) ---
    economy: bool = field(default_factory=lambda: os.environ.get("X4_TWITCH_ECONOMY", "1") != "0")
    wallet_path: str = field(default_factory=lambda: os.environ.get(
        "X4_TWITCH_WALLET", str(Path.home() / ".config" / "x4-twitch-bridge" / "viewers.json")))

    # --- Twitch (only used by the real source; see sources/twitch.py) ---
    channel: str = field(default_factory=lambda: os.environ.get("TWITCH_CHANNEL", ""))
    client_id: str = field(default_factory=lambda: os.environ.get("TWITCH_CLIENT_ID", ""))
    client_secret: str = field(default_factory=lambda: os.environ.get("TWITCH_CLIENT_SECRET", ""))
    # Where the bridge stores OAuth tokens (NEVER inside the X4 extension).
    token_file: str = field(default_factory=lambda: os.environ.get(
        "TWITCH_TOKEN_FILE", str(Path.home() / ".config" / "x4-twitch-bridge" / "tokens.json")))
