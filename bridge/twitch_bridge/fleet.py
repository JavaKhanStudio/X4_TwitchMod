"""The player's fleet as the bridge sees it, plus who has adopted what.

X4 publishes its ship roster over the pipe (MD cue `Twitch_PublishFleet`, every 45s
and after each adoption). This module holds that roster, prices each ship for
adoption, and records adoptions so a viewer keeps their ship across restarts.

WIRE FORMAT — one flat string, rows joined by ';', fields by '|':

    IDCODE|MACRO|SIZE ; IDCODE|MACRO|SIZE ; ...

Every field is engine-generated (id codes are `AAA-123`, macros are identifiers,
size is one letter), so none of them can contain a delimiter or a quote. Ship NAMES
are deliberately absent: they are player- and viewer-editable, and MD builds its
JSON by string concatenation, so a ship called `foo"bar` would corrupt the line.
The type label comes from the macro via the ships.py registry instead.

The **id code is the join key** in both directions: it is what chat types, what the
bridge stores, and what MD matches a ship on. Names are display only.

WHO OWNS THE TRUTH: the game owns the fleet, this module owns the adoptions. MD is
stateless about adoption — it just renames the ship it is told to. That keeps the MD
side trivial, at the cost that loading an OLD savegame leaves adoptions here that
never happened in that timeline; `prune_missing()` clears the ones whose ship is no
longer in the roster.
"""

from __future__ import annotations

import json
import os
import tempfile
import time
from dataclasses import asdict, dataclass
from pathlib import Path

from . import sectors as sectorreg
from . import ships as shipreg

# Adoption is a claim on an existing ship, not a purchase of one, so it is priced at
# a fraction of what buying the same hull costs (ships.py uses /300). Same registry,
# same scaling — an S-class fighter is pocket change, a battleship is an event.
ADOPT_COIN_DIVISOR = 1200
ADOPT_MIN_COINS = 100
# Fallback when the macro is not in ships.json (miners, traders, DLC hulls the
# generator didn't cover). Keyed by the size letter MD sends.
ADOPT_SIZE_PRICE = {"S": 150, "M": 500, "L": 1800, "XL": 4500}
ADOPT_UNKNOWN_PRICE = 500

# Hull classes, smallest first — the order MD's size letters come in and the order
# chat sees them listed. '?' is not here on purpose: it means MD could not class the
# ship, so it is never something a viewer can ask for by name.
SIZES = ["S", "M", "L", "XL"]
# What chat types for each. Normalised the same way as everything else viewer-typed:
# lowercased, non-alphanumerics dropped, so "X-L" and "extra large" both land.
SIZE_ALIASES = {
    "s": "S", "small": "S", "scout": "S", "fighter": "S",
    "m": "M", "med": "M", "medium": "M",
    "l": "L", "large": "L", "big": "L",
    "xl": "XL", "xlarge": "XL", "extralarge": "XL", "huge": "XL", "capital": "XL",
}


def parse_size(token: str) -> str | None:
    """A chat token -> a canonical hull class, or None if it isn't one."""
    norm = "".join(c for c in (token or "").lower() if c.isalnum())
    return SIZE_ALIASES.get(norm)


# Rebuilding costs MORE than adopting the same hull did: dying has to hurt, or a
# wreck is just a small toll. Multiplies the hull's adoption price.
RESURRECT_MULTIPLIER = 1.5

# One ship per viewer. Adoption is meant to give a viewer ONE thing in the game to
# care about; letting someone hoard six ships turns the roster into a land grab and
# starves everyone else, since the fleet is small and shared. A WRECK still counts as
# held — you resurrect it or !abandon it before taking another, which is exactly what
# gives abandon a purpose.
MAX_ADOPTIONS_PER_VIEWER = 1

# How many adoption events the companion keeps. Append-only history, newest last;
# old entries fall off the front so the file cannot grow without bound on a long-
# running channel.
HISTORY_LIMIT = 1000


@dataclass(frozen=True)
class LostShip:
    """An adopted ship that is no longer in the fleet, kept so it can be rebuilt.

    `macro` is why this record exists: once a ship is gone the roster can't tell us
    what it was, and the macro is the only thing needed to build the replacement. MD
    captures it inside the destroyed event, where the object is still readable."""
    idcode: str
    macro: str
    size: str
    owner: str          # the viewer who adopted it (lowercased)
    killer: str = ""    # faction display name, or "" when it just vanished


