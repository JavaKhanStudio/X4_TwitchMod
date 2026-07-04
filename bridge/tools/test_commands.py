"""Unit tests for the command/policy engine. Pure stdlib, deterministic clock.

    python tools/test_commands.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from twitch_bridge import protocol
from twitch_bridge.catalog import STARTER
from twitch_bridge.commands import CommandEngine, role_of

fail = 0
def check(cond, label):
    global fail
    print(f"{'PASS' if cond else 'FAIL'}: {label}")
    fail += 0 if cond else 1


class Clock:
    def __init__(self): self.t = 1000.0
    def __call__(self): return self.t
    def advance(self, dt): self.t += dt


clk = Clock()
eng = CommandEngine(STARTER, clock=clk)

# role derivation
check(role_of(["subscriber"]) == "subscriber", "role_of subscriber")
check(role_of(["moderator", "subscriber"]) == "moderator", "role_of picks highest")
check(role_of([]) == "everyone", "role_of default everyone")

# !ping allowed for everyone -> one cmd with action 'ping'
out = eng.process(protocol.chat("alice", "!ping"))
check(len(out) == 1 and out[0]["t"] == "cmd" and out[0]["id"] == "ping", "!ping -> cmd ping")
check(out[0]["by"] == "alice", "cmd carries user")

# immediate re-ping -> cooldown (5s) blocks it
check(eng.process(protocol.chat("alice", "!ping")) == [], "!ping cooldown blocks")
clk.advance(6)
check(len(eng.process(protocol.chat("bob", "!ping"))) == 1, "!ping ok after cooldown")

# !spawn requires moderator: everyone denied, moderator allowed with arg
check(eng.process(protocol.chat("alice", "!spawn fighter")) == [], "!spawn denied for everyone")
out = eng.process(protocol.chat("mod", "!spawn fighter", badges=["moderator"]))
check(len(out) == 1 and out[0]["id"] == "spawn", "!spawn allowed for moderator")
check(out[0]["args"].get("ship") == "fighter", "!spawn parsed ship arg")

# !rank is free for everyone and dispatches action 'rank' (MD reads the fight stats)
out = eng.process(protocol.chat("viewer", "!rank"))
check(len(out) == 1 and out[0]["id"] == "rank" and out[0]["by"] == "viewer", "!rank -> cmd rank")
# the !kills alias hits the same action, and shares !rank's cooldown (same id)
check(eng.process(protocol.chat("viewer", "!kills")) == [], "!kills shares !rank cooldown")
clk.advance(11)
out = eng.process(protocol.chat("viewer", "!kills"))
check(len(out) == 1 and out[0]["id"] == "rank", "!kills -> cmd rank after cooldown")

# !traderank / !econ dispatch the trade-rank action
out = eng.process(protocol.chat("viewer", "!traderank"))
check(len(out) == 1 and out[0]["id"] == "traderank", "!traderank -> cmd traderank")
check(eng.process(protocol.chat("viewer", "!econ")) == [], "!econ shares !traderank cooldown")

# unknown command and plain chat -> nothing
check(eng.process(protocol.chat("alice", "!nope")) == [], "unknown command ignored")
check(eng.process(protocol.chat("alice", "hello world")) == [], "plain chat ignored")

# event triggers
out = eng.process(protocol.raid("streamer", 250))
check(len(out) == 1 and out[0]["id"] == "reinforcements" and out[0]["args"]["viewers"] == 250,
      "raid -> reinforcements with viewers arg")

# redeem matches reward title only
check(eng.process(protocol.redeem("carol", "Wrong Reward")) == [], "redeem wrong title ignored")
out = eng.process(protocol.redeem("carol", "Pirate Attack"))
check(len(out) == 1 and out[0]["id"] == "pirate_attack", "redeem matching title -> cmd")

out = eng.process(protocol.cheer("dave", 500))
check(len(out) == 1 and out[0]["args"]["bits"] == 500, "cheer -> cheer_boost with bits")

# testing mode: cooldowns disabled -> the same command fires back-to-back
from twitch_bridge.runtime import Runtime  # noqa: E402
rt = Runtime(cooldowns_enabled=False)
eng2 = CommandEngine(STARTER, clock=clk, runtime=rt)
a = eng2.process(protocol.chat("eve", "!ping"))
b = eng2.process(protocol.chat("eve", "!ping"))   # no clock advance
check(len(a) == 1 and len(b) == 1, "cooldowns disabled: !ping fires with no wait")
rt.cooldowns_enabled = True
eng2.process(protocol.chat("eve", "!ping"))         # arm the cooldown
check(eng2.process(protocol.chat("eve", "!ping")) == [], "re-enabling cooldowns blocks again")

print(f"\n{'ALL PASS' if fail == 0 else str(fail) + ' FAILURES'}")
sys.exit(1 if fail else 0)
