#!/usr/bin/env python3
"""Validate the forward economy schema stub (StoreEvent / CATALOG / projections).
Keeps the schema from rotting; not a test of runtime behaviour (that's M4.0)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from twitch_bridge.catalog import (  # noqa: E402
    CATALOG, KARMA, KINDS, STARTER, STATUS, TIERS, StoreEvent, catalog_view)

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

print("\n" + ("ALL PASS" if ok else "SOME FAILED"))
sys.exit(0 if ok else 1)
