#!/usr/bin/env python3
"""Wallet + karma governor unit tests (headless)."""
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from twitch_bridge.wallet import EconomySettings, Wallet, new_karma  # noqa: E402

ok = True


def check(c, m):
    global ok
    print(("PASS: " if c else "FAIL: ") + m)
    ok = ok and c


# fake clock we control
class Clock:
    def __init__(self): self.t = 1000.0
    def __call__(self): return self.t


clk = Clock()
s = EconomySettings()
w = Wallet(tempfile.mktemp(suffix=".json"), s, clock=clk)

# starting balance / karma
v = w.get("Alice")
check(v.coins == s.starting_balance and v.karma == 100, "new viewer gets starting balance + karma")
check(w.get("ALICE") is v, "username is case-insensitive")

# coins
check(w.take_coins("alice", 100) and v.coins == 50, "take_coins debits when affordable")
check(not w.take_coins("alice", 999), "take_coins refuses when too poor")
w.give_coins("alice", -10**9)   # large negative from any balance -> clamp at 0
check(v.coins == 0, "give_coins never goes below 0")

# award loop: active viewer at 100 karma gets base coin_amount
w2 = Wallet(tempfile.mktemp(suffix=".json"), s, clock=clk)
a = w2.note_activity("bob")            # last_seen = now
before = a.coins
w2.award()
check(a.coins == before + s.coin_amount, "active 100-karma viewer earns base coin_amount")

# karma multiplier: 140 karma earns 1.4x
a.karma = 140
a.coins = 0
w2.award()
import math
check(a.coins == math.ceil(s.coin_amount * 1.4), "karma scales income (140 -> 1.4x)")

# activity decay: idle past no_coins_after earns nothing
clk.t += s.no_coins_after + 1
a.coins = 0
w2.award()
check(a.coins == 0, "idle past no_coins_after earns nothing")

# half coins in the decay band
clk.t = a.last_seen + s.half_coins_after + 1
a.karma = 100; a.coins = 0
w2.award()
check(a.coins == math.ceil(s.coin_amount * 0.5), "idle in decay band earns half")

# sub perk
sub = w2.note_activity("sue", sub=True)
sub.karma = 100; sub.coins = 0
clk.t = sub.last_seen
w2.award()
check(sub.coins == math.ceil((s.coin_amount + s.sub_bonus) * s.sub_mult), "sub bonus + multiplier")

# karma governor: good raises, bad lowers, doom tanks, clamped
check(new_karma(100, "good", 240, s) == min(s.karma_cap, 100 + round(240 / s.karma_good_div)), "good purchase raises karma")
check(new_karma(100, "bad", 240, s) == 100 - round(240 / s.karma_bad_div), "bad purchase lowers karma")
check(new_karma(15, "doom", 6500, s) == s.karma_floor, "doom tanks karma to the floor (clamped)")
check(new_karma(135, "good", 9999, s) == s.karma_cap, "karma never exceeds the cap")

# persistence round-trip (atomic)
path = tempfile.mktemp(suffix=".json")
w3 = Wallet(path, s, clock=clk)
w3.get("zed").coins = 777
w3.get("zed").karma = 123
w3.coins_awarded_total = 42
w3.save()
w4 = Wallet(path, s, clock=clk)
check(w4.get("zed").coins == 777 and w4.get("zed").karma == 123, "viewers persist across save/load")
check(w4.coins_awarded_total == 42, "totals persist")
check(Path(path).exists(), "save wrote the file atomically")

print("\n" + ("ALL PASS" if ok else "SOME FAILED"))
sys.exit(0 if ok else 1)
