"""Wire protocol between the Twitch bridge and X4.

One JSON object per line ("newline-delimited JSON"), UTF-8. This is the *only*
contract between the two processes; keep it small and stable.

Direction is encoded by message type (`t`):
  bridge -> X4 : chat, redeem, sub, cheer, raid, follow, ready
  X4 -> bridge : say, action, hello

See docs/00-overview-and-architecture.md §5 and docs/06-ecosystem-survey.md.
"""

from __future__ import annotations

import json
from typing import Any

# ---- message type constants -------------------------------------------------

# bridge -> X4 (Twitch events)
CHAT = "chat"
REDEEM = "redeem"      # channel-points custom reward redemption
SUB = "sub"
CHEER = "cheer"        # bits
RAID = "raid"
FOLLOW = "follow"
READY = "ready"        # handshake: bridge is connected and Twitch is live

# bridge -> X4 (vetted command, emitted by the command engine)
COMMAND = "cmd"        # a permission/cooldown-checked game action

# X4 -> bridge (actions the game asks us to perform)
SAY = "say"            # post a message to chat (Helix)
ACTION = "action"      # generic future action (ban, shoutout, ...)
HELLO = "hello"        # handshake from X4 on connect

# companion <-> X4 (status panel + the in-game Enable-Twitch toggle; doc 09 §6)
STATUS = "status"      # companion -> X4: connection / viewer-count for the in-game panel
CONTROL = "control"    # X4 -> companion: enable / disable / connect (with creds)


def encode(msg: dict[str, Any]) -> bytes:
    """Serialize one message to a single UTF-8 line (with trailing newline)."""
    return (json.dumps(msg, separators=(",", ":"), ensure_ascii=False) + "\n").encode("utf-8")


def decode(line: bytes | str) -> dict[str, Any]:
    """Parse one line into a message dict. Raises ValueError on bad input."""
    if isinstance(line, bytes):
        line = line.decode("utf-8")
    line = line.strip()
    if not line:
        raise ValueError("empty line")
    obj = json.loads(line)
    if not isinstance(obj, dict) or "t" not in obj:
        raise ValueError(f"not a protocol message: {line!r}")
    return obj


# ---- constructors (bridge -> X4) --------------------------------------------

def chat(user: str, msg: str, badges: list[str] | None = None) -> dict[str, Any]:
    return {"t": CHAT, "user": user, "msg": msg, "badges": badges or []}


def redeem(user: str, reward: str, amount: int = 1) -> dict[str, Any]:
    return {"t": REDEEM, "user": user, "reward": reward, "amount": amount}


def sub(user: str, tier: str = "1000", months: int = 1) -> dict[str, Any]:
    return {"t": SUB, "user": user, "tier": tier, "months": months}


def cheer(user: str, bits: int) -> dict[str, Any]:
    return {"t": CHEER, "user": user, "bits": bits}


def raid(user: str, viewers: int) -> dict[str, Any]:
    return {"t": RAID, "user": user, "viewers": viewers}


def follow(user: str) -> dict[str, Any]:
    return {"t": FOLLOW, "user": user}


def ready() -> dict[str, Any]:
    return {"t": READY}


def command(action: str, by: str, args: dict[str, Any] | None = None,
            tier: int | None = None) -> dict[str, Any]:
    """A vetted game action (post-policy). `action` is the id X4 dispatches on.
    `tier` (0..3, doc 08 §5) lets MD apply shared severity-aware safety."""
    msg: dict[str, Any] = {"t": COMMAND, "id": action, "by": by, "args": args or {}}
    if tier is not None:
        msg["tier"] = tier
    return msg


# ---- constructors (X4 -> chat, and companion status) ------------------------

def say(msg: str) -> dict[str, Any]:
    """Ask the bridge to post `msg` to Twitch chat (via the source / Helix)."""
    return {"t": SAY, "msg": msg}


def status(*, connected: bool, channel: str = "", viewers: int = 0,
           x4: bool = False) -> dict[str, Any]:
    """Companion -> X4: drive the in-game status panel (doc 09 §6)."""
    return {"t": STATUS, "connected": connected, "channel": channel,
            "viewers": viewers, "x4": x4}


def control(action: str, **fields: Any) -> dict[str, Any]:
    """X4 -> companion: 'enable' | 'disable' | 'connect' (with creds in fields)."""
    return {"t": CONTROL, "action": action, **fields}
