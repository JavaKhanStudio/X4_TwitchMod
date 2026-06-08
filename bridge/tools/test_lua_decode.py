"""Test the X4 mod's Lua json_decode against the bridge's real wire output.

Needs a Lua VM via `lupa` (pip install lupa). Skips (exit 0) if unavailable,
since the parsing logic only needs validating where a Lua runtime exists.

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
    print("SKIP: lupa not installed (pip install lupa)")
    sys.exit(0)

lua = LuaRuntime(unpack_returned_tuples=True)
lua.execute("""
  function RegisterEvent(name, fn) end
  function AddUITriggeredEvent(a, b, c) end
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

print(f"\n{'ALL PASS' if fail == 0 else str(fail) + ' FAILURES'}")
sys.exit(1 if fail else 0)
