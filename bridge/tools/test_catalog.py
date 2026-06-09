#!/usr/bin/env python3
"""Validate the forward economy schema stub (StoreEvent / CATALOG / projections).
Keeps the schema from rotting; not a test of runtime behaviour (that's M4.0)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from twitch_bridge.catalog import CATALOG, KARMA, STARTER, TIERS, StoreEvent, catalog_view  # noqa: E402

ok = True


def check(c, m):
    global ok
    print(("PASS: " if c else "FAIL: ") + m)
    ok = ok and c


# STARTER (live engine) is untouched and still a list of Commands.
check(len(STARTER) >= 6 and STARTER[0].action == "ping", "STARTER runtime catalog intact")

# CATALOG integrity.
keys = [e.buy_key for e in CATALOG]
ids = [e.id for e in CATALOG]
check(len(set(keys)) == len(keys), "buy_keys are unique")
check(len(set(ids)) == len(ids), "ids are unique")
for e in CATALOG:
    check(e.karma in KARMA, f"{e.id}: karma '{e.karma}' valid")
    check(e.tier in TIERS, f"{e.id}: tier {e.tier} valid")
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

# display() shape + item-list view.
d = ns.display()
for key in ("buy_key", "label", "description", "category", "tier", "tier_name",
            "karma", "syntax", "cost", "enabled"):
    check(key in d, f"display() has '{key}'")
check(d["tier_name"] == "Pure Interaction", "tier_name resolved from TIERS")

view = catalog_view()  # enabled_only=True
view_keys = {v["buy_key"] for v in view}
check("nameship" in view_keys, "enabled event in /catalog view")
check("khaak" not in view_keys, "disabled (tier-2) event excluded from default view")
check(len(catalog_view(enabled_only=False)) == len(CATALOG), "full view includes all")

print("\n" + ("ALL PASS" if ok else "SOME FAILED"))
sys.exit(0 if ok else 1)
