#!/usr/bin/env python3
"""!buy purchase engine + economy chat commands (headless)."""
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from twitch_bridge.catalog import StoreEvent  # noqa: E402
from twitch_bridge.economy import Economy  # noqa: E402
from twitch_bridge.wallet import EconomySettings, Wallet  # noqa: E402

ok = True


def check(c, m):
    global ok
    print(("PASS: " if c else "FAIL: ") + m)
    ok = ok and c


class Clock:
    def __init__(self): self.t = 0.0
    def __call__(self): return self.t


def chat(user, msg, badges=None):
    return {"t": "chat", "user": user, "msg": msg, "badges": badges or []}


def kinds(outs):
    return [o["t"] for o in outs]


clk = Clock()
s = EconomySettings(min_purchase_price=10)
# a controlled catalog
cat = [
    StoreEvent(id="name_ship", buy_key="nameship", cost=100, karma="neutral", tier=0,
               args=["name"], label="Name a ship", enabled=True),
    StoreEvent(id="pirate", buy_key="pirate", cost=200, karma="bad", tier=1,
               cooldown=60, event_cap=2, label="Pirate", enabled=True),
    StoreEvent(id="ware", buy_key="ware", cost_per_unit=2, unit="qty", karma="good", tier=1,
               args=["ware", "qty"], label="Ware", enabled=True),
    StoreEvent(id="khaak", buy_key="khaak", cost=900, karma="bad", tier=2,
               label="Khaak", enabled=False),  # disabled
]
w = Wallet(tempfile.mktemp(suffix=".json"), s, clock=lambda: 0)
econ = Economy(w, cat, clock=clk)

# balance
o = econ.handle_chat(chat("Alice", "!balance"))
check(o and o[0]["t"] == "say" and "150" in o[0]["msg"], "!balance reports coins")

# successful buy: cmd + say, coins debited, karma moved
w.get("alice").coins = 500
o = econ.handle_chat(chat("alice", "!buy nameship Serenity"))
check(kinds(o) == ["cmd", "say"], "buy emits a vetted cmd + a confirmation")
check(o[0]["id"] == "name_ship" and o[0]["args"] == {"name": "Serenity"} and o[0]["tier"] == 0,
      "cmd carries id, parsed args, tier")
check(w.get("alice").coins == 400, "coins debited by cost")

# not enough coins
w.get("bob").coins = 50
o = econ.handle_chat(chat("bob", "!buy nameship Foo"))
check(kinds(o) == ["say"] and "not enough" in o[0]["msg"], "poor viewer is refused")

# disabled event not buyable
o = econ.handle_chat(chat("alice", "!buy khaak"))
check("not available" in o[0]["msg"], "disabled event refused")

# variable price scales with qty (2/unit * 30 = 60)
w.get("alice").coins = 1000
o = econ.handle_chat(chat("alice", "!buy ware energycells 30"))
check(o[0]["t"] == "cmd" and w.get("alice").coins == 940, "variable event price scales with qty")

# bad-purchase lowers karma
k0 = w.get("alice").karma
econ.handle_chat(chat("alice", "!buy pirate"))
check(w.get("alice").karma < k0, "buying a bad event lowers karma")

# per-event cooldown
o = econ.handle_chat(chat("alice", "!buy pirate"))
check("cooldown" in o[0]["msg"], "second pirate within cooldown is blocked")

# karma-type cap: 1 pirate (bad) already recorded. Advance past the 60s cooldown but
# stay INSIDE the 900s cap window, set the bad cap to 1 -> next bad event is capped.
clk.t += 65
s.max_bad_per_interval = 1
o = econ.handle_chat(chat("alice", "!buy pirate"))
check("too many" in o[0]["msg"], "karma-type cap blocks excess bad events")

# gifting moves coins
w.get("alice").coins = 100
o = econ.handle_chat(chat("alice", "!gift @carol 40"))
check(w.get("alice").coins == 60 and w.get("carol").coins == s.starting_balance + 40,
      "!gift transfers coins")

# admin gated by role; broadcaster can givecoins
o = econ.handle_chat(chat("streamer", "!givecoins @dan 1000", badges=["broadcaster"]))
check(w.get("dan").coins >= 1000, "broadcaster !givecoins works")
o = econ.handle_chat(chat("rando", "!givecoins @dan 1000"))
check(o == [], "non-mod admin command ignored")

print("\n" + ("ALL PASS" if ok else "SOME FAILED"))
sys.exit(0 if ok else 1)
