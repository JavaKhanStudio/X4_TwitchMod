#!/usr/bin/env python3
"""!buy purchase engine + economy chat commands (headless)."""
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from twitch_bridge import ships  # noqa: E402
from twitch_bridge.catalog import StoreEvent  # noqa: E402
from twitch_bridge.economy import Economy  # noqa: E402
from twitch_bridge.runtime import Runtime  # noqa: E402
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

# blocked viewer: buy and gift are silently ignored, balance untouched
w.get("mallory").coins = 1000
w.set_banned("mallory", True)
o = econ.handle_chat(chat("mallory", "!buy nameship Nope"))
check(o == [] and w.get("mallory").coins == 1000, "blocked viewer's !buy is ignored, no coins spent")
o = econ.handle_chat(chat("mallory", "!gift @alice 100"))
check(o == [] and w.get("mallory").coins == 1000, "blocked viewer's !gift is ignored")
w.set_banned("mallory", False)
o = econ.handle_chat(chat("mallory", "!buy nameship Yes"))
check(o and o[0]["t"] == "cmd", "unblocked viewer can buy again")

# command aliases resolve to one canonical command
check(econ._canon.get("!bal") == "balance" and econ._canon.get("!coins") == "balance",
      "!bal / !coins alias !balance")
check(econ._canon.get("!give") == "gift" and econ._canon.get("!purchase") == "buy",
      "!give -> gift, !purchase -> buy")
o = econ.handle_chat(chat("alice", "!bal"))
check(o and o[0]["t"] == "say" and "balance" in o[0]["msg"], "!bal works end-to-end like !balance")
w.get("alice").coins = 500   # top up so the purchase is affordable
o = econ.handle_chat(chat("alice", "!purchase nameship Foo"))
check(o and o[0]["t"] == "cmd" and o[0]["id"] == "name_ship", "!purchase works like !buy")

# testing mode: cooldowns disabled -> a cooldown event is re-buyable immediately.
# Fresh settings: the shared `s` had its bad-karma cap tightened above, which would
# otherwise block the 2nd bad buy for a different reason than the cooldown.
rt = Runtime(cooldowns_enabled=False)
s2 = EconomySettings(min_purchase_price=10)
w2 = Wallet(tempfile.mktemp(suffix=".json"), s2, clock=lambda: 0)
econ2 = Economy(w2, cat, clock=clk, runtime=rt)
w2.get("zoe").coins = 10000
a = econ2.handle_chat(chat("zoe", "!buy pirate"))
b = econ2.handle_chat(chat("zoe", "!buy pirate"))   # no clock advance, cooldown is 60s
check(a[0]["t"] == "cmd" and b[0]["t"] == "cmd", "cooldowns disabled: cooldown event re-buys immediately")
rt.cooldowns_enabled = True
o = econ2.handle_chat(chat("zoe", "!buy pirate"))
check("cooldown" in o[0]["msg"], "re-enabling cooldowns blocks the next re-buy")

# testing mode: caps disabled -> per-window caps (event + karma) stop blocking.
# cooldowns also off here so the discriminator is the CAP, not the cooldown.
rt2 = Runtime(cooldowns_enabled=False, caps_enabled=False)
s3 = EconomySettings(min_purchase_price=10)
w3 = Wallet(tempfile.mktemp(suffix=".json"), s3, clock=lambda: 0)
econ3 = Economy(w3, cat, clock=clk, runtime=rt2)   # pirate: bad, event_cap=2
w3.get("kai").coins = 10000
outs = [econ3.handle_chat(chat("kai", "!buy pirate")) for _ in range(4)]
check(all(o[0]["t"] == "cmd" for o in outs), "caps disabled: repeated bad buys never hit a window cap")
rt2.caps_enabled = True   # re-enable -> event_cap (2) now blocks
o = econ3.handle_chat(chat("kai", "!buy pirate"))
check("maxed this window" in o[0]["msg"] or "too many" in o[0]["msg"],
      "re-enabling caps blocks the over-cap buy again")

# --- "buy any ship" (ship_picker) -----------------------------------------
ship_ev = StoreEvent(id="gift_ship", buy_key="ship", nicknames=["ships"],
                     ship_picker=True, karma="good", tier=1, enabled=True)
w4 = Wallet(tempfile.mktemp(suffix=".json"), EconomySettings(min_purchase_price=10), clock=lambda: 0)
econ4 = Economy(w4, [ship_ev], clock=clk)
w4.get("rich").coins = 500000

o = econ4.handle_chat(chat("rich", "!buy ship katana"))
kc = ships.SHIPS["katana"].coins
check(o[0]["t"] == "cmd" and o[0]["id"] == "gift_ship", "buy ship -> cmd gift_ship")
check(o[0]["args"] == {"macro": ships.SHIPS["katana"].macro}, "cmd carries ONLY the macro arg")
check(w4.get("rich").coins == 500000 - kc, f"charged the ship's scaled price ({kc})")

o = econ4.handle_chat(chat("rich", "!buy ship"))          # no name -> the list
check(o[0]["t"] == "say" and "!buy ship" in o[0]["msg"], "'!buy ship' lists ships")
o = econ4.handle_chat(chat("rich", "!buy ship zzzznope"))  # miss
check("no ship" in o[0]["msg"].lower(), "unknown ship is reported")
o = econ4.handle_chat(chat("rich", "!buy ship ra"))        # ambiguous -> suggest
check("did you mean" in o[0]["msg"].lower(), "ambiguous ship name -> suggestions")

w4.get("poor").coins = 10
o = econ4.handle_chat(chat("poor", "!buy ship katana"))
check("not enough" in o[0]["msg"], "too-poor viewer refused a ship (no cmd)")
check(all(x["t"] != "cmd" for x in o), "no ship spawned when unaffordable")

print("\n" + ("ALL PASS" if ok else "SOME FAILED"))
sys.exit(0 if ok else 1)
