"""The `!buy` purchase engine + economy chat commands (doc 08 §4).

Bridge owns policy (coins, karma, cooldowns, per-window caps); X4 owns effects.
`handle_chat(event)` returns a list of outputs, each either a vetted `cmd` (to X4)
or a `say` (to chat). Pure logic over a Wallet + the CATALOG — fully unit-testable.
"""

from __future__ import annotations

import time
from collections import deque

from . import protocol
from . import sectors as sectorreg
from . import ships as shipreg
from .catalog import (CATALOG, FACTION_KEYS, STANCE_KEYS, STANCE_TARGETS,
                      StoreEvent, resolve_faction, resolve_stance)
from . import fleet as fleetreg
from .fleet import Fleet, FleetShip
from .commands import ROLE_RANK, role_of
from .runtime import Runtime
from .wallet import EconomySettings, Wallet

KARMA_CAP_FIELD = {
    "bad": "max_bad_per_interval",
    "good": "max_good_per_interval",
    "neutral": "max_neutral_per_interval",
    "doom": "max_doom_per_interval",
}

# How long a charged purchase stays refundable. X4 acts on a command within a frame
# or two of receiving it, so this only has to outlive pipe latency; it is generous so
# a paused/loading game still refunds, and short enough that a viewer can't be handed
# coins back for something that visibly happened ages ago.
REFUND_WINDOW = 300.0

# Chat command shortcuts — EDIT THIS to add aliases. canonical -> [aliases] (no "!").
# e.g. "balance" responds to !balance, !bal, !coins. Add a word to a list to add a shortcut.
COMMAND_ALIASES = {
    "balance":      ["balance", "bal", "coins", "money"],
    "karma":        ["karma", "whatiskarma", "rep"],
    "shop":         ["shop", "catalog", "store", "purchaselist", "instructions", "commands", "help"],
    "sectors":      ["sectors", "sector", "where", "map"],
    "fleet":        ["fleet", "adoptable"],
    "myship":       ["myship", "myships"],
    "abandon_ship": ["abandon", "disown", "release"],
    "resurrect_ship": ["resurrect", "rebuild", "revive"],
    "gift":         ["gift", "give"],
    "buy":          ["buy", "purchase"],
    "givecoins":    ["givecoins"],
    "giveallcoins": ["giveallcoins"],
    "setkarma":     ["setkarma"],
}


