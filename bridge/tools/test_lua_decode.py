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
Lib = lua.execute(open(LUA).read())
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

print(f"\n{'ALL PASS' if fail == 0 else str(fail) + ' FAILURES'}")
sys.exit(1 if fail else 0)
