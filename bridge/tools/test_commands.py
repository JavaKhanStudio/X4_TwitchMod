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

# event triggers. ONE event may fan out to SEVERAL commands (a raid both summons
# reinforcements and makes Boso Ta call), so look the action up by id instead of
# asserting the batch size — otherwise every new event reaction breaks these.
def by_id(out, action):
    hits = [c for c in out if c["id"] == action]
    return hits[0] if len(hits) == 1 else None


out = eng.process(protocol.raid("streamer", 250))
cmd = by_id(out, "reinforcements")
check(cmd is not None and cmd["args"]["viewers"] == 250,
      "raid -> reinforcements with viewers arg")

# redeem matches reward title only
check(eng.process(protocol.redeem("carol", "Wrong Reward")) == [], "redeem wrong title ignored")
out = eng.process(protocol.redeem("carol", "Pirate Attack"))
check(len(out) == 1 and out[0]["id"] == "pirate_attack", "redeem matching title -> cmd")

out = eng.process(protocol.cheer("dave", 500))
cmd = by_id(out, "cheer_boost")
check(cmd is not None and cmd["args"]["bits"] == 500, "cheer -> cheer_boost with bits")

# Boso Ta call. fixed_args must REPLACE the event's own args, not merge with them:
# the ui lua ';'-joins arg values into the single string MD receives, so a leaked
# {"viewers": 250} would arrive as "excited;250" and match no mood in MD.
clk.advance(100)   # clear boso_raid's own cooldown, armed by the raid above
cmd = by_id(eng.process(protocol.raid("streamer2", 250)), "boso_call")
check(cmd is not None and cmd["argv"] == ["excited"], "raid -> boso_call, mood only (no viewers)")
cmd = by_id(eng.process(protocol.sub("frank", "1000", 3)), "boso_call")
check(cmd is not None and cmd["argv"] == ["praise"], "sub -> boso_call mood=praise")

# chat trigger: a typed mood wins; no token at all sends nothing and MD cycles.
clk.advance(100)
out = eng.process(protocol.chat("mod", "!boso angry", badges=["moderator"]))
check(len(out) == 1 and out[0]["id"] == "boso_call" and out[0]["argv"] == ["angry"],
      "!boso angry -> boso_call mood=angry")
clk.advance(100)
out = eng.process(protocol.chat("mod", "!boso", badges=["moderator"]))
check(len(out) == 1 and out[0]["argv"] == [], "!boso with no mood -> empty argv")
clk.advance(100)
out = eng.process(protocol.chat("mod", "!boso random", badges=["moderator"]))
check(len(out) == 1 and out[0]["argv"] == ["random"], "!boso random -> boso_call mood=random")

# Role floor is SUBSCRIBER, which by ROLE_RANK ordering admits vip and moderator too.
# Walk the whole boundary: the one role below the floor must be refused, and each
# role at or above it accepted. A floor set one notch wrong is invisible otherwise —
# it just silently opens the command to everyone or closes it to the subs it is for.
clk.advance(100)
check(eng.process(protocol.chat("lurker", "!boso", badges=[])) == [],
      "!boso denied for a plain viewer")
for role in ("subscriber", "vip", "moderator", "broadcaster"):
    clk.advance(100)   # clear both the global and the per-user cooldown
    out = eng.process(protocol.chat("user_" + role, "!boso", badges=[role]))
    check(len(out) == 1 and out[0]["id"] == "boso_call", f"!boso allowed for {role}")

# Per-user cooldown: one sub cannot hold the line. The channel-wide 5s has already
# lapsed here, so a block can only come from the per-user minute.
clk.advance(100)
check(len(eng.process(protocol.chat("eager", "!boso", badges=["subscriber"]))) == 1,
      "!boso: first call from a sub goes through")
clk.advance(10)
check(eng.process(protocol.chat("eager", "!boso", badges=["subscriber"])) == [],
      "!boso: same sub blocked by the per-user cooldown")
check(len(eng.process(protocol.chat("other", "!boso", badges=["vip"]))) == 1,
      "!boso: a different viewer is not blocked by someone else's cooldown")

# Crisis gate: !armada is mod-only AND tier-3, so being a moderator is not enough.
# Checked on the real STARTER catalog, because the point is that the shipped command
# carries crisis=True — a fixture would pass while the live one nuked the save.
clk.advance(100)
check(eng.process(protocol.chat("mod", "!armada", badges=["moderator"])) == [],
      "!armada does nothing while crisis level is not accepted")
