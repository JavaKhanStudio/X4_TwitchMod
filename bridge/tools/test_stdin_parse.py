#!/usr/bin/env python3
"""The stdin dev source: every command in its help parses to the event it always
has, bad input parses to nothing, and the help text lists exactly those commands."""
import contextlib
import io
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from twitch_bridge import protocol  # noqa: E402
from twitch_bridge.sources import stdin  # noqa: E402

ok = True


def check(c, m):
    global ok
    print(("PASS: " if c else "FAIL: ") + m)
    ok = ok and c


cases = {
    "chat alice hello there": protocol.chat("alice", "hello there"),
    "chat alice": protocol.chat("alice", ""),
    "CHAT alice hi": protocol.chat("alice", "hi"),
    "chatas moderator bob !spawn fighter": protocol.chat("bob", "!spawn fighter",
                                                         badges=["moderator"]),
    "redeem carol Pirate Attack": protocol.redeem("carol", "Pirate Attack"),
    "sub dave": protocol.sub("dave", "1000", 1),
    "sub dave 2000": protocol.sub("dave", "2000", 1),
    "sub dave 3000 7": protocol.sub("dave", "3000", 7),
    "cheer erin 500": protocol.cheer("erin", 500),
    "raid frank 250": protocol.raid("frank", 250),
    "follow gina": protocol.follow("gina"),
    "ready": protocol.ready(),
    '  {"t": "chat", "user": "x", "msg": "raw"}  ': {"t": "chat", "user": "x", "msg": "raw"},
}
for line, want in cases.items():
    got = stdin._parse(line)
    check(got == want, f"{line.strip()!r} -> {got}")

for bad in ["", "   ", "{not json", "nosuch thing", "chat", "cheer erin lots",
            "raid frank", "sub dave 1000 many", "chatas moderator"]:
    check(stdin._parse(bad) is None, f"{bad!r} -> None")

out = io.StringIO()
with contextlib.redirect_stdout(out):
    got = stdin._parse("help")
check(got is None and out.getvalue() == stdin.HELP, "'help' prints HELP and emits nothing")

listed = {ln.split()[0] for ln in stdin.HELP.splitlines()[1:]}
check(listed == {"chat", "chatas", "redeem", "sub", "cheer", "raid", "follow", "ready",
                 "{...}", "help", "quit"}, f"HELP lists every command: {sorted(listed)}")
check(stdin.HELP.splitlines()[2]
      == "  chatas <role> <user> <msg...>   chat with a badge "
         "(role: subscriber|vip|moderator|broadcaster)", "HELP keeps its column layout")

print("\nOK" if ok else "\nFAILED")
sys.exit(0 if ok else 1)
