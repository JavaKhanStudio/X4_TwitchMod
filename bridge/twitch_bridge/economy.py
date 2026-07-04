"""The `!buy` purchase engine + economy chat commands (doc 08 §4).

Bridge owns policy (coins, karma, cooldowns, per-window caps); X4 owns effects.
`handle_chat(event)` returns a list of outputs, each either a vetted `cmd` (to X4)
or a `say` (to chat). Pure logic over a Wallet + the CATALOG — fully unit-testable.
"""

from __future__ import annotations

import time
from collections import deque

from . import protocol
from . import ships as shipreg
from .catalog import CATALOG, StoreEvent
from .commands import ROLE_RANK, role_of
from .runtime import Runtime
from .wallet import EconomySettings, Wallet

KARMA_CAP_FIELD = {
    "bad": "max_bad_per_interval",
    "good": "max_good_per_interval",
    "neutral": "max_neutral_per_interval",
    "doom": "max_doom_per_interval",
}

# Chat command shortcuts — EDIT THIS to add aliases. canonical -> [aliases] (no "!").
# e.g. "balance" responds to !balance, !bal, !coins. Add a word to a list to add a shortcut.
COMMAND_ALIASES = {
    "balance":      ["balance", "bal", "coins", "money"],
    "karma":        ["karma", "whatiskarma", "rep"],
    "shop":         ["shop", "catalog", "store", "purchaselist", "instructions", "commands", "help"],
    "gift":         ["gift", "give"],
    "buy":          ["buy", "purchase"],
    "givecoins":    ["givecoins"],
    "giveallcoins": ["giveallcoins"],
    "setkarma":     ["setkarma"],
}


