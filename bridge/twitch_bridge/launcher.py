"""Best-effort app-menu launcher install, so users never file-hunt for the script.

Writes a `.desktop` entry pointing at the companion's own `run-companion.sh` (which
sits next to this package). Called on companion startup, so a *shared* mod just needs
to be run once and the launcher appears. Idempotent and failure-tolerant.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

APP_NAME = "X4 Twitch Companion"          # plain name — no symbols in the menu entry
DESKTOP_ID = "x4-twitch-companion.desktop"


def companion_script() -> Path | None:
    """The run-companion.sh that sits next to the twitch_bridge package, if present."""
    cand = Path(__file__).resolve().parent.parent / "run-companion.sh"
    return cand if cand.exists() else None


def desktop_path() -> Path:
    base = Path(os.environ.get("XDG_DATA_HOME") or (Path.home() / ".local" / "share"))
    return base / "applications" / DESKTOP_ID


def desktop_contents(script: Path) -> str:
    # The path can contain spaces (e.g. "X4 Foundations") -> MUST be double-quoted
    # in Exec per the Desktop Entry spec, or it won't launch.
    return (
        "[Desktop Entry]\n"
        "Type=Application\n"
        "Version=1.0\n"
        f"Name={APP_NAME}\n"
        "Comment=Start the X4 Twitch companion + dashboard\n"
        f'Exec="{script}"\n'
        "Icon=input-gaming\n"
        "Terminal=true\n"
        "Categories=Game;\n"
    )


def ensure_launcher() -> Path | None:
    """Create/refresh the launcher if needed. Returns its path, or None if skipped.

    The .desktop app-menu entry is a Linux (freedesktop) concept; on Windows the
    companion is started from run-companion.ps1 / the Steam launch option, so we
    skip this entirely."""
    if sys.platform == "win32":
        return None
    script = companion_script()
    if script is None:
        return None
    dest = desktop_path()
    want = desktop_contents(script)
    try:
        if dest.exists() and dest.read_text() == want:
            return dest
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(want)
        os.chmod(dest, 0o755)
        if shutil.which("update-desktop-database"):
            subprocess.run(["update-desktop-database", str(dest.parent)],
                           check=False, capture_output=True)
        return dest
    except OSError:
        return None
