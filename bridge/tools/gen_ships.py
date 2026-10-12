#!/usr/bin/env python3
"""Generate bridge/twitch_bridge/ships.json — the buyable-ship registry — straight
from an X4 install's game data, so prices are REAL and macros are CORRECT.

    py -3 tools/gen_ships.py "E:\\Steam\\steamapps\\common\\X4 Foundations"

It reads each cat/dat pair (base + every installed DLC), pulls `libraries/wares.xml`
(ship price + macro) and the English text `t/0001-l044.xml` (ship names), then emits
one row per player-buyable ship: {key, macro, label, credits, size, role}. Re-run
after installing a DLC to pick up its ships. `ships.py` loads the result at runtime.

Reading the cat/dat archives is x4cat.py's job; `all_cats`, `cat_entries` and
`extract` are re-exported here for the tools that import them from this file.
"""
from __future__ import annotations

import json
import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

from x4cat import all_cats, cat_entries, extract, install_root  # noqa: F401

# ships we never offer: pure-enemy (Xenon/Kha'ak, price 0), drones, and research hulls.
SKIP_MACRO = re.compile(r"_(xen|kha)_|transdrone|_drone_|_research_|_lasertower|_spacesuit")
# role from the macro's ship-type token; order matters (first hit wins).
ROLE_TOKENS = ["scout", "fighter", "heavyfighter", "corvette", "frigate", "gunboat",
               "destroyer", "battleship", "carrier", "resupplier", "builder", "miner",
               "trans", "scavenger", "auxiliary"]
# Only offer WARSHIPS: miners/transports/etc. have messy compound names and aren't
# what "buy a ship to fight in the arena" means. Keep the combat + recon roles.
COMBAT_ROLES = {"scout", "fighter", "heavy fighter", "corvette", "frigate",
                "gunboat", "destroyer", "carrier", "battleship"}
SIZE_RE = re.compile(r"_(xs|s|m|l|xl)_")


def size_of(macro: str) -> str:
    m = SIZE_RE.search(macro)
    return m.group(1).upper() if m else "?"


def role_of(macro: str) -> str:
    for tok in ROLE_TOKENS:
        if f"_{tok}_" in macro or f"_{tok}" in macro:
            return "heavy fighter" if tok == "heavyfighter" else ("transport" if tok == "trans" else tok)
    return "ship"


def merge_text(text_xml: bytes, into: dict[tuple[str, str], str]) -> None:
    """Merge ALL (page,id)->raw text from a t-file (needed to resolve name refs)."""
    try:
        root = ET.fromstring(text_xml)
    except ET.ParseError:
        return
    for pg in root.iter("page"):
        page = pg.get("id")
        for t in pg.iter("t"):
            if page and t.get("id"):
                into[(page, t.get("id"))] = t.text or ""


def resolve(page: str, tid: str, text: dict, depth: int = 0) -> str:
    """X4 names are `(comment){page,id}{page,id}` — strip the (comment) and splice in
    the referenced strings (e.g. 'Nemesis' + 'Vanguard'). Depth-guarded."""
    raw = text.get((page, tid), "")
    if depth > 5 or not raw:
        return ""
    raw = re.sub(r"\([^)]*\)", "", raw)                       # drop (comments)
    raw = re.sub(r"\{(\d+),\s*(\d+)\}",
                 lambda m: " " + resolve(m.group(1), m.group(2), text, depth + 1) + " ", raw)
    return re.sub(r"\s+", " ", raw).strip()


def parse_ships(wares_xml: bytes) -> list[dict]:
    try:
        root = ET.fromstring(wares_xml)
    except ET.ParseError:
        return []
    ships = []
    for w in root.iter("ware"):
        if w.get("transport") != "ship":
            continue
        comp = w.find("component")
        price = w.find("price")
        macro = comp.get("ref") if comp is not None else ""
        avg = int(price.get("average")) if price is not None and price.get("average") else 0
        m = re.match(r"\{(\d+),(\d+)\}", w.get("name", ""))
        ships.append({"macro": macro, "credits": avg, "tags": w.get("tags", ""),
                      "name_page": m.group(1) if m else "", "name_id": m.group(2) if m else ""})
    return ships


def load(root: Path) -> tuple[dict[str, dict], dict[tuple[str, str], str]]:
    """Every ship ware by macro (later cats override) and the English text by
    (page, id), for name resolution."""
    ships: dict[str, dict] = {}
    text: dict[tuple[str, str], str] = {}
    for cat in all_cats(root):
        w = extract(cat, "libraries/wares.xml")
        if w:
            for s in parse_ships(w):
                if s["macro"]:
                    ships[s["macro"]] = s
        t = extract(cat, "t/0001-l044.xml")
        if t:
            merge_text(t, text)
    return ships, text


def ship_row(macro: str, s: dict, text: dict) -> dict | None:
    """The registry row for one ship ware, or None if it is not a buyable warship."""
    if not macro or SKIP_MACRO.search(macro) or s["credits"] <= 0:
        return None
    if "noplayerbuild" in s["tags"] or "blueprintsaleonly" in s["tags"]:
        return None
    role = role_of(macro)
    if role not in COMBAT_ROLES:
        return None
    full = resolve(s["name_page"], s["name_id"], text)       # e.g. "Nemesis Vanguard"
    base = full.split(" ")[0] if full else ""                # the ship name: "Nemesis"
    if not base or not re.fullmatch(r"[A-Za-z][A-Za-z0-9'\-]*", base):
        return None   # skip anything that didn't resolve to a clean word
    return {"key": base.lower(), "label": base, "macro": macro,
            "credits": s["credits"], "size": size_of(macro), "role": role}


def buyable(ships: dict[str, dict], text: dict) -> list[dict]:
    # dedupe by NAME: X4 has many variants per ship (Vanguard/Sentinel/…) sharing one
    # ware name; offer each named warship ONCE, keeping the cheapest (base) variant.
    by_label: dict[str, dict] = {}
    for macro, s in ships.items():
        row = ship_row(macro, s, text)
        if row is None:
            continue
        cur = by_label.get(row["key"])
        if cur is None or row["credits"] < cur["credits"]:
            by_label[row["key"]] = row
    return sorted(by_label.values(), key=lambda r: (r["credits"], r["key"]))


def main() -> int:
    root = install_root()
    if root is None:
        return 1
    rows = buyable(*load(root))
    out = Path(__file__).resolve().parents[1] / "twitch_bridge" / "ships.json"
    out.write_text(json.dumps(rows, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"wrote {out} ({len(rows)} buyable ships; "
          f"{min(r['credits'] for r in rows):,}..{max(r['credits'] for r in rows):,} cr)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
