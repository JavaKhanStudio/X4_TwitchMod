"""Buyable-ship registry: the list behind `!buy ship <name>`.

`ships.json` is GENERATED from the X4 game data by `tools/gen_ships.py` — one row
per named warship with its real macro + in-game credit value. The coin price scales
with that value (`coins = credits / SHIP_COIN_DIVISOR`), so an expensive ship costs
proportionally more. Re-run the generator after installing a DLC to add its ships.

Kept dependency-free and pure so it is unit-testable and the economy engine can look
a ship up, price it, and hand its macro to X4 (which spawns it).
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

# coins = round(credits / DIVISOR), floored at MIN. Tune here (no regen needed):
# e.g. a ~620k-credit Nemesis => ~2070 coins, an 8M destroyer => ~27k coins.
SHIP_COIN_DIVISOR = 300
SHIP_MIN_COINS = 150


@dataclass(frozen=True)
class Ship:
    key: str        # what viewers type: !buy ship <key>  (lowercased ship name)
    label: str      # display name, e.g. "Nemesis"
    macro: str      # X4 macro the MD spawns via macro.{$macro}
    credits: int    # in-game average price (drives the coin price)
    size: str       # S / M / L / XL
    role: str       # fighter / corvette / destroyer / carrier / ...

    @property
    def coins(self) -> int:
        return max(SHIP_MIN_COINS, round(self.credits / SHIP_COIN_DIVISOR))


def _load() -> dict[str, Ship]:
    path = Path(__file__).with_name("ships.json")
    try:
        rows = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    out: dict[str, Ship] = {}
    for r in rows:
        try:
            out[r["key"]] = Ship(r["key"], r["label"], r["macro"], int(r["credits"]),
                                 r.get("size", "?"), r.get("role", "ship"))
        except (KeyError, TypeError, ValueError):
            continue
    return out


SHIPS: dict[str, Ship] = _load()


def resolve(query: str) -> tuple[Ship | None, list[Ship]]:
    """Map a viewer's text to a ship. Returns (ship, suggestions):
    a unique match -> (ship, []); ambiguous -> (None, candidates); miss -> (None, [])."""
    q = " ".join((query or "").split()).lower()
    if not q:
        return None, []
    if q in SHIPS:
        return SHIPS[q], []
    pref = sorted((s for s in SHIPS.values() if s.key.startswith(q)), key=lambda s: s.credits)
    if len(pref) == 1:
        return pref[0], []
    if pref:
        return None, pref
    sub = sorted((s for s in SHIPS.values() if q in s.key), key=lambda s: s.credits)
    if len(sub) == 1:
        return sub[0], []
    return None, sub


def listing() -> list[Ship]:
    """All ships, cheapest first."""
    return sorted(SHIPS.values(), key=lambda s: s.credits)


def sample(n: int = 6) -> list[Ship]:
    """A price-spread sample (cheapest..priciest) for a compact chat hint."""
    ships = listing()
    if len(ships) <= n:
        return ships
    step = (len(ships) - 1) / (n - 1)
    return [ships[round(i * step)] for i in range(n)]
