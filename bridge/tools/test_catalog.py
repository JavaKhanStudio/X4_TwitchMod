#!/usr/bin/env python3
"""Validate the forward economy schema stub (StoreEvent / CATALOG / projections).
Keeps the schema from rotting; not a test of runtime behaviour (that's M4.0).
Also checks that the published ships wiki (docs/wiki, built by ../X4_Wiki) shows the store's
prices: a price on the wiki that differs from the store is a bug."""
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from twitch_bridge.catalog import (  # noqa: E402
    CATALOG,
    KARMA,
    KINDS,
    STARTER,
    STATUS,
    TIERS,
    catalog_view,
)
from twitch_bridge import fleet  # noqa: E402
from twitch_bridge import ships as shipreg  # noqa: E402

WIKI = Path(__file__).resolve().parents[2] / "docs" / "wiki"
REBUILD = "py -3 ../X4_Wiki/tools/build_wiki.py --out docs/wiki"
PRICE = re.compile(r"data-price=(buy|adopt)>([0-9,]+)<")
SIZE = re.compile(r"class=sub>(XL|L|M|S) ")

ok = True


def check(c, m):
    global ok
    print(("PASS: " if c else "FAIL: ") + m)
    ok = ok and c


# STARTER (live engine) is untouched and still a list of Commands.
check(len(STARTER) >= 6 and STARTER[0].action == "ping", "STARTER runtime catalog intact")

# CATALOG integrity. Every key a viewer can type (buy_keys + nicknames) must be
# unique across the whole catalog, or the !buy lookup is ambiguous.
keys = [k for e in CATALOG for k in [e.buy_key] + e.nicknames]
ids = [e.id for e in CATALOG]
check(len(set(keys)) == len(keys), "buy_keys + nicknames are unique")
check(len(set(ids)) == len(ids), "ids are unique")
for e in CATALOG:
    check(e.karma in KARMA, f"{e.id}: karma '{e.karma}' valid")
    check(e.tier in TIERS, f"{e.id}: tier {e.tier} valid")
    check(e.status in STATUS, f"{e.id}: status '{e.status}' valid")
    check(e.kind in KINDS, f"{e.id}: kind '{e.kind}' valid")
    if e.variable:
        check(e.unit in e.args, f"{e.id}: variable event's unit '{e.unit}' is an arg")

# Severity safety: Major/Doom tiers ship disabled.
for e in CATALOG:
    if e.tier >= 2:
        check(e.default_enabled is False, f"{e.id}: tier>=2 ships disabled (safety)")

# syntax projection.
ns = next(e for e in CATALOG if e.id == "name_ship")
check(ns.syntax == "!buy nameship <name>", "buy syntax string")
wd = next(e for e in CATALOG if e.id == "ware_drop")
check(wd.syntax == "!buy ware <ware> <qty>", "variable buy syntax string")
ri = next(e for e in CATALOG if e.on_event)
check(ri.syntax.startswith("(auto on"), "event-triggered syntax string")
bal = next(e for e in CATALOG if e.id == "balance")
check(bal.syntax == "!balance", "info syntax is a direct command, not !buy")
check("bal" in bal.nicknames, "info nicknames carried")

# display() shape + item-list view.
d = ns.display()
for key in ("buy_key", "nicknames", "kind", "label", "description", "category",
            "tier", "tier_name", "karma", "syntax", "cost", "status", "enabled"):
    check(key in d, f"display() has '{key}'")
check(d["status"] == "planned", "status defaults to 'planned' and is projected")
check(d["tier_name"] == "Pure Interaction", "tier_name resolved from TIERS")

view = catalog_view()  # enabled_only=True
view_keys = {v["buy_key"] for v in view}
check("nameship" in view_keys, "enabled event in /catalog view")
check("khaak" not in view_keys, "disabled (tier-2) event excluded from default view")
check(len(catalog_view(enabled_only=False)) == len(CATALOG), "full view includes all")



def wiki_drift(wiki: Path) -> list[str]:
    """Every price on the published wiki that the store no longer charges, and every store ship
    without a page: !buy ship is ships.Ship.coins, !buy adopt is fleet.FleetShip.coins (a mod
    ship's page is priced by the size it shows, as the store prices a hull it does not know)."""
    errors = []
    pages = {p.stem: p for p in (wiki / "ships").glob("*.html")}
    errors += [f"store ship {k} has no page" for k in shipreg.SHIPS.keys() - pages.keys()]
    errors += [f"page {k} is not a store ship" for k in pages.keys() - shipreg.SHIPS.keys()]
    for key in pages.keys() & shipreg.SHIPS.keys():
        s = shipreg.SHIPS[key]
        store = {"buy": s.coins, "adopt": fleet.FleetShip(idcode="", macro=s.macro, size=s.size).coins}
        shown = {k: int(n.replace(",", "")) for k, n in PRICE.findall(pages[key].read_text("utf-8"))}
        errors += [f"{key} {k}: wiki {shown.get(k)}, store {v}" for k, v in store.items() if shown.get(k) != v]
    for page in (wiki / "mods").glob("*.html"):
        text = page.read_text("utf-8")
        size = SIZE.search(text)
        store = fleet.FleetShip(idcode="", macro=page.stem + "_macro", size=size[1] if size else "").coins
        shown = {k: int(n.replace(",", "")) for k, n in PRICE.findall(text)}
        if shown.get("adopt") != store:
            errors.append(f"mod {page.stem} adopt: wiki {shown.get('adopt')}, store {store}")
    return errors


# The published wiki matches the store. A retune of SHIP_COIN_DIVISOR / ADOPT_COIN_DIVISOR /
# ADOPT_SIZE_PRICE or a new ships.json (gen_ships.py) fails here until the wiki is rebuilt.
if WIKI.is_dir():
    drift = wiki_drift(WIKI)
    check(not drift, "docs/wiki shows the store's prices" + (
        f": {len(drift)} wrong, e.g. {'; '.join(drift[:3])}. Rebuild it: {REBUILD}" if drift else ""))
    real = shipreg.SHIP_COIN_DIVISOR
    shipreg.SHIP_COIN_DIVISOR = real * 2  # the check itself must catch a retune
    check(len(wiki_drift(WIKI)) > len(drift), "a !buy ship retune makes the wiki check fail")
    shipreg.SHIP_COIN_DIVISOR = real
else:
    print(f"SKIP: no published wiki at {WIKI}")

print("\n" + ("ALL PASS" if ok else "SOME FAILED"))
sys.exit(0 if ok else 1)
