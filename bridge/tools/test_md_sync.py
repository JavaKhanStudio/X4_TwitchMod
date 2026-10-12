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

from twitch_bridge.catalog import CATALOG, FACTION_KEYS  # noqa: E402
from twitch_bridge.economy import COMMAND_ALIASES  # noqa: E402

XML = (Path(__file__).resolve().parents[2]
       / "extensions" / "twitch_integration" / "md" / "twitch_integration.xml")
src = XML.read_text()

# action id -> does the cue body still contain a TODO marker?
# Splitting on '<cue ' isolates each body. DISPATCH cues (the ones with a control=
# filter, which is all this check cares about) are top-level; a dispatch cue may now
# have NESTED sub-cues under it — Twitch_OnBosoCall holds its call in one — and the
# split cuts those into blocks of their own. That is harmless for matching the action
# id, but it does mean a TODO parked inside a sub-cue would not be seen here.
# TWO dispatch shapes count as implementing an action:
#   control='<id>'          — the normal one; the args arrive ';'-joined in param3.
#   screen='Twitch_<id>'    — the 2-arg one. MD cannot split a string, so a command
#                             with two args is re-emitted by the ui lua on its own
#                             screen with the args in the control+value slots, and
#                             the cue deliberately has NO control filter.
cues: dict[str, bool] = {}
for block in src.split("<cue ")[1:]:
    m = re.search(r"control=\"'(\w+)'\"", block)
    if m:
        cues[m.group(1)] = "TODO" in block
        continue
    m = re.search(r"screen=\"'Twitch_(\w+)'\"", block)
    if m and m.group(1) != "Integration":
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

# Faction keys: MD matches the !buy args as literal strings, so its $keys list and
# the parallel $factions list must both mirror catalog.FACTION_KEYS exactly. A key
# in only one place makes that faction un-pickable (silent random fallback instead).
# EVERY copy is checked, not just the first: more than one cue carries these lists
# (the incident matches pairs with them, the stance cue resolves one key), and a
# library can't hand a list back to a cue that loops over it. Duplication is fine
# as long as it cannot drift quietly — that is this check's whole job.
mks = re.findall(r"name=\"\$keys\" exact=\"\[([^\]]*)\]\"", src)
mfs = re.findall(r"name=\"\$factions\" exact=\"\[([^\]]*)\]\"", src)
check(bool(mks) and len(mks) == len(mfs),
      f"found matching $keys/$factions definitions in MD ({len(mks)} copies)")
for n, (mk, mf) in enumerate(zip(mks, mfs), 1):
    md_keys = re.findall(r"'(\w+)'", mk)
    md_facs = re.findall(r"faction\.(\w+)", mf)
    check(md_keys == FACTION_KEYS,
          f"copy {n}: MD $keys == catalog.FACTION_KEYS"
          + ("" if md_keys == FACTION_KEYS else f" (MD has {md_keys})"))
    check(md_facs == FACTION_KEYS,
          f"copy {n}: MD $factions is faction.<key>, same order"
          + ("" if md_facs == FACTION_KEYS else f" (MD has {md_facs})"))

# --- MD structural rule the XSD cannot express -----------------------------------
# A cue inside an instantiated cue's subtree MUST have an event condition. Polled
# <check_value>-only conditions are legal on an ordinary cue (vanilla's own Boso call
# uses them) but not there, and the game rejects the cue AT LOAD:
#     twitch_integration.xml(1944): Found non-event condition 'check_value',
#     event condition required!
# A rejected cue is simply absent, so the failure is silent in game — a Boso call
# queued into a cue that no longer existed and nothing ever played. md.xsd validates
# this file happily, so the only cheap guard is here. Use a signalled cue that
# re-signals itself (cf. Twitch_RetryRead / Twitch_BosoPump) to wait for a state.
import xml.etree.ElementTree as ET  # noqa: E402


def has_event(cue) -> bool:
    conds = cue.find("conditions")
    if conds is None:
        return True     # no conditions at all is fine (a sub-cue with only a <delay>)
    return any(e.tag.startswith("event_") for e in conds.iter())


def walk(cue, inside_instantiated: bool, bad: list):
    for sub in cue.findall("./cues/cue"):
        if inside_instantiated and not has_event(sub):
            bad.append(sub.get("name"))
        walk(sub, inside_instantiated or sub.get("instantiate") == "true", bad)


bad_cues: list[str] = []
root = ET.parse(XML).getroot()
for top in root.findall("./cues/cue"):
    if top.get("instantiate") == "true" and not has_event(top):
        bad_cues.append(top.get("name"))
    walk(top, top.get("instantiate") == "true", bad_cues)
check(not bad_cues,
      "every cue under an instantiated cue has an event condition"
      + ("" if not bad_cues else f" (offenders: {bad_cues})"))

print("\n" + ("ALL PASS" if ok else "SOME FAILED"))
sys.exit(0 if ok else 1)
