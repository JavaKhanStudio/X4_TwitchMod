#!/usr/bin/env python3
"""Generate bridge/twitch_bridge/sectors.json — the sector registry — straight from
an X4 install's game data, so sector NAMES and MACROS are REAL.

    py -3 tools/gen_sectors.py "E:\\Steam\\steamapps\\common\\X4 Foundations"

Sector-targeted events (`!buy wharf argon prime`) need to turn viewer text into
something MD can resolve. MD has no string parsing at all, so the bridge does the
matching and sends the raw MACRO NAME; MD then does `find_sector macro="macro.{$m}"`.

Where the data lives (verified against X4 8.00):
  * `maps/xu_ep2_universe/*sectors.xml` — every sector macro of the PLAYABLE galaxy,
    one `<macro name="…" class="sector">` each. The base game ships `sectors.xml`;
    each DLC adds its own file in the same folder (dlc_terran_sectors.xml, …). Other
    map folders (demo_universe, mainmenuscene, the Timelines scenario universes) are
    NOT the playable galaxy and are skipped.
  * `libraries/mapdefaults.xml` — `<dataset macro="…"><properties><identification
    name="{page,line}"/>`: the display name, as a TextDB reference. Every DLC ships
    its own mapdefaults.xml with the datasets for its sectors.
  * `t/0001-l044.xml` — the English TextDB the {page,line} refs point into.

Re-run after installing a DLC to add its sectors. `sectors.py` loads the result.
Reuses the cat/dat reader in x4cat.py and the text resolver from gen_ships.py.
"""
from __future__ import annotations

import json
import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

from gen_ships import merge_text, resolve
from x4cat import all_cats, cat_entries, extract

# twitch_bridge.sectors (imported in main) from the bridge/ dir, uninstalled.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

# The playable galaxy's map folder. Everything else in maps/ is a menu backdrop or a
# self-contained Timelines scenario universe — spawning there is not a thing.
GALAXY_DIR = "maps/xu_ep2_universe/"


def sector_macros(root: Path) -> set[str]:
    """Every sector macro name of the playable galaxy (base game + installed DLCs)."""
    out: set[str] = set()
    for cat in all_cats(root):
        for path, _off, _size in cat_entries(cat):
            if not (path.startswith(GALAXY_DIR) and path.endswith("sectors.xml")):
                continue
            blob = extract(cat, path)
            if not blob:
                continue
            try:
                tree = ET.fromstring(blob)
            except ET.ParseError:
                continue
            for m in tree.iter("macro"):
                if m.get("class") == "sector" and m.get("name"):
                    out.add(m.get("name"))
    return out


def macro_names(root: Path) -> tuple[dict[str, str], dict[tuple[str, str], str]]:
    """(macro-lowercased -> '{page,line}' name ref, TextDB)."""
    names: dict[str, str] = {}
    text: dict[tuple[str, str], str] = {}
    for cat in all_cats(root):
        blob = extract(cat, "libraries/mapdefaults.xml")
        if blob:
            try:
                tree = ET.fromstring(blob)
            except ET.ParseError:
                tree = None
            if tree is not None:
                for d in tree.iter("dataset"):
                    ident = d.find("./properties/identification")
                    if d.get("macro") and ident is not None and ident.get("name"):
                        names[d.get("macro").lower()] = ident.get("name")
        t = extract(cat, "t/0001-l044.xml")
        if t:
            merge_text(t, text)
    return names, text


def key_of(label: str) -> str:
    """What viewers type. MUST stay identical to sectors.norm() — that function
    normalises the viewer's chat text and these keys are what it is matched against."""
    from twitch_bridge.sectors import norm
    return norm(label)


def main() -> int:
    root = Path(sys.argv[1] if len(sys.argv) > 1 else r"E:\Steam\steamapps\common\X4 Foundations")
    if not root.exists():
        print(f"X4 install not found: {root}")
        return 1

    macros = sector_macros(root)
    names, text = macro_names(root)

    rows: list[dict] = []
    seen: set[str] = set()
    unnamed: list[str] = []
    for macro in sorted(macros):
        ref = names.get(macro.lower())
        label = ""
        if ref:
            m = re.match(r"\{(\d+),\s*(\d+)\}", ref)
            if m:
                label = resolve(m.group(1), m.group(2), text)
        if not label:
            unnamed.append(macro)
            continue
        key = key_of(label)
        if not key or key in seen:
            # Two sectors sharing a display name would make `!buy … <name>` ambiguous
            # with no way for a viewer to pick. Keep the first, report the rest.
            unnamed.append(f"{macro} (duplicate name {label!r})")
            continue
        seen.add(key)
        # The macro is sent to MD verbatim for macro.{$m}; MD lookups are
        # case-insensitive but keep the game's own casing to stay diff-able.
        rows.append({"key": key, "label": label, "macro": macro})

    rows.sort(key=lambda r: r["key"])
    out = Path(__file__).resolve().parents[1] / "twitch_bridge" / "sectors.json"
    out.write_text(json.dumps(rows, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"wrote {out} ({len(rows)} sectors)")
    if unnamed:
        print(f"  skipped {len(unnamed)}: " + ", ".join(unnamed[:10]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
