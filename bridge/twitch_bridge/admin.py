"""Dashboard admin actions: give coins, block viewers, the live testing switches.

The dashboard POSTs `{"action": ..., "user": ..., "amount"/"value": ...}`; app.py runs
`Admin.run(body)` on the event loop so wallet and runtime changes never race the
loop's own reads. One method per action, looked up in ACTIONS.
"""

from __future__ import annotations

from typing import ClassVar

# What an action needs before it can run. Checked in this order, so an action
# that needs a target also answers "economy is off" when there is no wallet.
FREE, ECONOMY, TARGET = "free", "economy", "target"


class Admin:
    def __init__(self, runtime, status, wallet=None, fleet=None) -> None:
        self.runtime = runtime
        self.status = status
        self.wallet = wallet
        self.fleet = fleet

    def publish_flags(self) -> None:
        """Push the WHOLE live-switch set to the dashboard. Status.set_flags replaces
        the dict rather than merging, so a partial push silently unsyncs the other
        checkboxes."""
        rt = self.runtime
        self.status.set_flags({"cooldowns_enabled": rt.cooldowns_enabled,
                               "caps_enabled": rt.caps_enabled,
                               "stations_to_player": rt.stations_to_player,
                               "crisis_enabled": rt.crisis_enabled})

    async def run(self, body: dict) -> dict:
        action = (body.get("action") or "").strip()
        target = (body.get("user") or "").strip().lstrip("@").lower()
        # An unknown action gets the same checks as a viewer action, then says so.
        handler, needs = self.ACTIONS.get(action, (None, TARGET))
        if needs != FREE and self.wallet is None:
            return {"ok": False, "error": "economy is off"}
        if needs == TARGET and not target:
            return {"ok": False, "error": "a viewer name is required"}
        if handler is None:
            return {"ok": False, "error": f"unknown action '{action}'"}
        try:
            return handler(self, action, body, target)
        except (ValueError, TypeError):   # int() of an amount the dashboard sent
            return {"ok": False, "error": "invalid amount"}

    # -- runtime testing toggles: work with or without the economy --------------

    def _stationowner(self, action, body, target) -> dict:
        rt = self.runtime
        rt.stations_to_player = bool(body.get("value"))
        self.publish_flags()
        self.status.note("stations now go to "
                         + ("the PLAYER" if rt.stations_to_player else "the Twitch Allies"))
        return {"ok": True, "stations_to_player": rt.stations_to_player}

    def _crisis(self, action, body, target) -> dict:
        rt = self.runtime
        rt.crisis_enabled = bool(body.get("value"))
        self.publish_flags()
        self.status.note("CRISIS LEVEL ACCEPTED — tier-3 events can be bought"
                         if rt.crisis_enabled else "crisis events are off again")
        return {"ok": True, "crisis_enabled": rt.crisis_enabled}

    def _switch(self, action, body, target) -> dict:
        """`cooldowns` and `caps`: the two testing switches the streamer flips."""
        field = "cooldowns_enabled" if action == "cooldowns" else "caps_enabled"
        setattr(self.runtime, field, bool(body.get("value")))
        self.publish_flags()
        label = "cooldowns" if action == "cooldowns" else "purchase limits"
        self.status.note(f"testing: {label} {'ON' if getattr(self.runtime, field) else 'OFF'}")
        return {"ok": True, field: getattr(self.runtime, field)}

    # -- economy reads and bulk actions -----------------------------------------

    def _list(self, action, body, target) -> dict:
        # The moderation table. Each viewer carries their adopted ship, so a
        # mod looking at "who is this person" sees what they hold in the game
        # without cross-referencing a second panel.
        rows = self.wallet.viewer_list()
        if self.fleet is not None:
            for r in rows:
                r["ships"] = [self.fleet.card(c) for c in self.fleet.ships_of(r["username"])]
        return {"ok": True, "viewers": rows}

    def _adoptions(self, action, body, target) -> dict:
        # Who holds what right now, plus the full lifecycle log. Read-only:
        # the dashboard shows it, nothing acts on it.
        fleet = self.fleet
        if fleet is None:
            return {"ok": False, "error": "the fleet is not tracked"}
        current = [dict(fleet.card(code), user=who) for code, who in fleet.adoptions.items()]
        current.sort(key=lambda r: (r["user"], r["idcode"]))
        return {"ok": True, "adoptions": current, "history": list(reversed(fleet.history))}

    def _giveall(self, action, body, target) -> dict:
        wallet = self.wallet
        amount = int(body.get("amount") or 0)
        for v in list(wallet.viewers.values()):
            wallet.give_coins(v.username, amount)
        wallet.save()
        self.status.set_econ(wallet.stats())
        self.status.note(f"admin: gave {amount} coins to all {len(wallet.viewers)} viewers")
        return {"ok": True, "count": len(wallet.viewers), "amount": amount}

    # -- one named viewer ---------------------------------------------------------

    def _give(self, action, body, target) -> dict:
        amount = int(body.get("amount") or 0)
        coins = self.wallet.give_coins(target, amount)
        self.wallet.save()
        self.status.set_econ(self.wallet.stats())
        self.status.note(f"admin: gave {amount} coins to {target} (now {coins})")
        return {"ok": True, "user": target, "coins": coins}

    def _ban(self, action, body, target) -> dict:
        """`ban` and `unban`."""
        v = self.wallet.set_banned(target, action == "ban")
        self.wallet.save()
        self.status.note(f"admin: {'blocked' if v.banned else 'unblocked'} {target}")
        return {"ok": True, "user": target, "banned": v.banned}

    ACTIONS: ClassVar[dict[str, tuple]] = {
        "stationowner": (_stationowner, FREE),
        "crisis": (_crisis, FREE),
        "cooldowns": (_switch, FREE),
        "caps": (_switch, FREE),
        "list": (_list, ECONOMY),
        "adoptions": (_adoptions, ECONOMY),
        "giveall": (_giveall, ECONOMY),
        "give": (_give, TARGET),
        "ban": (_ban, TARGET),
        "unban": (_ban, TARGET),
    }
