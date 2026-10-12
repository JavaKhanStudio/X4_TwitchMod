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
CMDFAIL = "cmdfail"    # a `cmd` could not be carried out -> refund the buyer
FLEET = "fleet"        # the player's ship roster (see fleet.py for the row format)
SHIPDOWN = "shipdown"  # an ADOPTED ship was destroyed (idcode, macro, killer)
SHIPNEW = "shipnew"    # a resurrected hull exists: {old: <id>, idcode: <new id>}

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
    `tier` (0..3, doc 08 §5) lets MD apply shared severity-aware safety.

    `argv` carries the SAME values as `args`, as an ORDERED array, and is what the
    mod actually reads. `args` is a JSON object; the ui lua decodes it into a Lua
    hash table whose `pairs()` order is undefined — verified: {"ware","qty"} came
    back as "50;energycells". JSON arrays keep their order through the decoder, so
    multi-arg commands only survive the trip via `argv`. `args` stays for logs and
    for anything reading a value by name."""
    args = args or {}
    msg: dict[str, Any] = {"t": COMMAND, "id": action, "by": by, "args": args,
                           "argv": [str(v) for v in args.values()]}
    if tier is not None:
        msg["tier"] = tier
    return msg


# ---- constructors (X4 -> chat, and companion status) ------------------------

def fleet(data: str, total: int | None = None, sent: int | None = None) -> dict[str, Any]:
    """X4 -> bridge: the player's ship roster (MD cue Twitch_PublishFleet).

    `data` is rows joined by ';', fields by '|': `IDCODE|MACRO|SIZE`. `total` is how
    many ships the player actually owns and `sent` how many fit in this line, so a
    capped roster can never be mistaken for the whole fleet. Defined here (rather
    than only in MD) so the format has one written-down owner and the tests build it
    the same way the game does. See fleet.py."""
    n = len([r for r in data.split(";") if r])
    return {"t": FLEET, "total": total if total is not None else n,
            "sent": sent if sent is not None else n, "data": data}


def shipdown(idcode: str, macro: str = "", killer: str = "") -> dict[str, Any]:
    """X4 -> bridge: an adopted ship died (MD cue Twitch_ShipDown).

    `macro` matters more than it looks: once the ship is gone the roster cannot say
    what it was, and the macro is all that is needed to rebuild it. MD reads it
    inside the destroyed event, the last moment the object is still readable."""
    return {"t": SHIPDOWN, "idcode": idcode, "macro": macro, "killer": killer}


def shipnew(old: str, idcode: str) -> dict[str, Any]:
    """X4 -> bridge: a replacement hull was built. A rebuilt ship is a NEW object
    with a NEW id code, so the adoption has to be re-keyed — only MD learns the new
    code, which is why it reports back rather than the bridge assuming."""
    return {"t": SHIPNEW, "old": old, "idcode": idcode}


def say(msg: str) -> dict[str, Any]:
    """Ask the bridge to post `msg` to Twitch chat (via the source / Helix)."""
    return {"t": SAY, "msg": msg}


def cmdfail(action: str, reason: str = "") -> dict[str, Any]:
    """X4 could not carry out a `cmd` -> the bridge refunds whoever bought it.

    Only the action id and a human reason cross the pipe: MD has no idea who the
    buyer was (the `by` field never reaches it — the ui lua forwards only the arg
    VALUES), so the bridge matches this against its own record of what it charged
    for that action. See Economy.handle_x4_failure."""
    return {"t": CMDFAIL, "id": action, "reason": reason}


def status(*, connected: bool, channel: str = "", viewers: int = 0,
           x4: bool = False) -> dict[str, Any]:
    """Companion -> X4: drive the in-game status panel (doc 09 §6)."""
    return {"t": STATUS, "connected": connected, "channel": channel,
            "viewers": viewers, "x4": x4}


def control(action: str, **fields: Any) -> dict[str, Any]:
    """X4 -> companion: 'enable' | 'disable' | 'connect' (with creds in fields)."""
    return {"t": CONTROL, "action": action, **fields}
