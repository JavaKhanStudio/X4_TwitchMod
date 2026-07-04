"""Viewer wallet + karma governor (doc 08 §2-3). Bridge-side, persistent, headless.

Owns the per-viewer economy: coins (a watch-time currency), karma (a reputation %
that multiplies coin income and is moved by purchases), activity tracking, and the
periodic award loop. Persisted to a JSON file (atomic write), gitignored.

This is pure logic — no asyncio, no Twitch — so it is fully unit-testable. The app
calls `note_activity()` on chat, `award()` on a timer, and the purchase engine
(economy.py) calls `take_coins()` / `apply_purchase_karma()`.
"""

from __future__ import annotations

import json
import math
import os
import tempfile
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path


@dataclass
class EconomySettings:
    """All the tunable knobs (doc 08 §2.2, §3). Times are in SECONDS."""

    # earning
    starting_balance: int = 150
    coin_interval: float = 120.0      # award cadence (2 min)
    coin_amount: int = 30             # base per interval, before multipliers
    min_purchase_price: int = 60
    chat_reqs_for_coins: bool = True
    half_coins_after: float = 30 * 60   # idle knee → half coins
    no_coins_after: float = 60 * 60     # idle floor → no coins

    # role perks: flat bonus + income multiplier
    sub_bonus: int = 10
    sub_mult: float = 1.25
    vip_bonus: int = 5
    vip_mult: float = 1.15
    mod_bonus: int = 3
    mod_mult: float = 1.05

    # karma
    starting_karma: int = 100
    karma_cap: int = 140
    karma_floor: int = 10
    # purchase karma deltas: delta = round(price / divisor); good/neutral add, bad/doom subtract
    karma_good_div: int = 12
    karma_neutral_div: int = 28
    karma_bad_div: int = 16
    karma_doom_div: int = 7

    # per-window event caps (doc 08 §3.1)
    cap_window: float = 15 * 60       # rolling window for the caps below, seconds
    max_bad_per_interval: int = 3
    max_good_per_interval: int = 10
    max_neutral_per_interval: int = 10
    max_doom_per_interval: int = 1

    # gifting (doc 08 §4.2)
    min_karma_to_gift: int = 0


@dataclass
class Viewer:
    username: str
    coins: int = 0
    karma: int = 100
    last_seen: float = 0.0
    sub: bool = False
    vip: bool = False
    mod: bool = False
    banned: bool = False


def new_karma(current: int, karmatype: str, price: int, s: EconomySettings) -> int:
    """Karma after a purchase (doc 08 §3). Good/neutral raise it, bad/doom lower it,
    scaled by price; clamped to [floor, cap]."""
    div = {"good": s.karma_good_div, "neutral": s.karma_neutral_div,
           "bad": s.karma_bad_div, "doom": s.karma_doom_div}.get(karmatype, s.karma_neutral_div)
    delta = round(price / div) if div else 0
    if karmatype in ("bad", "doom"):
        delta = -delta
    return max(s.karma_floor, min(s.karma_cap, current + delta))


