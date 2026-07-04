#!/usr/bin/env python3
"""Generate bridge/twitch_bridge/ships.json — the buyable-ship registry — straight
from an X4 install's game data, so prices are REAL and macros are CORRECT.

    py -3 tools/gen_ships.py "E:\\Steam\\steamapps\\common\\X4 Foundations"

It reads each cat/dat pair (base + every installed DLC), pulls `libraries/wares.xml`
(ship price + macro) and the English text `t/0001-l044.xml` (ship names), then emits
one row per player-buyable ship: {key, macro, label, credits, size, role}. Re-run
after installing a DLC to pick up its ships. `ships.py` loads the result at runtime.

The X4 cat format is text: '<path with spaces> <size> <timestamp> <hash>' per line;
the dat is those files concatenated in listing order. We compute each file's offset
from the running size sum and slice it out of the dat.
"""
from __future__ import annotations

import json
import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

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


def cat_entries(cat: Path):
    """Yield (relpath_lower, offset, size) for a .cat, honoring space-containing paths."""
    offset = 0
    for line in cat.read_text(encoding="utf-8", errors="replace").splitlines():
        parts = line.split(" ")
        if len(parts) < 4:
            continue
        try:
            size = int(parts[-3])
        except ValueError:
            continue
        path = " ".join(parts[:-3]).lower()
        yield path, offset, size
        offset += size


def extract(cat: Path, want: str) -> bytes | None:
    dat = cat.with_suffix(".dat")
    if not dat.exists():
        return None
    for path, off, size in cat_entries(cat):
        if path == want:
            with open(dat, "rb") as f:
                f.seek(off)
                return f.read(size)
    return None


def all_cats(root: Path) -> list[Path]:
    cats = sorted((c for c in root.glob("*.cat") if "_sig" not in c.name))
    for ext in sorted(root.glob("extensions/*")):
        cats += sorted(c for c in ext.glob("*.cat") if "_sig" not in c.name)
    return cats


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


def main() -> int:
    root = Path(sys.argv[1] if len(sys.argv) > 1 else r"E:\Steam\steamapps\common\X4 Foundations")
    if not root.exists():
        print(f"X4 install not found: {root}"); return 1

    ships: dict[str, dict] = {}          # macro -> ship data (later cats override)
    text: dict[tuple[str, str], str] = {}  # (page,id) -> raw text (for name resolution)
    for cat in all_cats(root):
        w = extract(cat, "libraries/wares.xml")
        if w:
            for s in parse_ships(w):
                if s["macro"]:
                    ships[s["macro"]] = s
        t = extract(cat, "t/0001-l044.xml")
        if t:
            merge_text(t, text)

    # dedupe by NAME: X4 has many variants per ship (Vanguard/Sentinel/…) sharing one
    # ware name; offer each named warship ONCE, keeping the cheapest (base) variant.
    by_label: dict[str, dict] = {}
    for macro, s in ships.items():
        if not macro or SKIP_MACRO.search(macro) or s["credits"] <= 0:
            continue
        if "noplayerbuild" in s["tags"] or "blueprintsaleonly" in s["tags"]:
            continue
        role = role_of(macro)
        if role not in COMBAT_ROLES:
            continue
        full = resolve(s["name_page"], s["name_id"], text)       # e.g. "Nemesis Vanguard"
        base = full.split(" ")[0] if full else ""                # the ship name: "Nemesis"
        if not base or not re.fullmatch(r"[A-Za-z][A-Za-z0-9'\-]*", base):
            continue   # skip anything that didn't resolve to a clean word
        row = {"key": base.lower(), "label": base, "macro": macro,
               "credits": s["credits"], "size": size_of(macro), "role": role}
        cur = by_label.get(base.lower())
        if cur is None or row["credits"] < cur["credits"]:
            by_label[base.lower()] = row

    rows = sorted(by_label.values(), key=lambda r: (r["credits"], r["key"]))
    out = Path(__file__).resolve().parents[1] / "twitch_bridge" / "ships.json"
    out.write_text(json.dumps(rows, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"wrote {out} ({len(rows)} buyable ships; "
          f"{min(r['credits'] for r in rows):,}..{max(r['credits'] for r in rows):,} cr)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
