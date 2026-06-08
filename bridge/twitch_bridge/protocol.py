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

# X4 -> bridge (actions the game asks us to perform)
SAY = "say"            # post a message to chat (Helix)
ACTION = "action"      # generic future action (ban, shoutout, ...)
HELLO = "hello"        # handshake from X4 on connect


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