@dataclass(frozen=True)
class FleetShip:
    idcode: str          # "PSF-481" — the join key, what chat types
    macro: str           # X4 macro, looked up in ships.json for a label + price
    size: str            # S / M / L / XL (from MD; '?' if it couldn't be classed)
    # Live status, refreshed with every roster (every 45s). -1 means "the game did
    # not say" — an older mod build, or a ship with no readable value — which must
    # not be shown as 0% and read as "about to explode".
    hull: int = -1       # 0..100
    shield: int = -1     # 0..100
    sector_macro: str = ""   # token; named via sectors.json, never sent as text

    @property
    def sector(self) -> str:
        """Human sector name, or "" when unknown. The macro is the wire form; the
        name is looked up here so no display text ever crosses the pipe."""
        if not self.sector_macro:
            return ""
        for s in sectorreg.SECTORS.values():
            if s.macro.lower() == self.sector_macro.lower():
                return s.label
        return self.sector_macro

    @property
    def condition(self) -> str:
        """"hull 87%, shields 100%" — omitting whatever the game didn't report."""
        bits = []
        if self.hull >= 0:
            bits.append(f"hull {self.hull}%")
        if self.shield >= 0:
            bits.append(f"shields {self.shield}%")
        return ", ".join(bits)

    @property
    def _known(self) -> shipreg.Ship | None:
        return shipreg.MACROS.get(self.macro.lower())

    @property
    def label(self) -> str:
        """Ship TYPE, e.g. "Nemesis" — never the in-game name (never transmitted)."""
        k = self._known
        if k is not None:
            return k.label
        return _label_from_macro(self.macro)

    @property
    def role(self) -> str:
        k = self._known
        return k.role if k is not None else "ship"

    @property
    def coins(self) -> int:
        k = self._known
        if k is not None:
            return max(ADOPT_MIN_COINS, round(k.credits / ADOPT_COIN_DIVISOR))
        return ADOPT_SIZE_PRICE.get(self.size.upper(), ADOPT_UNKNOWN_PRICE)


def _pct(parts: list[str], i: int) -> int:
    """Roster column `i` as a 0-100 percentage, -1 if absent or unreadable."""
    try:
        return max(0, min(100, round(float(parts[i]))))
    except (IndexError, TypeError, ValueError):
        return -1


def _label_from_macro(macro: str) -> str:
    """Best-effort display name for a hull ships.json doesn't know.

    `ship_arg_m_frigate_01_a_macro` -> "Arg Frigate 01". Ugly but honest: it tells a
    viewer what they are looking at instead of showing a raw engine identifier."""
    parts = [p for p in macro.lower().replace("_macro", "").split("_") if p]
    if parts and parts[0] == "ship":
        parts = parts[1:]
    drop = {"s", "m", "l", "xl", "a", "b", "c", "d"}
    kept = [p for p in parts if p not in drop]
    return " ".join(p.capitalize() for p in kept) or macro


