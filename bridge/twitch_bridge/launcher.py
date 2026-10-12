"""Best-effort menu launcher install, so users never file-hunt for the script.

On Linux, writes a `.desktop` entry pointing at the companion's own `run-companion.sh`;
on Windows, a Start Menu shortcut pointing at `Start Companion.cmd` (both sit next to
this package). Called on companion startup, so a *shared* mod just needs to be run once
and the launcher appears. Idempotent and failure-tolerant.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

APP_NAME = "X4 Twitch Companion"          # plain name — no symbols in the menu entry
DESKTOP_ID = "x4-twitch-companion.desktop"
COMMENT = "Start the X4 Twitch companion + dashboard"


def companion_script() -> Path | None:
    """The run-companion script that sits next to the twitch_bridge package, if present.

    Windows double-clicks the .cmd wrapper (a .ps1 is not double-clickable); every
    other platform runs the shell script directly."""
    name = "Start Companion.cmd" if sys.platform == "win32" else "run-companion.sh"
    cand = Path(__file__).resolve().parent.parent / name
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
        f"Comment={COMMENT}\n"
        f'Exec="{script}"\n'
        "Icon=input-gaming\n"
        "Terminal=true\n"
        "Categories=Game;\n"
    )


def shortcut_path() -> Path:
    """The Start Menu .lnk (per-user Programs folder — no admin rights needed)."""
    base = Path(os.environ.get("APPDATA") or (Path.home() / "AppData" / "Roaming"))
    return base / "Microsoft" / "Windows" / "Start Menu" / "Programs" / f"{APP_NAME}.lnk"


def _write_shortcut(script: Path, dest: Path) -> bool:
    """Create/overwrite the .lnk via WScript.Shell. True on success.

    Windows has no plain-text shortcut format, so this shells out to PowerShell's COM
    bridge rather than taking a pywin32 dependency for one file."""
    ps = (
        "$ErrorActionPreference='Stop';"
        "$s=(New-Object -ComObject WScript.Shell).CreateShortcut($env:X4TC_LNK);"
        "$s.TargetPath=$env:X4TC_TARGET;"
        "$s.WorkingDirectory=$env:X4TC_DIR;"
        "$s.Description=$env:X4TC_DESC;"
        "$s.Save()"
    )
    env = {
        **os.environ,
        "X4TC_LNK": str(dest),
        "X4TC_TARGET": str(script),
        "X4TC_DIR": str(script.parent),
        "X4TC_DESC": COMMENT,
    }
    try:
        dest.parent.mkdir(parents=True, exist_ok=True)
        r = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", ps],
            check=False, capture_output=True, env=env,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        return r.returncode == 0 and dest.exists()
    except (OSError, ValueError):
        return False


def board_agent() -> str:
    """The Atelier board agent running this process, '' for a person (board r2).

    A board agent must never put anything on Simon's machine — a menu entry, a
    browser tab — whatever flags it forgot, so the launcher and --open check this
    at the point they act."""
    return os.environ.get("ATELIER_AGENT", "")


def ensure_launcher() -> Path | None:
    """Create/refresh the launcher if needed. Returns its path, or None if skipped."""
    if board_agent():
        return None
    script = companion_script()
    if script is None:
        return None

    if sys.platform == "win32":
        dest = shortcut_path()
        # Reading a .lnk back costs another PowerShell spawn; the cheap staleness
        # check is the mtime — refresh only when the target script is newer.
        try:
            if dest.exists() and dest.stat().st_mtime >= script.stat().st_mtime:
                return dest
        except OSError:
            pass
        return dest if _write_shortcut(script, dest) else None

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
