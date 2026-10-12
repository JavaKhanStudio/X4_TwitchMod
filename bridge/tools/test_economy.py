#!/usr/bin/env python3
"""!buy purchase engine + economy chat commands (headless)."""
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from twitch_bridge import protocol, ships  # noqa: E402
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
    StoreEvent(id="armada", buy_key="armada", cost=300, karma="doom", tier=3,
               label="Armada", enabled=True),  # tier 3 => needs crisis consent
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

# crisis level (tier 3): enabled, priced, in the shop — and refused until the
# streamer accepts it. The refusal must cost nothing and must not be phrased as
# "unavailable", since the event is real and one click away.
w.get("alice").coins = 5000
o = econ.handle_chat(chat("alice", "!buy armada"))
check(kinds(o) == ["say"] and "CRISIS" in o[0]["msg"], "crisis event refused while the switch is off")
check(w.get("alice").coins == 5000, "a refused crisis buy charges nothing")
check("armada" not in econ.handle_chat(chat("alice", "!shop"))[0]["msg"],
      "crisis events stay out of the !shop teaser while off")
econ.rt.crisis_enabled = True
o = econ.handle_chat(chat("alice", "!buy armada"))
check(kinds(o) == ["cmd", "say"] and o[0]["id"] == "armada",
      "crisis event buyable once the streamer accepts crisis level")
check(w.get("alice").coins == 4700, "and it charges normally")
econ.rt.crisis_enabled = False
check("CRISIS" in econ.handle_chat(chat("alice", "!buy armada"))[0]["msg"],
      "turning the switch back off closes the door again")

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

# --- faction args (arg_domain) --------------------------------------------
# MD matches faction names as literal lowercase strings, so the bridge has to
# canonicalise here; an unresolvable name must be REFUSED, not silently turned
# into a random incident the viewer paid for.
inc = StoreEvent(id="faction_incident", buy_key="incident", cost=300, tier=1,
                 args=["faction1", "faction2"], arg_domain="faction",
                 distinct_args=True, label="Incident", enabled=True)
w5 = Wallet(tempfile.mktemp(suffix=".json"), EconomySettings(min_purchase_price=10), clock=lambda: 0)
econ5 = Economy(w5, [inc], clock=clk)
w5.get("dip").coins = 10000

o = econ5.handle_chat(chat("dip", "!buy incident argon paranid"))
check(o[0]["t"] == "cmd" and o[0]["args"] == {"faction1": "argon", "faction2": "paranid"},
      "two named factions reach the cmd in order")
check(o[0]["argv"] == ["argon", "paranid"], "argv mirrors args in declared order")

o = econ5.handle_chat(chat("dip", "!buy incident HOP Zyarth"))
check(o[0]["t"] == "cmd" and o[0]["argv"] == ["holyorder", "split"],
      "case + short names resolve to the keys MD matches on")

o = econ5.handle_chat(chat("dip", "!buy incident teladi"))
check(o[0]["t"] == "cmd" and o[0]["argv"] == ["teladi"], "one named faction is allowed")

o = econ5.handle_chat(chat("dip", "!buy incident"))
check(o[0]["t"] == "cmd" and o[0]["argv"] == [], "no args -> cmd with an empty payload (random pair)")

before = w5.get("dip").coins
o = econ5.handle_chat(chat("dip", "!buy incident xenon argon"))
check(kinds(o) == ["say"] and "not a faction" in o[0]["msg"], "unknown faction is refused")
check(w5.get("dip").coins == before, "refused buy costs nothing")

o = econ5.handle_chat(chat("dip", "!buy incident argon ARGON"))
check(kinds(o) == ["say"] and "DIFFERENT" in o[0]["msg"], "the same faction twice is refused")

# The Twitch faction is a legal incident target like any other (its relations are
# deliberately unlocked, unlike twitchfoe's).
o = econ5.handle_chat(chat("dip", "!buy incident twitch paranid"))
check(o[0]["t"] == "cmd" and o[0]["argv"] == ["twitchally", "paranid"],
      "twitchally is pickable in an incident, by alias")