class Wallet:
    def __init__(self, path: str, settings: EconomySettings | None = None, clock=time.time):
        self.path = Path(path)
        self.s = settings or EconomySettings()
        self.clock = clock
        self.viewers: dict[str, Viewer] = {}
        self.coins_awarded_total = 0
        self.load()

    # -- viewer access -------------------------------------------------------
    def get(self, username: str) -> Viewer:
        u = username.lower()
        v = self.viewers.get(u)
        if v is None:
            v = Viewer(username=u, coins=self.s.starting_balance, karma=self.s.starting_karma)
            self.viewers[u] = v
        return v

    def note_activity(self, username: str, *, sub=None, vip=None, mod=None) -> Viewer:
        v = self.get(username)
        v.last_seen = self.clock()
        if sub is not None:
            v.sub = sub
        if vip is not None:
            v.vip = vip
        if mod is not None:
            v.mod = mod
        return v

    # -- coins ---------------------------------------------------------------
    def give_coins(self, username: str, n: int) -> int:
        v = self.get(username)
        v.coins = max(0, v.coins + n)
        return v.coins

    def take_coins(self, username: str, n: int) -> bool:
        """Debit n coins if affordable; return success."""
        v = self.get(username)
        if v.coins < n:
            return False
        v.coins -= n
        return True

    # -- karma ---------------------------------------------------------------
    def apply_purchase_karma(self, username: str, karmatype: str, price: int) -> int:
        v = self.get(username)
        v.karma = new_karma(v.karma, karmatype, price, self.s)
        return v.karma

    def set_karma(self, username: str, karma: int) -> int:
        v = self.get(username)
        v.karma = max(self.s.karma_floor, min(self.s.karma_cap, karma))
        return v.karma

    # -- moderation ----------------------------------------------------------
    def set_banned(self, username: str, banned: bool) -> Viewer:
        """Block/unblock a viewer: banned viewers stop earning (award loop) and
        are refused by the purchase engine. Returns the viewer."""
        v = self.get(username)
        v.banned = banned
        return v

    def viewer_list(self) -> list[dict]:
        """Snapshot of every known viewer for the dashboard admin panel,
        richest first. Read-only projection — never hand out live Viewers."""
        rows = [
            {"username": v.username, "coins": v.coins, "karma": v.karma,
             "banned": v.banned, "sub": v.sub, "vip": v.vip, "mod": v.mod}
            for v in self.viewers.values()
        ]
        rows.sort(key=lambda r: (r["banned"], -r["coins"], r["username"]))
        return rows

    # -- the award loop (doc 08 §2.1) ---------------------------------------
    def _activity_mult(self, v: Viewer) -> float:
        if not self.s.chat_reqs_for_coins:
            return 1.0
        idle = self.clock() - v.last_seen
        if idle > self.s.no_coins_after:
            return 0.0
        if idle > self.s.half_coins_after:
            return 0.5
        return 1.0

    def reward_for(self, v: Viewer) -> int:
        base = self.s.coin_amount
        mult = v.karma / 100.0
        if v.sub:
            base += self.s.sub_bonus
            mult *= self.s.sub_mult
        elif v.vip:
            base += self.s.vip_bonus
            mult *= self.s.vip_mult
        elif v.mod:
            base += self.s.mod_bonus
            mult *= self.s.mod_mult
        return int(math.ceil(base * mult * self._activity_mult(v)))

    def award(self) -> int:
        """Award coins to every active, non-banned viewer. Returns total handed out."""
        total = 0
        for v in self.viewers.values():
            if v.banned:
                continue
            n = self.reward_for(v)
            if n > 0:
                v.coins += n
                total += n
        self.coins_awarded_total += total
        return total

    # -- persistence (atomic) ------------------------------------------------
    def load(self) -> None:
        if not self.path.exists():
            return
        try:
            data = json.loads(self.path.read_text())
        except (ValueError, OSError):
            return
        for u, d in data.get("viewers", {}).items():
            self.viewers[u] = Viewer(**d)
        self.coins_awarded_total = data.get("coins_awarded_total", 0)

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "viewers": {u: asdict(v) for u, v in self.viewers.items()},
            "coins_awarded_total": self.coins_awarded_total,
        }
        fd, tmp = tempfile.mkstemp(dir=str(self.path.parent), suffix=".tmp")
        try:
            with os.fdopen(fd, "w") as f:
                json.dump(payload, f)
            os.replace(tmp, self.path)   # atomic
        finally:
            if os.path.exists(tmp):
                os.unlink(tmp)

    def stats(self) -> dict:
        return {
            "viewers": len(self.viewers),
            "coins_in_circulation": sum(v.coins for v in self.viewers.values()),
            "coins_awarded_total": self.coins_awarded_total,
        }
