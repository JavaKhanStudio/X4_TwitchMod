"""Test the X4 mod's Lua json_decode against the bridge's real wire output.

Needs a Lua VM via `lupa` (pip install lupa). FAILS (exit 1) without it: a
silent skip let WSL's python3, which has no lupa, pass it without running a
line (r37). Under WSL, run it with Windows `py.exe`, which has lupa.

    python tools/test_lua_decode.py
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))            # repo root
LUA = os.path.join(ROOT, "extensions", "twitch_integration", "ui", "twitch_integration.lua")
sys.path.insert(0, os.path.join(ROOT, "bridge"))

from twitch_bridge import protocol  # noqa: E402

try:
    from lupa import LuaRuntime
except ImportError:
    print("FAIL: lupa not installed (pip install lupa; under WSL use py.exe)")
    sys.exit(1)

lua = LuaRuntime(unpack_returned_tuples=True)
# Capture the registered MD-event handler and any signals the module emits.
lua.execute("""
  _G._reg = {}
  _G._signals = {}
  function RegisterEvent(name, fn) _reg[name] = fn end
  function AddUITriggeredEvent(screen, control, value)
    table.insert(_signals, {screen, control, value})
  end
  function DebugError(s) end
""")
with open(LUA) as f:
    Lib = lua.execute(f.read())
decode = Lib["json_decode"]

cases = [
    protocol.chat("alice", '!spawn fighter "now"'),
    protocol.redeem("bob", "Pirate Attack", 1),
    protocol.raid("bigstreamer", 250),
    protocol.sub("carol", "1000", 3),
    protocol.cheer("dave", 500),
    protocol.follow("erin"),
]

fail = 0
for msg in cases:
    line = protocol.encode(msg).decode().rstrip("\n")
    val, _err = decode(line)
    if val is None:
        print(f"FAIL decode: {line}"); fail += 1; continue
    ok = all(str(val[k]) == str(v) for k, v in msg.items() if not isinstance(v, list))
    print(f"{'PASS' if ok else 'FAIL'}: t={val['t']!s:8} {line}")
    fail += 0 if ok else 1

val, _ = decode('{"t":"chat", broken')
print(f"{'PASS' if val is None else 'FAIL'}: malformed input handled")
fail += 0 if val is None else 1

# Dispatch logic: onDecode must emit the action id as the MD `control` for cmd
# messages, and the type for others.
g = lua.globals()
on_decode = g._reg["Twitch.Decode"]
def last_control(line):
    lua.execute("_G._signals = {}")
    on_decode(None, line)
    sigs = g._signals
    return sigs[len(sigs)][2] if len(sigs) >= 1 else None  # lua 1-indexed

c = last_control('{"t":"cmd","id":"ping","by":"alice","args":{}}')
print(f"{'PASS' if c == 'ping' else 'FAIL'}: cmd dispatched by action id (got {c!r})")
fail += 0 if c == "ping" else 1

c = last_control('{"t":"ready"}')
print(f"{'PASS' if c == 'ready' else 'FAIL'}: non-cmd dispatched by type (got {c!r})")
fail += 0 if c == "ready" else 1


# Arg ORDER. MD reads the ';'-joined payload positionally, so the values must reach
# it in the order the catalog declares. `args` is a JSON object -> a Lua hash table
# whose pairs() order is undefined (this silently emitted "50;energycells"), so the
# lua must read the ordered `argv` array instead. Build the lines with the real
# protocol constructor so a regression in either half fails here.
def signals(line):
    """All (screen, control, value) triples one line produces, in order."""
    lua.execute("_G._signals = {}")
    on_decode(None, line)
    return [(g._signals[i][1], g._signals[i][2], g._signals[i][3])
            for i in range(1, len(g._signals) + 1)]           # lua is 1-indexed


def payload(line):
    """The joined-args value on the normal screen (what 1-arg cues read)."""
    for screen, _control, value in signals(line):
        if screen == "Twitch_Integration":
            return value
    return None


for args, want in [
    ({"faction1": "argon", "faction2": "paranid"}, "argon;paranid"),
    ({"faction1": "paranid", "faction2": "argon"}, "paranid;argon"),
    ({"ware": "energycells", "qty": "50"}, "energycells;50"),
    ({"a": "1", "b": "2", "c": "3", "d": "4"}, "1;2;3;4"),
    ({"faction1": "teladi"}, "teladi"),
    ({}, ""),
]:
    line = protocol.encode(protocol.command("faction_incident", "alice", args)).decode().rstrip("\n")
    got = payload(line)
    print(f"{'PASS' if got == want else 'FAIL'}: arg order {list(args.values())} -> {got!r}")
    fail += 0 if got == want else 1

# Station builds: the id IS the station type (one MD cue each) and the two args are
# WHERE (sector macro, "" = the player's current sector) and WHO OWNS IT. Both must
# arrive as separate strings on the station's own screen — MD reads them straight
# out of param2/param3, because it cannot split the ';'-joined form.
for sector, owner in [("Cluster_14_Sector001_macro", "ally"),
                      ("Cluster_14_Sector001_macro", "player"),
                      ("", "player")]:
    line = protocol.encode(protocol.command(
        "station_wharf", "alice", {"sector": sector, "owner": owner})).decode().rstrip("\n")
    want = ("Twitch_station_wharf", sector, owner)
    got = signals(line)
    print(f"{'PASS' if want in got else 'FAIL'}: station cmd -> (screen, sector, owner) {want!r}")
    fail += 0 if want in got else 1

# The empty sector is the case that matters: MD branches on `$SectorMacro != ''`, so
# it must arrive as an empty STRING, not as a missing or shifted slot.
line = protocol.encode(protocol.command(
    "station_wharf", "alice", {"sector": "", "owner": "ally"})).decode().rstrip("\n")
pair = [s for s in signals(line) if s[0] == "Twitch_station_wharf"]
ok_empty = pair and pair[0][1] == "" and pair[0][2] == "ally"
print(f"{'PASS' if ok_empty else 'FAIL'}: an empty sector stays an empty string beside the owner")
fail += 0 if ok_empty else 1

# Fixed-owner stations (Kha'ak hive, Raider den) send ONE arg and therefore stay on
# the control form — no second event, nothing for a viewer to redirect.
line = protocol.encode(protocol.command(
    "station_khaakhive", "alice", {"sector": "Cluster_14_Sector001_macro"})).decode().rstrip("\n")
sigs = signals(line)
ok_fixed = (len(sigs) == 1 and sigs[0][0] == "Twitch_Integration"
            and sigs[0][1] == "station_khaakhive")
print(f"{'PASS' if ok_fixed else 'FAIL'}: a fixed-owner station stays 1-arg on the control form")
fail += 0 if ok_fixed else 1

# TWO-ARG COMMANDS get a second event on their own screen, with the args in the
# control and value slots. MD cannot split a string (the `string` datatype has one
# property: format), so this is the ONLY way a cue receives two independent values.
line = protocol.encode(protocol.command(
    "adopt_ship", "ana", {"idcode": "PSF-481", "name": "ana's Nemesis"})).decode().rstrip("\n")
sigs = signals(line)
check_pair = ("Twitch_adopt_ship", "PSF-481", "ana's Nemesis")
print(f"{'PASS' if check_pair in sigs else 'FAIL'}: 2-arg cmd also emits (screen, arg1, arg2) — got {sigs}")
fail += 0 if check_pair in sigs else 1
joined = [s for s in sigs if s[0] == "Twitch_Integration"]
want_joined = "PSF-481;ana's Nemesis"
got_joined = joined[0][2] if joined else None
print(f"{'PASS' if got_joined == want_joined else 'FAIL'}: "
      f"the joined form still fires too (1-arg cues unaffected)")
fail += 0 if got_joined == want_joined else 1

# 1-arg and 0-arg commands must NOT get the extra event (nothing listens for it).
for args in ({"macro": "ship_arg_s_scout_01_a_macro"}, {}):
    line = protocol.encode(protocol.command("gift_ship", "ana", args)).decode().rstrip("\n")
    extra = [s for s in signals(line) if s[0] != "Twitch_Integration"]
    print(f"{'PASS' if not extra else 'FAIL'}: {len(args)}-arg cmd emits one event only")
    fail += 0 if not extra else 1

# No `argv` (older bridge / hand-written line): must still be deterministic, not random.
got = payload('{"t":"cmd","id":"x","by":"a","args":{"faction1":"argon","faction2":"paranid"}}')
print(f"{'PASS' if got == 'argon;paranid' else 'FAIL'}: argv-less line falls back to sorted keys (got {got!r})")
fail += 0 if got == "argon;paranid" else 1

print(f"\n{'ALL PASS' if fail == 0 else str(fail) + ' FAILURES'}")
sys.exit(1 if fail else 0)