# --- Twitch faction stance (arg_domain="faction_stance") -------------------
# Two args of DIFFERENT kinds. Order is fixed rather than sniffed: "ally" is both a
# faction alias and a stance, so guessing would make `!buy stance ally war` a coin flip.
st = StoreEvent(id="faction_stance", buy_key="stance", cost=900, tier=2,
                args=["faction", "stance"], arg_domain="faction_stance",
                label="Stance", enabled=True)
w6 = Wallet(tempfile.mktemp(suffix=".json"), EconomySettings(min_purchase_price=10), clock=lambda: 0)
econ6 = Economy(w6, [st], clock=clk)
w6.get("dip").coins = 100000

for line, want in [("!buy stance paranid war", ["paranid", "war"]),
                   ("!buy stance HOP ally", ["holyorder", "ally"]),
                   ("!buy stance teladi peace", ["teladi", "ally"]),
                   ("!buy stance zya hostile", ["split", "war"]),
                   ("!buy stance argon ceasefire", ["argon", "neutral"])]:
    o = econ6.handle_chat(chat("dip", line))
    check(o[0]["t"] == "cmd" and o[0]["argv"] == want, f"{line!r} -> {want}")

before = w6.get("dip").coins
o = econ6.handle_chat(chat("dip", "!buy stance twitchally war"))
check(kinds(o) == ["say"] and "that IS the Twitch faction" in o[0]["msg"],
      "the Twitch faction can't be its own stance target")
o = econ6.handle_chat(chat("dip", "!buy stance paranid banana"))
check(kinds(o) == ["say"] and "not a stance" in o[0]["msg"], "an unknown stance is refused")
o = econ6.handle_chat(chat("dip", "!buy stance xenon war"))
check(kinds(o) == ["say"] and "not a faction" in o[0]["msg"], "an unknown faction is refused")
o = econ6.handle_chat(chat("dip", "!buy stance paranid"))
check(kinds(o) == ["say"] and "usage" in o[0]["msg"], "a missing stance gets usage help")
check(w6.get("dip").coins == before, "none of the rejected stance buys cost a coin")

# --- station builds: sector arg (arg_domain="sector") ----------------------
# The sector name is MULTI-WORD and MD can't parse strings, so the bridge must
# collapse the whole tail of the line into ONE value and send the sector's MACRO.
# Omitting it must send an EMPTY value — that is how MD is told "player.sector".
wharf = StoreEvent(id="station_wharf", buy_key="wharf", cost=9000, tier=1, karma="good",
                   args=["sector"], arg_domain="sector", label="Wharf", enabled=True)
w6 = Wallet(tempfile.mktemp(suffix=".json"), EconomySettings(min_purchase_price=10), clock=lambda: 0)
econ6 = Economy(w6, [wharf], clock=clk)
w6.get("architect").coins = 100000

o = econ6.handle_chat(chat("architect", "!buy wharf argon prime"))
check(o[0]["t"] == "cmd" and o[0]["id"] == "station_wharf", "buy wharf -> cmd station_wharf")
check(o[0]["argv"] == ["Cluster_14_Sector001_macro"],
      f"multi-word sector collapses to ONE macro arg (got {o[0]['argv']})")

o = econ6.handle_chat(chat("architect", "!buy wharf"))
check(o[0]["t"] == "cmd" and o[0]["argv"] == [""],
      f"no sector -> empty arg, MD reads it as player.sector (got {o[0]['argv']})")
o = econ6.handle_chat(chat("architect", "!buy wharf here"))
check(o[0]["t"] == "cmd" and o[0]["argv"] == [""], "'here' also means the player's sector")

before = w6.get("architect").coins
o = econ6.handle_chat(chat("architect", "!buy wharf grand exchange"))
check(kinds(o) == ["say"] and "which sector" in o[0]["msg"].lower(),
      "an ambiguous sector asks which one")