eng.rt.crisis_enabled = True
clk.advance(100)
out = eng.process(protocol.chat("mod", "!armada", badges=["moderator"]))
check(len(out) == 1 and out[0]["id"] == "xenon_armada",
      "!armada fires once crisis level is accepted")
clk.advance(100)
check(eng.process(protocol.chat("viewer", "!armada", badges=[])) == [],
      "!armada is still moderator-only with crisis level accepted")
eng.rt.crisis_enabled = False
clk.advance(100)
check(eng.process(protocol.chat("mod", "!armada", badges=["moderator"])) == [],
      "turning crisis level back off closes !armada again")

# every mood the bridge advertises must exist in the MD cue's parallel $moods list
import re  # noqa: E402

from twitch_bridge.catalog import BOSO_MOODS  # noqa: E402

md_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))), "extensions", "twitch_integration", "md",
    "twitch_integration.xml")
with open(md_path, encoding="utf-8") as fh:
    md = fh.read()
m = re.search(r'name="\$moods" exact="\[([^\]]*)\]"', md)
md_moods = tuple(re.findall(r"'(\w+)'", m.group(1))) if m else ()
check(md_moods == BOSO_MOODS, f"BOSO_MOODS matches MD $moods ({md_moods})")

# The no-argument !boso must CYCLE, not randomise: that is what makes it a usable
# demo (N presses show N different moods). Guard the mechanism, since a stray
# `.random` here would silently turn the test command back into a coin flip.
check("static.$BosoCycle" in md, "MD keeps a mood cycle counter in static.$BosoCycle")
check(".random" not in md.split("$moods.indexof")[1].split("$line")[0],
      "no-mood path advances the cycle instead of randomising")

# A call that lands while the player is busy must WAIT, not refund. Guard the two
# halves of that: the dispatcher no longer refuses on player state, and the wait
# cue polls for it. Re-adding a player-state check to the dispatch path would make
# calls vanish again, which is exactly the bug this replaced.
boso = md.split('name="Twitch_OnBosoCall"')[1].split("</cue>")[0]
check("Twitch_Fail" not in boso,
      "boso_call dispatch does not refund (the wait cue owns the outcome)")
pump = md.split('name="Twitch_BosoPump"')[1].split("</cue>")[0]
check("isinconversation" in pump and "isinfullscreenmenu" in pump,
      "Twitch_BosoPump re-checks player availability before playing")
check("$PersistentCharacters.$BosoTa" in pump,
      "Twitch_BosoPump also waits for Boso Ta to exist")
# The wait MUST be a signalled loop, not a polled condition: a non-event condition
# inside an instantiated cue's subtree is rejected at load and the call vanishes.
check("<event_cue_signalled/>" in pump, "Twitch_BosoPump waits on an event, not a poll")
check("signal_cue cue=\"Twitch_BosoPump\"" in pump,
      "Twitch_BosoPump re-signals itself while work remains")
# Deadline, not a retry counter: N queued calls mean N loops all incrementing the
# same head job, so a counter would expire ~N times too early.
check("$expires" in md and "player.age" in pump,
      "give-up is a wall-clock deadline, not a pass count")

# `!boso random` draws from the generated pool. Three things have to line up: the
# word is NOT a mood (or the cycle would swallow it), MD tests for it, and the
# generated pool file exists with the library MD calls.
from twitch_bridge.catalog import BOSO_RANDOM  # noqa: E402

check(BOSO_RANDOM not in BOSO_MOODS, "'random' is kept out of BOSO_MOODS")
check(f"$mood == '{BOSO_RANDOM}'" in md and "md.Twitch_BosoLines.RandomLine" in md,
      "MD routes the random word to the generated line pool")
pool_path = os.path.join(os.path.dirname(md_path), "twitch_boso_lines.xml")
pool = ""
if os.path.exists(pool_path):
    with open(pool_path, encoding="utf-8") as f:
        pool = f.read()
check('<library name="RandomLine"' in pool,
      "twitch_boso_lines.xml provides RandomLine")
# Every id in the pool must be a plausible page-10201 line, and there must be a lot
# of them — a truncated regeneration would still parse but would quietly shrink the
# variety this command exists for.
ids = re.findall(r"\b\d{6,9}\b", pool)
check(len(ids) > 1000, f"pool carries the full line set ({len(ids)} ids)")

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