class Economy:
    def __init__(self, wallet: Wallet, catalog: list[StoreEvent] | None = None,
                 clock=time.monotonic, runtime: Runtime | None = None,
                 fleet: Fleet | None = None):
        self.w = wallet
        self.s: EconomySettings = wallet.s
        self.clock = clock
        self.rt = runtime if runtime is not None else Runtime()
        # The player's ship roster, published by X4. None => adoption is unavailable
        # (headless tests, economy running before the game ever connected).
        self.fleet = fleet
        # !buy lookup: buy_key + nicknames -> event. Info actions are excluded —
        # they answer via COMMAND_ALIASES below, they are not purchases.
        self.by_key = {}
        self.events = list(catalog if catalog is not None else CATALOG)
        for e in self.events:
            if e.kind == "info":
                continue
            self.by_key[e.buy_key.lower()] = e
            for n in e.nicknames:
                self.by_key[n.lower()] = e
        self._purchases: deque[tuple[float, str, str]] = deque()  # (when, event_id, karmatype)
        # Refundable purchases awaiting X4's verdict: (when, event_id, user, cost,
        # karma_before, label). X4 only reports FAILURE (a success ack per command
        # would double the pipe traffic for nothing), so entries sit here until they
        # are refunded or age out of REFUND_WINDOW.
        self._refundable: deque[tuple[float, str, str, int, int, str]] = deque()
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
            # Crisis events are left OUT of the teaser while the switch is off —
            # they sort near the front alphabetically ("armada"), and advertising a
            # key that answers "not right now" reads as broken, not as gated.
            keys = sorted({e.buy_key for e in self.by_key.values()
                           if e.enabled and (self.rt.crisis_enabled or not e.crisis)})
            return [protocol.say(f"@{user} buy events with !buy <key>. Try !buy "
                                 + ", ".join(keys[:6]))]
        if canon == "sectors":
            return [protocol.say(self._sector_msg(user, " ".join(tok[1:])))]
        if canon == "fleet":
            return [protocol.say(self._fleet_list_msg(user, " ".join(tok[1:])))]
        if canon == "myship":
            arg = " ".join(tok[1:]).strip()
            if arg and self.fleet is not None and self.fleet.seen:
                return [protocol.say(self._ship_detail_msg(user, arg))]
            return [protocol.say(self._myship_msg(user))]
        if canon == "abandon_ship":
            return self._abandon(user, role, tok[1:])
        if canon == "resurrect_ship":
            return self._resurrect(user, role, tok[1:])
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
        # "!buy station" isn't one purchase — station types are separate events (each
        # is its own MD cue), so answer with the menu instead of "not available".
        if tok[1].lower() in ("station", "stations"):
            return [protocol.say(self._station_list_msg(user))]
        ev = self.by_key.get(tok[1].lower())
        if ev is None or not ev.enabled:
            return [protocol.say(f"@{user} '{tok[1]}' is not available.")]
        # Crisis level (tier 3). Refused BEFORE anything is charged, and phrased as
        # a locked door rather than a missing item: the event is real, it is in the
        # shop, and it becomes buyable the moment the streamer ticks the box.
        if ev.crisis and not self.rt.crisis_enabled:
            return [protocol.say(f"@{user} {ev.label or ev.buy_key} is a CRISIS-level event "
                                 f"and the streamer has not accepted crisis level. Ask nicely.")]

        if ev.ship_picker:                       # "!buy ship <name>" — priced per ship
            return self._buy_ship(user, role, ev, tok[2:])
        if ev.fleet_picker:                      # "!buy adopt <ID>" — priced per hull
            return self._buy_adopt(user, role, ev, tok[2:])

        argvals = tok[2:]
        argvals, err = self._canon_args(ev, argvals)
        if err:
            return [protocol.say(f"@{user} {err}")]
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
        karma_before = self.w.get(user).karma
        self.w.take_coins(user, cost)
        self.w.apply_purchase_karma(user, ev.karma, cost)
        self._record(ev)
        self._make_refundable(ev, user, cost, karma_before)
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
        karma_before = self.w.get(user).karma
        self.w.take_coins(user, cost)
        self.w.apply_purchase_karma(user, ev.karma, cost)
        self._record(ev)
        self._make_refundable(ev, user, cost, karma_before, label=ship.label)
        bal = self.w.get(user)
        return [
            protocol.command(ev.id, user, {"macro": ship.macro}, tier=ev.tier),
            protocol.say(f"@{user} bought a {ship.label} ({ship.size} {ship.role}) for {cost} — "
                         f"{bal.coins} coins left (karma {bal.karma}%)"),
        ]

    # -- "adopt a ship": claim one of the player's EXISTING ships ---------------
    def _buy_adopt(self, user: str, role: str, ev: StoreEvent, argvals: list[str]) -> list[dict]:
        """Price scales with the hull, because the price IS the hull's value (fleet.py
        reads it from the same ships.json that prices `!buy ship`, /1200 instead of
        /300). Nothing here is a fixed cost, so `ev.cost` is unused."""
        if self.fleet is None or not self.fleet.seen:
            return [protocol.say(f"@{user} the fleet list hasn't arrived from the game yet "
                                 f"— try again in a moment.")]
        query = " ".join(argvals)
        if not query:                            # "!buy adopt" -> what's available
            return [protocol.say(self._fleet_list_msg(user))]

        ship, suggestions = self.fleet.resolve(query)
        if ship is None:
            if suggestions:
                names = ", ".join(f"{s.idcode} ({s.label})" for s in suggestions)
                return [protocol.say(f"@{user} which one? {names} — adopt by ID code.")]
            return [protocol.say(f"@{user} no ship '{query}' in the fleet. "
                                 f"!buy adopt for the list.")]
        # ONE ship per viewer. Checked before the price and the balance so the
        # message is the useful one ("you already have X") rather than a coin
        # complaint. A wreck still counts as held — resurrect it or let it go first.
        held = self.fleet.at_limit(user)
        if held:
            what = ", ".join(self._ship_line(c, brief=True) for c in held)
            return [protocol.say(f"@{user} you already have a ship: {what}. "
                                 f"!abandon it first (one ship per viewer).")]
        owner = self.fleet.owner_of(ship.idcode)
        if owner is not None:
            who = "you already" if owner == user.lower() else f"@{owner}"
            return [protocol.say(f"@{user} {ship.idcode} is taken — {who} adopted it.")]

        cost = ship.coins
        if ROLE_RANK[role] < ROLE_RANK[ev.min_role]:
            return [protocol.say(f"@{user} {ev.label or ev.buy_key} needs {ev.min_role}.")]
        if self.w.get(user).coins < cost:
            return [protocol.say(f"@{user} not enough coins: {ship.label} costs {cost}, "
                                 f"you have {self.w.get(user).coins}.")]
        capped = self._cap_check(ev)
        if capped:
            return [protocol.say(f"@{user} {capped}")]

        # commit. The NAME is composed here, not in MD: this is the only side that
        # knows both the viewer's handle and the hull's type name, and it keeps MD
        # from ever concatenating viewer-controlled text.
        newname = self.fleet.adopted_name(user, ship)
        karma_before = self.w.get(user).karma
        self.w.take_coins(user, cost)
        self.w.apply_purchase_karma(user, ev.karma, cost)
        self._record(ev)
        self._make_refundable(ev, user, cost, karma_before,
                              label=f"{ship.label} {ship.idcode}", ref=ship.idcode)
        # Claim it now so two viewers can't buy the same ship in the same second;
        # handle_x4_failure releases it if the game says the ship is gone.
        self.fleet.adopt(user, ship.idcode)
        bal = self.w.get(user)
        return [
            # TWO args on purpose: MD cannot split a string, so the ui lua re-emits a
            # 2-arg command with the values in the event's control+value slots.
            protocol.command(ev.id, user, {"idcode": ship.idcode, "name": newname},
                             tier=ev.tier),
            protocol.say(f"@{user} adopted {ship.idcode}, a {ship.label} "
                         f"({ship.size} {ship.role}), for {cost} — it is now "
                         f"\"{newname}\" ({bal.coins} coins left)."),
        ]

    def _fleet_list_msg(self, user: str, query: str = "") -> str:
        """'!fleet' -> everything adoptable; '!fleet L' -> just that hull class.

        A big fleet overflows one chat line, and the six cheapest ships are all
        scouts — so without a filter the capitals nobody can see are the ones worth
        buying. The filter is on the LIST only, never on `!buy adopt`: there a bare
        letter would be ambiguous against an ID code or a type name."""
        if self.fleet is None or not self.fleet.seen:
            return f"@{user} the fleet list hasn't arrived from the game yet."
        query = query.strip()
        size = fleetreg.parse_size(query) if query else None
        if query and size is None:
            return (f"@{user} '{query}' isn't a hull class — use "
                    + ", ".join(f"!fleet {s}" for s in fleetreg.SIZES)
                    + " (or plain !fleet for all).")

        free = self.fleet.available(size)
        if not free:
            if size:
                have = self.fleet.sizes_available()
                menu = (", ".join(f"{k} x{v}" for k, v in have.items())
                        if have else "none right now")
                return f"@{user} no {size}-class ship is up for adoption. Available: {menu}."
            return (f"@{user} every ship in the fleet is already adopted "
                    f"({len(self.fleet.adoptions)} of {self.fleet.total}).")

        show = ", ".join(f"{s.idcode} {s.label} {s.coins}c" for s in free[:6])
        more = f" (+{len(free) - 6} more)" if len(free) > 6 else ""
        what = f"{size}-class" if size else "adoptable"
        # Point at the filter only when it would actually help.
        hint = ""
        if not size:
            have = self.fleet.sizes_available()
            if len(have) > 1:
                hint = " — filter with " + ", ".join(f"!fleet {k}" for k in have)
        # Never let a capped roster read as the whole fleet.
        cap = (f" [showing {self.fleet.sent} of {self.fleet.total} ships the player owns]"
               if self.fleet.truncated else "")
        return f"@{user} {what}, !buy adopt <ID>: {show}{more}{hint}{cap}"

    # -- giving an adopted ship back --------------------------------------------
    def _abandon(self, user: str, role: str, args: list[str]) -> list[dict]:
        """Release an adoption: the claim goes, and X4 reverts the ship's name.

        FREE and NOT refunded. Adoption buys the ship being yours for as long as you
        want it, so handing it back is not a return — and a refund would make
        adopt/abandon a no-cost way to churn the roster and re-price hulls.

        The name is not "restored" from anything the bridge remembers: MD clears it
        with <clear_object_name>, which reverts to the game's own default. Writing
        the type label back would look identical for a stock ship and would silently
        destroy the player's own name if they had renamed it before a viewer
        adopted it."""
        if self.fleet is None or not self.fleet.seen:
            return [protocol.say(f"@{user} the fleet list hasn't arrived from the game yet.")]
        is_mod = ROLE_RANK[role] >= ROLE_RANK["moderator"]
        mine = self.fleet.ships_of(user)
        query = " ".join(args).strip()

        if not query:
            # No argument is the common case: most viewers only ever hold one ship.
            if not mine:
                return [protocol.say(f"@{user} you haven't adopted a ship. (!fleet to see "
                                     f"what's available)")]
            if len(mine) > 1:
                return [protocol.say(f"@{user} which one? " + ", ".join(mine)
                                     + " — !abandon <ID>")]
            idcode = mine[0]
        else:
            # Mods may release anyone's ship; everyone else only their own, so a
            # viewer can't disown someone else's adoption.
            idcode, candidates = self.fleet.resolve_adopted(
                query, owner=None if is_mod else user)
            if idcode is None:
                if candidates:
                    return [protocol.say(f"@{user} which one? " + ", ".join(candidates))]
                held = self.fleet.owner_of(query.upper())
                if held is not None:
                    return [protocol.say(f"@{user} {query.upper()} belongs to @{held}, "
                                         f"not you.")]
                return [protocol.say(f"@{user} you have no adopted ship '{query}'. "
                                     f"(!myship to see yours)")]

        owner = self.fleet.owner_of(idcode) or user.lower()
        ship = self.fleet.ships.get(idcode)
        what = ship.label if ship is not None else "ship"
        self.fleet.release(idcode, event="abandoned")
        whose = "" if owner == user.lower() else f" (@{owner}'s)"
        return [
            # ONE arg, so this stays on the normal control-form dispatch — MD needs
            # nothing but the id code to find the ship and clear its name.
            protocol.command("abandon_ship", user, {"idcode": idcode}),
            protocol.say(f"@{user} released {idcode}{whose} — the {what} is up for "
                         f"adoption again (no refund)."),
        ]

    # -- rebuilding a destroyed ship --------------------------------------------
    def _resurrect(self, user: str, role: str, args: list[str]) -> list[dict]:
        """Rebuild a wreck. Costs the hull's adoption price x RESURRECT_MULTIPLIER.

        X4 cannot un-destroy anything, so this buys a REPLACEMENT hull of the same
        type; it gets a new id code, and the adoption is re-keyed onto it when X4
        reports back (see handle_ship_new). The claim is not released here — if the
        rebuild fails, the wreck must still be theirs to try again."""
        if self.fleet is None or not self.fleet.seen:
            return [protocol.say(f"@{user} the fleet list hasn't arrived from the game yet.")]
        wrecks = self.fleet.lost_of(user)
        query = " ".join(args).strip()
        if not query:
            if not wrecks:
                return [protocol.say(f"@{user} none of your ships are destroyed. "
                                     f"(!myship to see yours)")]
            if len(wrecks) > 1:
                menu = ", ".join(f"{r.idcode} ({FleetShip(r.idcode, r.macro, r.size).label} "
                                 f"{self.fleet.resurrect_cost(r)}c)" for r in wrecks)
                return [protocol.say(f"@{user} which wreck? {menu} — !resurrect <ID>")]
            rec = wrecks[0]
        else:
            code = query.upper()
            rec = self.fleet.lost.get(code)
            if rec is None:
                return [protocol.say(f"@{user} '{query}' isn't one of your wrecks. "
                                     f"(!myship shows your ships and wrecks)")]
            if rec.owner != user.lower() and ROLE_RANK[role] < ROLE_RANK["moderator"]:
                return [protocol.say(f"@{user} {code} is @{rec.owner}'s wreck, not yours.")]

        if not rec.macro:
            # No macro means the ship left the roster without ever being seen, so
            # there is nothing to rebuild FROM. Say so rather than charging.
            return [protocol.say(f"@{user} {rec.idcode} can't be rebuilt — the game never "
                                 f"told us what it was. !abandon {rec.idcode} to let it go.")]

        cost = self.fleet.resurrect_cost(rec)
        ship = FleetShip(rec.idcode, rec.macro, rec.size)
        if self.w.get(user).coins < cost:
            return [protocol.say(f"@{user} not enough coins: rebuilding a {ship.label} "
                                 f"costs {cost}, you have {self.w.get(user).coins}.")]

        karma_before = self.w.get(user).karma
        self.w.take_coins(user, cost)
        self._make_refundable_raw("resurrect_ship", user, cost, karma_before,
                                  label=f"{ship.label} {rec.idcode}", ref=rec.idcode)
        bal = self.w.get(user)
        return [
            # (old id code, macro) — two args, so this rides the 2-field screen event.
            # The RENAME is not sent: X4 answers with the new id code and the bridge
            # then issues an ordinary adopt_ship, reusing the tested rename path.
            protocol.command("resurrect_ship", user,
                             {"old": rec.idcode, "macro": rec.macro}),
            protocol.say(f"@{user} paid {cost} to rebuild the {ship.label} — a new hull is "
                         f"being laid down ({bal.coins} coins left)."),
        ]

    def handle_ship_down(self, msg: dict) -> list[dict]:
        """X4: an adopted ship was destroyed. Record it and tell chat."""
        if self.fleet is None:
            return []
        idcode = str(msg.get("idcode") or "")
        rec = self.fleet.mark_lost(idcode, str(msg.get("macro") or ""),
                                   str(msg.get("killer") or ""))
        if rec is None:
            return []            # not an adopted ship: nobody to tell
        ship = FleetShip(rec.idcode, rec.macro, rec.size)
        by = f" by {rec.killer}" if rec.killer else ""
        cost = self.fleet.resurrect_cost(rec)
        return [protocol.say(f"@{rec.owner} your {ship.label} ({rec.idcode}) was destroyed"
                             f"{by}! !resurrect to rebuild it for {cost} coins.")]

    def handle_ship_new(self, msg: dict) -> list[dict]:
        """X4 built the replacement: re-key the adoption and rename the new hull."""
        if self.fleet is None:
            return []
        old, new = str(msg.get("old") or ""), str(msg.get("idcode") or "")
        owner = self.fleet.rebuilt(old, new)
        if owner is None or not new:
            return []
        ship = self.fleet.ships.get(new)
        label = ship.label if ship is not None else "ship"
        return [
            protocol.command("adopt_ship", owner,
                             {"idcode": new, "name": f"{owner}'s {label}"}),
            protocol.say(f"@{owner} your {label} flies again as {new}."),
        ]

    def _myship_msg(self, user: str) -> str:
        if self.fleet is None or not self.fleet.seen:
            return f"@{user} the fleet list hasn't arrived from the game yet."
        mine = self.fleet.ships_of(user)
        if not mine:
            return (f"@{user} you haven't adopted a ship yet — !buy adopt for the list.")
        rows = [self._ship_line(code, brief=True) for code in mine]
        return (f"@{user} your ship(s): " + " | ".join(rows)
                + ("  (!myship <ID> for detail)" if len(mine) > 1 else ""))

    def _ship_detail_msg(self, user: str, query: str) -> str:
        """`!myship <ID>` — the full card for one ship, anyone's."""
        code = " ".join(query.split()).upper()
        if code not in self.fleet.ships and code not in self.fleet.lost:
            return (f"@{user} no ship '{code}' in the fleet. (!fleet for what's "
                    f"adoptable, !myship for yours)")
        owner = self.fleet.owner_of(code)
        who = f"adopted by @{owner}" if owner else "unadopted"
        return f"@{user} {self._ship_line(code)} — {who}"

    def _ship_line(self, code: str, brief: bool = False) -> str:
        """One ship's status. A wreck reports how to rebuild it instead of a
        condition, because hull/shields on a destroyed ship mean nothing."""
        wreck = self.fleet.lost.get(code)
        if wreck is not None:
            ship = FleetShip(code, wreck.macro, wreck.size)
            killed = f" by {wreck.killer}" if wreck.killer else ""
            return (f"{code} {ship.label} DESTROYED{killed} — !resurrect "
                    f"{self.fleet.resurrect_cost(wreck)}c")
        s = self.fleet.ships.get(code)
        if s is None:
            return f"{code} (not in the latest fleet list)"
        bits = [f"{code} {s.label}"]
        if not brief:
            bits.append(f"{s.size} {s.role}")
        cond = s.condition
        if cond:
            bits.append(cond)
        if s.sector:
            bits.append(f"in {s.sector}")
        return ", ".join(bits)

    def _ship_list_msg(self, user: str) -> str:
        smp = ", ".join(f"{s.key} {s.coins}c" for s in shipreg.sample(6))
        return (f"@{user} buy any of {len(shipreg.SHIPS)} ships with !buy ship <name>. "
                f"e.g. {smp}")

    # -- station + sector helpers -------------------------------------------
    def _station_list_msg(self, user: str) -> str:
        """'!buy station' -> the menu. Each station type is its own buy key."""
        rows = [e for e in self.events
                if e.arg_domain == "sector" and e.kind == "effect" and e.enabled]
        if not rows:
            return f"@{user} no stations are enabled right now."
        menu = ", ".join(f"{e.buy_key} {e.cost}c" for e in sorted(rows, key=lambda e: e.cost))
        owner = "the player" if self.rt.stations_to_player else "the Twitch Allies"
        return (f"@{user} stations are bought by name: {menu}. Add a sector to place it "
                f"there, or leave it off for the player's current sector — "
                f"e.g. !buy wharf, !buy defence argon prime. They go to {owner} by default; "
                f"end the line with 'player' or 'ally' to choose. (!sectors for help)")

    def _sector_msg(self, user: str, query: str) -> str:
        """'!sectors' -> how it works; '!sectors <text>' -> what that text resolves to."""
        n = len(sectorreg.SECTORS)
        if not query:
            return (f"@{user} {n} sectors can be targeted. Put the name after a station buy "
                    f"(!buy defence argon prime); leave it off to build where the player is. "
                    f"!sectors <name> checks a name.")
        sector, suggestions, here = sectorreg.resolve(query)
        if here:
            return f"@{user} '{query}' means the player's current sector."
        if sector is not None:
            return f"@{user} '{query}' -> {sector.label}."
        if suggestions:
            return f"@{user} '{query}' matches {len(suggestions)}: " + ", ".join(
                s.label for s in suggestions[:8])
        return f"@{user} no sector matches '{query}'."

    # -- station ownership: the streamer's default, overridable per purchase -----
    # What a viewer may type at the end of a station buy. These are the ONLY two
    # values MD is ever sent, so the words chat uses can change freely here.
    OWNER_WORDS = {"player": "player", "mine": "player", "me": "player",
                   "ally": "ally", "allies": "ally", "twitchally": "ally"}

    def _split_owner(self, argvals: list[str]) -> tuple[list[str], str]:
        """Peel a trailing owner word off a station buy.

        Returns (remaining tokens, "player"|"ally"). With no word, the streamer's
        current default applies (Runtime.stations_to_player, a dashboard switch)."""
        if argvals and argvals[-1].lower() in self.OWNER_WORDS:
            return argvals[:-1], self.OWNER_WORDS[argvals[-1].lower()]
        return argvals, ("player" if self.rt.stations_to_player else "ally")

    # -- arg canonicalisation (runs BEFORE the charge, so a typo costs nothing) --
    def _canon_args(self, ev: StoreEvent, argvals: list[str]):
        """Resolve viewer-typed args to the exact tokens MD matches on.

        MD compares arg strings literally, so "Argon" or "hop" used to miss and the
        cue quietly produced a RANDOM incident — the viewer paid for a pick they
        didn't get. Anything unresolvable is now refused up front instead."""
        if not ev.arg_domain:
            return argvals, None
        if ev.arg_domain == "sector":
            # A station buy resolves to exactly TWO values: WHERE and WHO OWNS IT.
            #   !buy wharf                    -> here,        default owner
            #   !buy wharf argon prime        -> Argon Prime, default owner
            #   !buy wharf player             -> here,        the player
            #   !buy wharf argon prime ally   -> Argon Prime, Twitch Allies
            # The owner word is taken off the END first, because a sector name is
            # MULTI-WORD ("second contact ii flashpoint") and swallows anything left.
            # Events whose owner is FIXED (a Raider den, a Kha'ak hive) declare no
            # `owner` arg and stay single-valued — nobody gets to put a Kha'ak hive
            # on the player's account.
            choosable = "owner" in ev.args
            argvals, owner = self._split_owner(argvals) if choosable else (argvals, "")
            tail = [owner] if choosable else []
            # What goes to MD is the sector's MACRO name — the only form it can turn
            # back into a sector (find_sector macro="macro.{$m}"). Empty is
            # meaningful: MD reads it as "the player's current sector".
            sector, suggestions, here = sectorreg.resolve(" ".join(argvals))
            if here:
                return [""] + tail, None
            if sector is None:
                if suggestions:
                    names = ", ".join(s.label for s in suggestions[:6])
                    return argvals, f"which sector? {names}"
                return argvals, (f"no sector called '{' '.join(argvals)}'. Leave it off for "
                                 "the player's current sector, or try !sectors <name>.")
            return [sector.macro] + tail, None
        if ev.arg_domain == "faction_stance":
            # Exactly two values, of DIFFERENT kinds: who, then what stance. Order is
            # fixed rather than sniffed, because "ally" is legal on both sides (it is
            # an alias for the twitchally faction AND a stance) and guessing would
            # turn `!buy stance ally war` into a coin flip.
            if len(argvals) < 2:
                return argvals, (f"usage: !buy {ev.buy_key} <faction> <{'|'.join(STANCE_KEYS)}> "
                                 f"— e.g. !buy {ev.buy_key} paranid war")
            target = resolve_faction(argvals[0])
            if target is None:
                return argvals, (f"'{argvals[0]}' is not a faction. Pick from: "
                                 + ", ".join(STANCE_TARGETS))
            if target == "twitchally":
                return argvals, ("that IS the Twitch faction — name who they should "
                                 "be ally/neutral/war WITH.")
            stance = resolve_stance(" ".join(argvals[1:]))
            if stance is None:
                return argvals, (f"'{' '.join(argvals[1:])}' is not a stance. Use "
                                 + ", ".join(STANCE_KEYS) + ".")
            return [target, stance], None
        argvals = argvals[:len(ev.args)] if ev.args else argvals
        out = []
        for tokn in argvals:
            if ev.arg_domain == "faction":
                key = resolve_faction(tokn)
                if key is None:
                    return argvals, (f"'{tokn}' is not a faction. Pick from: "
                                     + ", ".join(FACTION_KEYS))
            else:
                key = tokn
            out.append(key)
        if ev.distinct_args and len(set(out)) != len(out):
            return out, "pick two DIFFERENT factions (or none, for a random pair)."
        return out, None

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

    # -- refunds: X4 charged for something it then couldn't do (doc 08 §4.1) ----
    def _make_refundable_raw(self, action: str, user: str, cost: int, karma_before: int,
                             label: str = "", ref: str = "") -> None:
        """Same as _make_refundable, for commands that are not StoreEvents (a free
        top-level !command that still charges, e.g. !resurrect)."""
        self._refundable.append((self.clock(), action, user, cost, karma_before,
                                 label or action, ref))

    def _make_refundable(self, ev: StoreEvent, user: str, cost: int,
                         karma_before: int, label: str = "", ref: str = "") -> None:
        """Remember what this purchase cost, so handle_x4_failure can undo it.

        `ref` names the specific thing bought (an ID code, ...). When the cue can
        echo it back on failure, the refund is exact instead of oldest-first."""
        self._refundable.append((self.clock(), ev.id, user, cost, karma_before,
                                 label or ev.label or ev.buy_key, ref))

    def handle_x4_failure(self, msg: dict) -> list[dict]:
        """X4 says a command could not be carried out -> give the coins back.

        MD cannot name the buyer (the `by` field never reaches it — the ui lua
        forwards only the arg VALUES), so the match is on the ACTION ID against what
        the bridge itself charged. Oldest-first: commands are processed in the order
        they were sent, so the oldest outstanding charge for that action is the one
        this failure belongs to. Every purchasable event is capped and cooled down
        per action, so two of the same being in flight at once is already unusual.

        Karma is RESTORED from the pre-purchase value rather than re-derived —
        new_karma() clamps at the floor/cap, so applying its inverse would silently
        drift a viewer sitting at either end."""
        action = str(msg.get("id") or "")
        reason = str(msg.get("reason") or "").strip()
        ref = str(msg.get("ref") or "").strip()
        tail = f" ({reason})" if reason else ""
        # An adoption is recorded optimistically (the roster is up to 45s stale, so
        # only X4 can say whether the ship is still there). If X4 refuses it, the
        # claim has to come back off the ship or the viewer keeps a ghost.
        if action == "adopt_ship" and self.fleet is not None and ref:
            self.fleet.release(ref)
        self._prune_refundable()
        # Exact match first when the game named what failed; oldest-first only as the
        # fallback for cues that can't. Oldest-first is a guess, and for any action
        # acknowledged ONLY on failure it is a wrong one — successes are never
        # retired from this list, so the first failure would refund someone else's
        # earlier, perfectly good purchase.
        order = sorted(range(len(self._refundable)),
                       key=lambda i: self._refundable[i][6] != ref if ref else 0)
        for i in order:
            when, eid, user, cost, karma_before, label, rec_ref = self._refundable[i]
            if eid != action:
                continue
            if ref and rec_ref and rec_ref != ref:
                continue
            del self._refundable[i]
            self.w.give_coins(user, cost)
            self.w.set_karma(user, karma_before)
            # The event never happened, so it must not burn the cooldown or the
            # per-window cap either — drop its purchase record too.
            for j, (_t, pid, _k) in enumerate(self._purchases):
                if pid == action:
                    del self._purchases[j]
                    break
            bal = self.w.get(user)
            return [protocol.say(f"@{user} {label} could not be built{tail} — {cost} coins "
                                 f"refunded ({bal.coins} coins, karma {bal.karma}%).")]
        # Nothing to refund: a free/auto-fired event (raid allies), a charge that
        # aged out, or the economy was off when it was bought. Still tell chat.
        return [protocol.say(f"That action could not be carried out{tail}.")]

    def _prune_refundable(self) -> None:
        cutoff = self.clock() - REFUND_WINDOW
        while self._refundable and self._refundable[0][0] < cutoff:
            self._refundable.popleft()

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