check(w6.get("architect").coins == before, "ambiguous sector costs nothing")
o = econ6.handle_chat(chat("architect", "!buy wharf zzzznope"))
check(kinds(o) == ["say"] and "no sector" in o[0]["msg"].lower(), "unknown sector is refused")
check(w6.get("architect").coins == before, "refused sector costs nothing")

# "!buy station" is a menu, not a purchase (each type is its own event/MD cue)
o = econ6.handle_chat(chat("architect", "!buy station"))
check(kinds(o) == ["say"] and "wharf" in o[0]["msg"], "'!buy station' lists the station types")

# !sectors — the lookup helper
o = econ6.handle_chat(chat("architect", "!sectors"))
check(kinds(o) == ["say"] and "sectors" in o[0]["msg"].lower(), "!sectors explains itself")
o = econ6.handle_chat(chat("architect", "!sectors argon prime"))
check("Argon Prime" in o[0]["msg"], "!sectors <name> resolves a name")
o = econ6.handle_chat(chat("architect", "!map grand"))
check("Grand Exchange" in o[0]["msg"], "!map is an alias and lists near misses")

# --- station ownership: streamer default + per-purchase override -----------
# Two values now reach MD: the sector macro and the owner word. The owner is taken
# off the END of the line, because a sector name is multi-word and would swallow it.
own = StoreEvent(id="station_wharf", buy_key="wharf", cost=100, tier=1, karma="good",
                 args=["sector", "owner"], arg_domain="sector", label="Wharf", enabled=True)
fixed = StoreEvent(id="station_khaakhive", buy_key="hive", cost=100, tier=3, karma="doom",
                   args=["sector"], arg_domain="sector", label="Hive", enabled=True)
rt3 = Runtime()
# The hive is tier 3, so these owner-parsing checks would otherwise all be answered
# by the crisis gate instead of by the parser they are actually testing.
rt3.crisis_enabled = True
w8 = Wallet(tempfile.mktemp(suffix=".json"), EconomySettings(min_purchase_price=10), clock=lambda: 0)
econ8 = Economy(w8, [own, fixed], clock=clk, runtime=rt3)
w8.get("vi").coins = 1000000

check(rt3.stations_to_player is False, "the shipped default is: chat builds for the allies")
o = econ8.handle_chat(chat("vi", "!buy wharf argon prime"))
check(o[0]["argv"] == ["Cluster_14_Sector001_macro", "ally"], f"default owner is ally ({o[0]['argv']})")
o = econ8.handle_chat(chat("vi", "!buy wharf"))
check(o[0]["argv"] == ["", "ally"], "no sector + default owner")

# per-purchase override, with and without a sector
o = econ8.handle_chat(chat("vi", "!buy wharf argon prime player"))
check(o[0]["argv"] == ["Cluster_14_Sector001_macro", "player"], "trailing 'player' overrides")
o = econ8.handle_chat(chat("vi", "!buy wharf player"))
check(o[0]["argv"] == ["", "player"], "'player' alone = player-owned, current sector")
o = econ8.handle_chat(chat("vi", "!buy wharf PLAYER"))
check(o[0]["argv"] == ["", "player"], "the owner word is case-insensitive")

# the streamer's switch flips the default, and chat can still override it back
rt3.stations_to_player = True
o = econ8.handle_chat(chat("vi", "!buy wharf argon prime"))
check(o[0]["argv"] == ["Cluster_14_Sector001_macro", "player"], "switch flips the default to player")
o = econ8.handle_chat(chat("vi", "!buy wharf argon prime ally"))
check(o[0]["argv"] == ["Cluster_14_Sector001_macro", "ally"], "'ally' overrides the switch back")
rt3.stations_to_player = False

# a multi-word sector must not lose its last word to the owner parser
o = econ8.handle_chat(chat("vi", "!buy wharf black hole sun iv"))
check(o[0]["argv"][1] == "ally" and o[0]["argv"][0].startswith("Cluster_"),
      f"a multi-word sector still resolves ({o[0]['argv']})")

