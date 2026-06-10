#!/usr/bin/env python3
"""Catalog ⇄ MD sync check: the `status` field in catalog.py must match what the
MD script actually implements, so the roadmap can never quietly lie.

An EFFECT event counts as implemented when twitch_integration.xml has a cue
dispatching on its action id (control='<id>') whose body carries no TODO marker.
An INFO event lives bridge-side: implemented when its id is a canonical command
in economy.py's COMMAND_ALIASES — whose alias list must also equal the entry's
buy_key + nicknames (one source of truth for what viewers can type).

  status == "live"        -> must be implemented                (else FAIL)
  implemented             -> status must be "live"              (else FAIL: catalog lags the game)
  "wip"/"planned"/"suggested" and not implemented               -> fine
"""
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from twitch_bridge.catalog import CATALOG  # noqa: E402
from twitch_bridge.economy import COMMAND_ALIASES  # noqa: E402

XML = (Path(__file__).resolve().parents[2]
       / "extensions" / "twitch_integration" / "md" / "twitch_integration.xml")
src = XML.read_text()

# control id -> does the cue body still contain a TODO marker?
# Cues in this file are flat (not nested), so splitting on '<cue ' isolates each body.
cues: dict[str, bool] = {}
for block in src.split("<cue ")[1:]:
    m = re.search(r"control=\"'(\w+)'\"", block)
    if m:
        cues[m.group(1)] = "TODO" in block

ok = True


def check(c, m):
    global ok
    print(("PASS: " if c else "FAIL: ") + m)
    ok = ok and c


check(len(cues) >= 1, f"parsed dispatch cues from MD ({len(cues)} found: {sorted(cues)})")

for e in CATALOG:
    if e.kind == "info":
        wired = e.id in COMMAND_ALIASES
        if e.status == "live":
            check(wired, f"{e.id}: live info action is a COMMAND_ALIASES canonical in economy.py")
            check(set([e.buy_key] + e.nicknames) == set(COMMAND_ALIASES.get(e.id, ())),
                  f"{e.id}: buy_key+nicknames == COMMAND_ALIASES['{e.id}']")
        elif wired:
            check(False, f"{e.id}: handled in economy.py but status is '{e.status}' "
                         "— promote it to 'live' in catalog.py")
        else:
            print(f"  ok : {e.id:<16} {e.status:<10} (info; not in economy.py yet)")
        continue
    implemented = cues.get(e.id) is False          # cue exists, TODO-free
    stub = cues.get(e.id) is True                  # cue exists, still a TODO stub
    if e.status == "live":
        check(implemented, f"{e.id}: status 'live' -> MD cue exists and is TODO-free")
    elif implemented:
        check(False, f"{e.id}: MD cue is implemented but status is '{e.status}' "
                     "— promote it to 'live' in catalog.py")
    else:
        where = "stub cue in MD" if stub else "no MD cue yet"
        print(f"  ok : {e.id:<16} {e.status:<10} ({where})")

print("\n" + ("ALL PASS" if ok else "SOME FAILED"))
sys.exit(0 if ok else 1)
