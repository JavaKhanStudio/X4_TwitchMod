"""Sector registry: turns viewer text ("argon prime") into an X4 sector MACRO.

`sectors.json` is GENERATED from the X4 game data by `tools/gen_sectors.py` — one
row per sector of the playable galaxy, with its real macro name. Re-run the
generator after installing a DLC to add its sectors.

Why the bridge does this instead of X4: the Mission Director has **no string
operations at all** (no split, no substring, no lowercase — see the `string`
datatype in scriptproperties.xml), so it cannot match "argon prime" against
anything. It CAN turn a macro-name string into a macro with `macro.{$name}`, which
is exactly what `find_sector macro="macro.{$m}"` needs. So: chat text is resolved
here, and only the macro name crosses the pipe.

Kept dependency-free and pure so it is unit-testable, mirroring ships.py.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

# Words a viewer uses for "wherever the player is right now". These resolve to the
# EMPTY macro, which the MD cues read as "use player.sector".
# NOTE "player" is deliberately NOT here: on a station buy it is the OWNER flag
# (`!buy wharf player` = player-owned, current sector), and one word cannot mean
# both the place and the owner. See economy._split_owner.
HERE_WORDS = {"", "here", "current", "me", "us", "mysector", "my sector"}

# Sectors that exist only because THIS MOD adds them (twitch_arena's maps/), so the
# generator — which reads the game's own archives — can never see them. Keep in sync
# with extensions/twitch_arena/maps/*/sectors.xml.
MOD_SECTORS = [
    {"key": "twitch", "label": "Twitch Sector", "macro": "twitchmain_sector_macro"},
]


def norm(text: str) -> str:
    """Canonical form of a sector name. Apostrophes are DROPPED (so "Atiya's" and
    "Atiyas" agree), every other non-alphanumeric becomes a space, then whitespace
    is collapsed. gen_sectors.py builds the registry keys with this same function."""
    s = "".join("" if c in "'’`´" else (c if (c.isalnum() or c.isspace()) else " ")
                for c in (text or "").lower())
    return " ".join(s.split())


@dataclass(frozen=True)
class Sector:
    key: str      # what viewers type, normalised: "argon prime"
    label: str    # display name, e.g. "Argon Prime"
    macro: str    # X4 macro the MD resolves via macro.{$macro}


def _load() -> dict[str, Sector]:
    path = Path(__file__).with_name("sectors.json")
    try:
        rows = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        rows = []
    out: dict[str, Sector] = {}
    for r in list(rows) + MOD_SECTORS:
        try:
            key = norm(r["key"])
            out[key] = Sector(key, r["label"], r["macro"])
        except (KeyError, TypeError):
            continue
    return out


SECTORS: dict[str, Sector] = _load()


def resolve(query: str) -> tuple[Sector | None, list[Sector], bool]:
    """Map viewer text to a sector. Returns (sector, suggestions, here):

      here=True                -> "" / "here" / … : the caller should target the
                                  player's current sector (empty macro to MD)
      (sector, [], False)      -> unique match
      (None, candidates, False)-> ambiguous; candidates are the near misses
      (None, [], False)        -> no such sector
    """
    q = norm(query)
    if q in HERE_WORDS:
        return None, [], True
    if q in SECTORS:
        return SECTORS[q], [], False
    pref = sorted((s for s in SECTORS.values() if s.key.startswith(q)), key=lambda s: s.key)
    if len(pref) == 1:
        return pref[0], [], False
    if pref:
        return None, pref, False
    sub = sorted((s for s in SECTORS.values() if q in s.key), key=lambda s: s.key)
    if len(sub) == 1:
        return sub[0], [], False
    return None, sub, False


def listing() -> list[Sector]:
    """All sectors, alphabetically."""
    return sorted(SECTORS.values(), key=lambda s: s.key)