# fixed-owner events declare no owner arg and stay single-valued: a Kha'ak hive
# can never be talked onto the player's account.
o = econ8.handle_chat(chat("vi", "!buy hive argon prime player"))
check(kinds(o) == ["say"], "'player' is not a sector, so a fixed-owner buy rejects it")
o = econ8.handle_chat(chat("vi", "!buy hive argon prime"))
check(o[0]["argv"] == ["Cluster_14_Sector001_macro"], f"fixed-owner buy sends one value ({o[0]['argv']})")

# --- refunds: X4 charged for something it could not do ---------------------
# MD can only name the ACTION (the buyer never reaches it), so the bridge matches
# the failure against its own record of what it charged.
w7 = Wallet(tempfile.mktemp(suffix=".json"), EconomySettings(min_purchase_price=10), clock=lambda: 0)
econ7 = Economy(w7, [wharf], clock=clk)
w7.get("builder").coins = 100000
start_coins = w7.get("builder").coins
start_karma = w7.get("builder").karma

o = econ7.handle_chat(chat("builder", "!buy wharf argon prime"))
check(o[0]["t"] == "cmd", "wharf bought")
check(w7.get("builder").coins == start_coins - 9000, "charged up front")

o = econ7.handle_x4_failure({"t": "cmdfail", "id": "station_wharf",
                             "reason": "no room in Argon Prime"})
check(kinds(o) == ["say"], "a failure produces exactly one chat line")
check("refunded" in o[0]["msg"] and "no room in Argon Prime" in o[0]["msg"],
      f"the refund names the reason ({o[0]['msg']})")
check("@builder" in o[0]["msg"], "the refund is addressed to the buyer, not the chatter")
check(w7.get("builder").coins == start_coins, "coins fully restored")
check(w7.get("builder").karma == start_karma, "karma restored to its pre-purchase value")

# ...and the failed event must not burn its cooldown either — nothing happened.
o = econ7.handle_chat(chat("builder", "!buy wharf argon prime"))
check(o[0]["t"] == "cmd", "a refunded event can be re-bought immediately (cooldown released)")

# The wire shape MD actually writes. Twitch_Fail concatenates this JSON by hand, so
# pin the literal line here: if the MD string build and protocol.CMDFAIL ever drift,
# the refund silently stops working (the bridge would treat it as an unknown action).
raw = ('{"t":"cmdfail","id":"station_wharf","reason":"no room in Argon Prime"}\n')
decoded = protocol.decode(raw)
check(decoded["t"] == protocol.CMDFAIL, "MD's hand-built line decodes as a cmdfail")
w7.get("builder").coins = 60000
econ7.handle_chat(chat("builder", "!buy wharf"))
before = w7.get("builder").coins
o = econ7.handle_x4_failure(decoded)
check(w7.get("builder").coins == before + 9000, "the literal MD line drives a real refund")

# A second failure with nothing outstanding must not hand out free coins.
econ7.handle_x4_failure({"t": "cmdfail", "id": "station_wharf", "reason": "no room"})
coins = w7.get("builder").coins
o = econ7.handle_x4_failure({"t": "cmdfail", "id": "station_wharf", "reason": "no room"})
check(w7.get("builder").coins == coins, "a failure with no outstanding charge refunds nothing")
check(kinds(o) == ["say"] and "@builder" not in o[0]["msg"],
      "unmatched failure still tells chat, without naming anyone")

# An unrelated action's failure must not refund a different event's buyer.
w7.get("builder").coins = 50000
econ7.handle_chat(chat("builder", "!buy wharf"))
before = w7.get("builder").coins
econ7.handle_x4_failure({"t": "cmdfail", "id": "station_shipyard", "reason": "nope"})
check(w7.get("builder").coins == before, "a failure only refunds its own action id")

# Charges age out, so a viewer can't be refunded for something long since built.
clk.t += 301
before = w7.get("builder").coins
econ7.handle_x4_failure({"t": "cmdfail", "id": "station_wharf", "reason": "late"})
check(w7.get("builder").coins == before, "charges older than the refund window are not refunded")

print("\n" + ("ALL PASS" if ok else "SOME FAILED"))
sys.exit(0 if ok else 1)
