"""Persist the companion's Twitch *app* credentials (client id/secret/channel).

Stored in the user config dir, **never** the repo (gitignored, chmod 600). OAuth
*tokens* live separately in tokens.json (managed by twitchAPI). See SECURITY.md.
"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

DEFAULT_PATH = Path.home() / ".config" / "x4-twitch-bridge" / "setup.json"
FIELDS = ("client_id", "client_secret", "channel")


def _path(path: str | os.PathLike | None) -> Path:
    # X4_TWITCH_SETUP lets tests/screenshots point at an isolated file.
    return Path(path or os.environ.get("X4_TWITCH_SETUP") or DEFAULT_PATH)


def load(path: str | os.PathLike | None = None) -> dict:
    p = _path(path)
    if not p.exists():
        return {}
    try:
        data = json.loads(p.read_text())
    except (ValueError, OSError):
        return {}
    return {k: data.get(k, "") for k in FIELDS}


def save(data: dict, path: str | os.PathLike | None = None) -> None:
    p = _path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    payload = {k: str(data.get(k, "") or "") for k in FIELDS}
    fd, tmp = tempfile.mkstemp(dir=str(p.parent), suffix=".tmp")
    try:
        with os.fdopen(fd, "w") as f:
            json.dump(payload, f)
        os.replace(tmp, p)         # atomic
        try:
            os.chmod(p, 0o600)     # secret → owner-only
        except OSError:
            pass
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)