class Economy:
    def __init__(self, wallet: Wallet, catalog: list[StoreEvent] | None = None,
                 clock=time.monotonic, runtime: Runtime | None = None):
        self.w = wallet
        self.s: EconomySettings = wallet.s
        self.clock = clock
        self.rt = runtime if runtime is not None else Runtime()
        # !buy lookup: buy_key + nicknames -> event. Info actions are excluded —
        # they answer via COMMAND_ALIASES below, they are not purchases.
        self.by_key = {}
        for e in (catalog if catalog is not None else CATALOG):
            if e.kind == "info":
                continue
            self.by_key[e.buy_key.lower()] = e
            for n in e.nicknames:
                self.by_key[n.lower()] = e
        self._purchases: deque[tuple[float, str, str]] = deque()  # (when, event_id, karmatype)
        # alias ("!bal") -> canonical ("balance")
        self._canon = {f"!{a.lower()}": c for c, al in COMMAND_ALIASES.items() for a in al}

    # -- public: process one chat message -----------------------------------
    def handle_chat(self, event: dict) -> list[dict]:
        user = event.get("user", "?")
        badges = event.get("badges")
        role = role_of(badges)
        self.w.note_activity(user, sub=("subscriber" in (badges or []) or "founder" in (badges or [])),
                             vip=("vip" in (badges or [])), mod=("moderator" in (badges or [])))
        msg = (event.get("msg") or "").strip()
        if not msg.startswith("!"):
            return []
        tok = msg.split()
        canon = self._canon.get(tok[0].lower())   # resolve any alias to its canonical command

        if canon == "balance":
            v = self.w.get(user)
            return [protocol.say(f"@{user} balance: {v.coins} coins · karma {v.karma}%")]
        if canon == "karma":
            return [protocol.say(f"@{user} karma is a % that multiplies your coin income; "
                                 f"buying good events raises it, bad/doom events lower it. You: "
                                 f"{self.w.get(user).karma}%")]
        if canon == "shop":
            return [protocol.say(f"@{user} buy events with !buy <key>. Try !buy "
                                 + ", ".join(sorted({e.buy_key for e in self.by_key.values() if e.enabled})[:6]))]
        if canon == "gift":
            return self._gift(user, tok)
        if canon == "buy":
            return self._buy(user, role, tok)
        # admin (mod/broadcaster only)
        if canon in ("givecoins", "giveallcoins", "setkarma") and ROLE_RANK[role] >= ROLE_RANK["moderator"]:
            return self._admin(canon, tok)
        return []

    # -- the purchase pipeline (doc 08 §4.1) --------------------------------
    def _buy(self, user: str, role: str, tok: list[str]) -> list[dict]:
        if self.w.get(user).banned:
            return []   # blocked viewers are silently ignored (no engagement)
        if len(tok) < 2:
            return [protocol.say(f"@{user} usage: !buy <key> [args]")]
        ev = self.by_key.get(tok[1].lower())
        if ev is None or not ev.enabled:
            return [protocol.say(f"@{user} '{tok[1]}' is not available.")]

        if ev.ship_picker:                       # "!buy ship <name>" — priced per ship
            return self._buy_ship(user, role, ev, tok[2:])

        argvals = tok[2:]
        cost, err = self._cost(ev, argvals)
        if err:
            return [protocol.say(f"@{user} {err}")]

        if ROLE_RANK[role] < ROLE_RANK[ev.min_role]:
            return [protocol.say(f"@{user} {ev.label or ev.buy_key} needs {ev.min_role}.")]
        if self.w.get(user).coins < cost:
            return [protocol.say(f"@{user} not enough coins: {ev.label or ev.buy_key} costs "
                                 f"{cost}, you have {self.w.get(user).coins}.")]
        capped = self._cap_check(ev)
        if capped:
            return [protocol.say(f"@{user} {capped}")]

        # commit
        self.w.take_coins(user, cost)
        self.w.apply_purchase_karma(user, ev.karma, cost)
        self._record(ev)
        args = {name: argvals[i] for i, name in enumerate(ev.args) if i < len(argvals)}
        bal = self.w.get(user)   # post-deduction balance
        return [
            protocol.command(ev.id, user, args, tier=ev.tier),
            protocol.say(f"@{user} bought {ev.label or ev.buy_key} for {cost} — "
                         f"{bal.coins} coins left (karma {bal.karma}%)"),
        ]

    # -- "buy any ship", priced by the ship's in-game value (ships.py registry) ---
    def _buy_ship(self, user: str, role: str, ev: StoreEvent, argvals: list[str]) -> list[dict]:
        query = " ".join(argvals)
        if not query:                            # "!buy ship" / "!buy ships" -> the list
            return [protocol.say(self._ship_list_msg(user))]
        ship, suggestions = shipreg.resolve(query)
        if ship is None:
            if suggestions:
                names = ", ".join(s.key for s in suggestions[:8])
                return [protocol.say(f"@{user} did you mean: {names}? (!buy ship <name>)")]
            return [protocol.say(f"@{user} no ship '{query}'. Try !buy ship for the list.")]

        cost = ship.coins
        if ROLE_RANK[role] < ROLE_RANK[ev.min_role]:
            return [protocol.say(f"@{user} {ev.label or ev.buy_key} needs {ev.min_role}.")]
        if self.w.get(user).coins < cost:
            return [protocol.say(f"@{user} not enough coins: {ship.label} costs {cost}, "
                                 f"you have {self.w.get(user).coins}.")]
        capped = self._cap_check(ev)
        if capped:
            return [protocol.say(f"@{user} {capped}")]

        # commit — send ONLY the macro as the arg (the lua ';'-joins arg values; a
        # single value keeps event.param3 == the macro string for macro.{$macro}).
        self.w.take_coins(user, cost)
        self.w.apply_purchase_karma(user, ev.karma, cost)
        self._record(ev)
        bal = self.w.get(user)
        return [
            protocol.command(ev.id, user, {"macro": ship.macro}, tier=ev.tier),
            protocol.say(f"@{user} bought a {ship.label} ({ship.size} {ship.role}) for {cost} — "
                         f"{bal.coins} coins left (karma {bal.karma}%)"),
        ]

    def _ship_list_msg(self, user: str) -> str:
        smp = ", ".join(f"{s.key} {s.coins}c" for s in shipreg.sample(6))
        return (f"@{user} buy any of {len(shipreg.SHIPS)} ships with !buy ship <name>. "
                f"e.g. {smp}")

    def _cost(self, ev: StoreEvent, argvals: list[str]):
        if ev.variable:
            if not argvals or not argvals[-1].lstrip("-").isdigit():
                return 0, f"usage: {ev.syntax}"
            qty = int(argvals[-1])
            if qty <= 0:
                return 0, "quantity must be positive."
            return max(self.s.min_purchase_price, ev.cost_per_unit * qty), None
        return ev.cost, None

    # -- per-window caps + cooldown (doc 08 §3.1) ---------------------------
    def _prune(self) -> None:
        cutoff = self.clock() - self.s.cap_window
        while self._purchases and self._purchases[0][0] < cutoff:
            self._purchases.popleft()

    def _cap_check(self, ev: StoreEvent) -> str | None:
        self._prune()
        # per-event re-buy cooldown (skipped in testing mode; caps still apply)
        if ev.cooldown and self.rt.cooldowns_enabled:
            last = max((t for t, eid, _ in self._purchases if eid == ev.id), default=None)
            if last is not None and self.clock() - last < ev.cooldown:
                wait = int(ev.cooldown - (self.clock() - last))
                return f"{ev.label or ev.buy_key} on cooldown, wait {wait}s."
        # per-event cap within window (skipped when caps disabled for testing)
        if ev.event_cap and self.rt.caps_enabled:
            n = sum(1 for _, eid, _ in self._purchases if eid == ev.id)
            if n >= ev.event_cap:
                return f"{ev.label or ev.buy_key} maxed this window."
        # per-karma-type cap within window (skipped when caps disabled for testing)
        limit = getattr(self.s, KARMA_CAP_FIELD.get(ev.karma, ""), None)
        if limit is not None and self.rt.caps_enabled:
            n = sum(1 for _, _, k in self._purchases if k == ev.karma)
            if n >= limit:
                return f"too many '{ev.karma}' events right now, try later."
        return None

    def _record(self, ev: StoreEvent) -> None:
        self._purchases.append((self.clock(), ev.id, ev.karma))

    # -- gifting + admin ----------------------------------------------------
    def _gift(self, user: str, tok: list[str]) -> list[dict]:
        if self.w.get(user).banned:
            return []   # blocked viewers can't move coins either
        if len(tok) < 3 or not tok[2].lstrip("-").isdigit():
            return [protocol.say(f"@{user} usage: !gift @user <amount>")]
        target = tok[1].lstrip("@")
        amount = int(tok[2])
        if amount <= 0:
            return [protocol.say(f"@{user} amount must be positive.")]
        if self.w.get(user).karma < self.s.min_karma_to_gift:
            return [protocol.say(f"@{user} your karma is too low to gift.")]
        if not self.w.take_coins(user, amount):
            return [protocol.say(f"@{user} not enough coins to gift {amount}.")]
        self.w.give_coins(target, amount)
        return [protocol.say(f"@{target} got {amount} coins from @{user}!")]

    def _admin(self, cmd: str, tok: list[str]) -> list[dict]:
        if cmd == "giveallcoins" and len(tok) >= 2 and tok[1].lstrip("-").isdigit():
            n = int(tok[1])
            for v in self.w.viewers.values():
                self.w.give_coins(v.username, n)
            return [protocol.say(f"gave {n} coins to all {len(self.w.viewers)} viewers.")]
        if cmd == "givecoins" and len(tok) >= 3 and tok[2].lstrip("-").isdigit():
            target = tok[1].lstrip("@")
            self.w.give_coins(target, int(tok[2]))
            return [protocol.say(f"@{target} now has {self.w.get(target).coins} coins.")]
        if cmd == "setkarma" and len(tok) >= 3 and tok[2].lstrip("-").isdigit():
            target = tok[1].lstrip("@")
            self.w.set_karma(target, int(tok[2]))
            return [protocol.say(f"@{target} karma set to {self.w.get(target).karma}%.")]
        return []
