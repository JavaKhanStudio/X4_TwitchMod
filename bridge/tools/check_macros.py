#!/usr/bin/env python3
"""Check every macro our MD scripts reference against the BASE GAME + official DLC.

    py -3 tools/check_macros.py "E:\\Steam\\steamapps\\common\\X4 Foundations"

Why: a macro that exists on THIS machine may not be vanilla. `station_arg_defence_
base_01_macro` looks exactly like a base-game station hull, and every other
`station_*_base_01_macro` is — but that one ships in a third-party mod
(faction_fix_pack). It got into the defence-platform cue from a survey that scanned
every .cat in the install, mods included, and the game answered at load with:

    twitch_integration.xml(1260): Warning while parsing expression:
    Property lookup failed  * Input: macro.station_arg_defence_base_01_macro

The lookup fails, the macro is null, and the station silently never builds. So this
check reads ONLY the base archives and `extensions/ego_dlc_*` — never anything else
installed — which is the same standard the mod itself has to meet: it must work on a
plain X4 + DLC install.

Catches both spellings MD uses: the `macro.<name>` expression form and the bare
`macro="<name>"` attribute on create_ship / create_station / find_*.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

from x4cat import extract

MD_FILES = sorted((Path(__file__).resolve().parents[2] / "extensions").rglob("md/*.xml"))

# `macro.<name>` in an expression, and macro="<name>" as a bare attribute value.
RE_EXPR = re.compile(r"macro\.([a-z0-9_]+_macro)\b", re.IGNORECASE)
RE_ATTR = re.compile(r'macro="([a-z0-9_]+_macro)"', re.IGNORECASE)


def vanilla_macros(root: Path) -> dict[str, str]:
    """name(lower) -> which archive defines it. Base game + ego_dlc_* ONLY."""
    cats = sorted(c for c in root.glob("*.cat") if "_sig" not in c.name)
    for ext in sorted(root.glob("extensions/ego_dlc_*")):
        cats += sorted(c for c in ext.glob("*.cat") if "_sig" not in c.name)
    index: dict[str, str] = {}
    for cat in cats:
        blob = extract(cat, "index/macros.xml")
        if not blob:
            continue
        for m in re.finditer(r'<entry name="([^"]+)"', blob.decode("utf-8", "replace")):
            index[m.group(1).lower()] = cat.parent.name
    return index


def main() -> int:
    root = Path(sys.argv[1] if len(sys.argv) > 1
                else r"E:\Steam\steamapps\common\X4 Foundations")
    if not root.exists():
        print(f"X4 install not found: {root}")
        return 1

    index = vanilla_macros(root)
    if not index:
        print("could not read index/macros.xml from any base archive")
        return 1

    # Macros this mod DEFINES itself are legitimately absent from the vanilla index.
    ours = set()
    for idx in (Path(__file__).resolve().parents[2] / "extensions").rglob("index/macros.xml"):
        ours |= {m.lower() for m in re.findall(r'<entry name="([^"]+)"',
                                               idx.read_text(encoding="utf-8"))}

    bad = 0
    total = 0
    for md in MD_FILES:
        src = md.read_text(encoding="utf-8")
        used = sorted(set(RE_EXPR.findall(src)) | set(RE_ATTR.findall(src)))
        total += len(used)
        for name in used:
            if name.lower() in index or name.lower() in ours:
                continue
            bad += 1
            line = next((i for i, ln in enumerate(src.splitlines(), 1) if name in ln), 0)
            print(f"FAIL: {md.name}:{line} '{name}' is not in the base game or any "
                  f"official DLC (nor defined by this mod)")

    print(f"\nchecked {total} macro references across {len(MD_FILES)} MD file(s)")
    print("ALL PASS" if not bad else f"{bad} UNRESOLVED")
    return 0 if not bad else 1


if __name__ == "__main__":
    sys.exit(main())