class Fleet:
    """Roster + adoption registry. Pure and file-backed; no I/O beyond its own JSON."""

    def __init__(self, path: str | os.PathLike | None = None, clock=time.time):
        self.path = Path(path) if path else None
        self.clock = clock
        self.ships: dict[str, FleetShip] = {}      # idcode -> ship (latest roster)
        self.adoptions: dict[str, str] = {}        # idcode -> viewer (lowercased)
        self.lost: dict[str, LostShip] = {}        # idcode -> destroyed/gone, rebuildable
        # Append-only record of everything that ever happened to an adopted ship, so
        # the streamer can see who had what and how it ended long after the ship and
        # the adoption are gone. Never read back into game logic — this is a log.
        self.history: list[dict] = []
        self.total = 0                             # ships the game reports owning
        self.sent = 0                              # ships that fit in the roster line
        self.seen = False                          # has the game ever published?
        self.load()

    # -- roster (from X4) ---------------------------------------------------
    def update(self, msg: dict) -> int:
        """Apply a `fleet` message. Returns the number of ships in the roster."""
        data = str(msg.get("data") or "")
        ships: dict[str, FleetShip] = {}
        for row in data.split(";"):
            if not row:
                continue
            parts = row.split("|")
            if len(parts) < 3:
                continue                            # malformed row: skip, keep the rest
            idcode, macro, size = parts[0].strip(), parts[1].strip(), parts[2].strip()
            if not idcode:
                continue
            # Columns 4-6 are newer than the first roster format; a mod build that
            # predates them simply sends three fields and the status stays unknown.
            ships[idcode] = FleetShip(idcode, macro, size or "?",
                                      hull=_pct(parts, 3), shield=_pct(parts, 4),
                                      sector_macro=parts[5].strip() if len(parts) > 5 else "")
        self.ships = ships
        self.total = int(msg.get("total") or len(ships))
        self.sent = int(msg.get("sent") or len(ships))
        self.seen = True
        return len(ships)

    @property
    def truncated(self) -> bool:
        """True when the game owns more ships than one roster line could carry."""
        return self.total > self.sent

    # -- lookup -------------------------------------------------------------
    def available(self, size: str | None = None) -> list[FleetShip]:
        """Roster ships nobody has adopted yet, cheapest first.

        `size` filters to one hull class (already canonical — parse_size first)."""
        rows = (s for s in self.ships.values() if s.idcode not in self.adoptions)
        if size:
            rows = (s for s in rows if s.size.upper() == size)
        return sorted(rows, key=lambda s: (s.coins, s.idcode))

    def sizes_available(self) -> dict[str, int]:
        """How many unadopted ships per hull class, biggest-first for display."""
        counts: dict[str, int] = {}
        for s in self.available():
            counts[s.size.upper()] = counts.get(s.size.upper(), 0) + 1
        return {k: counts[k] for k in SIZES if k in counts}

    def resolve(self, query: str) -> tuple[FleetShip | None, list[FleetShip]]:
        """Chat text -> a ship. Returns (ship, suggestions).

        An ID code is exact and unambiguous, so it wins. A type name ("nemesis") is
        a convenience that only resolves when exactly one unadopted ship matches —
        otherwise the candidates come back so chat can be shown the id codes."""
        q = " ".join((query or "").split()).lower()
        if not q:
            return None, []
        for code, ship in self.ships.items():
            if code.lower() == q:
                return ship, []
        matches = [s for s in self.available() if s.label.lower() == q]
        if not matches:
            matches = [s for s in self.available() if q in s.label.lower()]
        if len(matches) == 1:
            return matches[0], []
        return None, matches[:8]

    # -- adoptions ----------------------------------------------------------
    def owner_of(self, idcode: str) -> str | None:
        return self.adoptions.get(idcode)

    def resolve_adopted(self, query: str, owner: str | None = None
                        ) -> tuple[str | None, list[str]]:
        """Chat text -> an ADOPTED ship's id code. Returns (idcode, candidates).

        Separate from resolve() because that one deliberately searches what is still
        AVAILABLE. Here the opposite set is wanted, and it must include ships that
        have dropped out of the roster entirely — a destroyed ship is precisely the
        one someone wants to let go of, and it would be unreleasable otherwise."""
        q = " ".join((query or "").split()).lower()
        if not q:
            return None, []
        pool = [c for c, who in self.adoptions.items()
                if owner is None or who == owner.lower()]
        for code in pool:
            if code.lower() == q:
                return code, []
        named = [c for c in pool
                 if (self.ships[c].label.lower() == q) if c in self.ships]
        if not named:
            named = [c for c in pool if c in self.ships and q in self.ships[c].label.lower()]
        if len(named) == 1:
            return named[0], []
        return None, named[:8]

    def ships_of(self, user: str) -> list[str]:
        u = (user or "").lower()
        return [c for c, who in self.adoptions.items() if who == u]

    def at_limit(self, user: str) -> list[str]:
        """The ships already blocking this viewer from adopting, if any."""
        held = self.ships_of(user)
        return held if len(held) >= MAX_ADOPTIONS_PER_VIEWER else []

    def log(self, event: str, user: str, idcode: str, **extra) -> None:
        """Record one adoption-lifecycle event. `label` is resolved here so the log
        still reads sensibly after the ship (and its roster entry) is long gone."""
        known = self.ships.get(idcode) or (
            FleetShip(idcode, self.lost[idcode].macro, self.lost[idcode].size)
            if idcode in self.lost else None)
        row = {"at": round(self.clock()), "event": event, "user": (user or "").lower(),
               "idcode": idcode, "label": known.label if known else ""}
        row.update({k: v for k, v in extra.items() if v})
        self.history.append(row)
        del self.history[:-HISTORY_LIMIT]

    def adopt(self, user: str, idcode: str) -> None:
        self.adoptions[idcode] = (user or "").lower()
        self.log("adopted", user, idcode)
        self.save()

    def release(self, idcode: str, event: str = "released") -> None:
        """Undo an adoption — abandoning, or rolling back a command X4 refused."""
        owner = self.adoptions.get(idcode, "")
        self.lost.pop(idcode, None)
        if self.adoptions.pop(idcode, None) is not None:
            self.log(event, owner, idcode)
            self.save()

    def prune_missing(self) -> list[str]:
        """Move adoptions whose ship left the roster into the LOST list.

        This used to release them outright, which quietly made resurrection
        impossible: a destroyed ship was un-adopted within one 45s poll, so by the
        time its owner typed !resurrect there was nothing left to rebuild.

        A ship normally announces its own death (MD's Twitch_ShipDown), which records
        the killer too. This is the catch-all for the cases that produce no event —
        destroyed while the companion was down, sold, captured. They become lost
        rather than released because lost is recoverable and released is not; the
        owner can always !abandon a wreck they don't want."""
        if not self.seen or self.truncated:
            return []                # a partial roster is not evidence of absence
        gone = [c for c in self.adoptions if c not in self.ships and c not in self.lost]
        for c in gone:
            self.mark_lost(c)
        return gone

    # -- destroyed ships ----------------------------------------------------
    def mark_lost(self, idcode: str, macro: str = "", killer: str = "") -> LostShip | None:
        """Record an adopted ship as destroyed/gone. Returns the record, or None if
        the ship wasn't adopted (nobody to rebuild it for)."""
        owner = self.adoptions.get(idcode)
        if owner is None:
            return None
        known = self.ships.get(idcode)
        rec = LostShip(idcode=idcode,
                       macro=macro or (known.macro if known else ""),
                       size=known.size if known else "?",
                       owner=owner, killer=killer)
        self.lost[idcode] = rec
        self.log("destroyed", owner, idcode, killer=killer)
        self.save()
        return rec

    def card(self, idcode: str) -> dict:
        """One ship flattened for the companion UI: id, type, state, condition.

        Lives here rather than in the dashboard so the moderation table and
        /api/adoptions cannot disagree about a ship's state, and so it can be tested
        without standing up an HTTP server."""
        ship = self.ships.get(idcode)
        wreck = self.lost.get(idcode)
        label = (ship.label if ship is not None
                 else (FleetShip(idcode, wreck.macro, wreck.size).label
                       if wreck is not None else ""))
        return {
            "idcode": idcode,
            "label": label,
            # "missing" is not "destroyed": a ship can drop off the roster without
            # anyone reporting a death (companion down, sold, captured), and showing
            # that as destroyed would invent a killer that never existed.
            "state": ("destroyed" if wreck is not None
                      else "flying" if ship is not None else "missing"),
            # A wreck reports NO condition. Whatever the last roster said about its
            # hull is from before it died, and showing "hull 55%" beside "destroyed"
            # is worse than showing nothing.
            "hull": ship.hull if (ship is not None and wreck is None) else -1,
            "shield": ship.shield if (ship is not None and wreck is None) else -1,
            "sector": ship.sector if (ship is not None and wreck is None) else "",
            "killer": wreck.killer if wreck is not None else "",
            "rebuild": self.resurrect_cost(wreck) if wreck is not None else 0,
        }

    def lost_of(self, user: str) -> list[LostShip]:
        u = (user or "").lower()
        return [r for r in self.lost.values() if r.owner == u]

    def resurrect_cost(self, rec: LostShip) -> int:
        """Priced off the same hull value as adoption, times the death penalty."""
        ship = FleetShip(rec.idcode, rec.macro, rec.size)
        return max(ADOPT_MIN_COINS, round(ship.coins * RESURRECT_MULTIPLIER))

    def rebuilt(self, old: str, new: str) -> str | None:
        """X4 built the replacement: move the adoption from the old id code to the
        new one. A rebuilt ship is a NEW object with a NEW id code — the old code
        never comes back, so the registry has to be re-keyed, not reused."""
        rec = self.lost.pop(old, None)
        owner = self.adoptions.pop(old, None) or (rec.owner if rec else None)
        if owner is None:
            return None
        self.adoptions[new] = owner
        self.log("rebuilt", owner, new, was=old)
        self.save()
        return owner

    # -- naming -------------------------------------------------------------
    @staticmethod
    def adopted_name(user: str, ship: FleetShip) -> str:
        """The name X4 will give the ship. Composed HERE, not in MD: the bridge is
        the only side that knows the viewer's handle and the hull's type name, and
        MD then never has to concatenate viewer-supplied text."""
        return f"{user}'s {ship.label}"

    # -- persistence --------------------------------------------------------
    def load(self) -> None:
        if self.path is None or not self.path.exists():
            return
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (ValueError, OSError):
            return
        raw = data.get("adoptions")
        if isinstance(raw, dict):
            self.adoptions = {str(k): str(v).lower() for k, v in raw.items()}
        # Wrecks persist too: the chosen policy is that a lost ship stays rebuildable
        # forever, which has to mean across companion restarts as well.
        hist = data.get("history")
        if isinstance(hist, list):
            self.history = [h for h in hist if isinstance(h, dict)][-HISTORY_LIMIT:]
        for k, v in (data.get("lost") or {}).items():
            try:
                self.lost[str(k)] = LostShip(**v)
            except (TypeError, ValueError):
                continue

    def save(self) -> None:
        if self.path is None:
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=str(self.path.parent), suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump({"adoptions": self.adoptions,
                       "lost": {k: asdict(v) for k, v in self.lost.items()},
                       "history": self.history}, f)
            os.replace(tmp, self.path)   # atomic, same as wallet.py
        finally:
            if os.path.exists(tmp):
                os.unlink(tmp)
