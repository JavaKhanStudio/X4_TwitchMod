"""Command + policy engine (the bridge owns policy; X4 owns effects — D6).

Turns raw Twitch events into *vetted* `cmd` messages for X4, applying:
  * permissions  — minimum viewer role (everyone < subscriber < vip < moderator < broadcaster)
  * cooldowns    — global per-command, and optional per-user

A Command is triggered either by a chat prefix (`!spawn`) or by an event type
(`raid`, `sub`, `cheer`, `follow`, `redeem`, optionally matching a reward title).
Edit the catalog in `catalog.py` to change what viewers can do.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field

from . import protocol

log = logging.getLogger("commands")

ROLE_RANK = {"everyone": 0, "subscriber": 1, "vip": 2, "moderator": 3, "broadcaster": 4}

# Twitch chat badge set_id -> our role name.
BADGE_ROLE = {
    "broadcaster": "broadcaster",
    "moderator": "moderator",
    "vip": "vip",
    "subscriber": "subscriber",
    "founder": "subscriber",
}


def role_of(badges) -> str:
    """Highest role implied by a chat message's badges."""
    best, rank = "everyone", 0
    for b in badges or []:
        r = BADGE_ROLE.get(b)
        if r and ROLE_RANK[r] > rank:
            best, rank = r, ROLE_RANK[r]
    return best


@dataclass
class Command:
    id: str                                  # unique id (also the cooldown key)
    action: str                              # action id X4 dispatches on
    chat_prefix: str | None = None           # e.g. "!spawn" (chat trigger)
    on_event: str | None = None              # e.g. "raid"/"sub"/"cheer"/"follow"/"redeem"
    reward: str | None = None                # for redeem: match this reward title
    min_role: str = "everyone"               # permission floor (chat triggers)
    cooldown: float = 0.0                    # global cooldown, seconds
    user_cooldown: float = 0.0               # per-user cooldown, seconds
    arg_names: list[str] = field(default_factory=list)  # chat tokens -> named args


class CommandEngine:
    def __init__(self, commands, clock=time.monotonic):
        self.clock = clock
        self._by_prefix: dict[str, Command] = {}
        self._by_event: dict[str, list[Command]] = {}
        for c in commands:
            if c.chat_prefix:
                self._by_prefix[c.chat_prefix.lower()] = c
            if c.on_event:
                self._by_event.setdefault(c.on_event, []).append(c)
        self._last_global: dict[str, float] = {}
        self._last_user: dict[tuple[str, str], float] = {}

    def process(self, event: dict) -> list[dict]:
        """Return zero or more vetted `cmd` messages for this Twitch event."""
        if event.get("t") == protocol.CHAT:
            return self._chat(event)
        return self._event(event)

    # ---- triggers ----------------------------------------------------------

    def _chat(self, event: dict) -> list[dict]:
        msg = (event.get("msg") or "").strip()
        if not msg.startswith("!"):
            return []
        tokens = msg.split()
        cmd = self._by_prefix.get(tokens[0].lower())
        if cmd is None:
            return []
        user = event.get("user", "?")
        role = role_of(event.get("badges"))
        if ROLE_RANK[role] < ROLE_RANK[cmd.min_role]:
            log.debug("deny %s for %s (role %s < %s)", cmd.id, user, role, cmd.min_role)
            return []
        if not self._cooldown_ok(cmd, user):
            log.debug("cooldown %s for %s", cmd.id, user)
            return []
        args = {name: tokens[i + 1] for i, name in enumerate(cmd.arg_names)
                if i + 1 < len(tokens)}
        return [protocol.command(cmd.action, user, args)]

    def _event(self, event: dict) -> list[dict]:
        cmds = self._by_event.get(event.get("t"), [])
        out: list[dict] = []
        for cmd in cmds:
            if cmd.reward and event.get("reward") != cmd.reward:
                continue
            user = event.get("user", "?")
            if not self._cooldown_ok(cmd, user):  # events skip role gating
                continue
            out.append(protocol.command(cmd.action, user, _event_args(event)))
        return out

    # ---- cooldown ----------------------------------------------------------

    def _cooldown_ok(self, cmd: Command, user: str) -> bool:
        now = self.clock()
        if cmd.cooldown:
            last = self._last_global.get(cmd.id)
            if last is not None and now - last < cmd.cooldown:
                return False
        if cmd.user_cooldown:
            last = self._last_user.get((cmd.id, user))
            if last is not None and now - last < cmd.user_cooldown:
                return False
        self._last_global[cmd.id] = now
        self._last_user[(cmd.id, user)] = now
        return True


def _event_args(event: dict) -> dict:
    """Carry the useful scalar fields of an event into the command args."""
    keep = ("viewers", "bits", "tier", "months", "reward", "amount")
    return {k: event[k] for k in keep if k in event}
