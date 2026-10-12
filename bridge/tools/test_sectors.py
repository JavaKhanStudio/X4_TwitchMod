#!/usr/bin/env python3
"""Sector registry (sectors.py + generated sectors.json) unit tests."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from twitch_bridge import sectors  # noqa: E402

ok = True


def check(c, m):
    global ok
    print(("PASS: " if c else "FAIL: ") + m)
    ok = ok and c


check(len(sectors.SECTORS) > 100,
      f"registry loaded from sectors.json ({len(sectors.SECTORS)} sectors)")
check("argon prime" in sectors.SECTORS, "argon prime present")
check(sectors.SECTORS["argon prime"].macro == "Cluster_14_Sector001_macro",
      "argon prime carries the real X4 macro")
check("twitch" in sectors.SECTORS, "the mod's own Twitch Sector is in the registry")

# every row must have a macro MD can feed to macro.{$name}
check(all(s.macro and " " not in s.macro for s in sectors.SECTORS.values()),
      "every macro is a single bare token")
# keys must already be in canonical form, or resolve() can never match them
check(all(k == sectors.norm(k) for k in sectors.SECTORS),
      "every key is already normalised (gen_sectors.py used sectors.norm)")

# norm: apostrophes vanish so "Atiya's" and "Atiyas" agree
check(sectors.norm("Atiya's Misfortune I") == sectors.norm("atiyas   misfortune i") ==
      "atiyas misfortune i", "norm drops apostrophes and collapses spaces")

# resolve: here / exact / prefix / ambiguous / miss
s, sug, here = sectors.resolve("")
check(here and s is None, "empty query -> the player's current sector")
for word in ("here", "HERE", "current", "my sector"):
    _s, _sug, h = sectors.resolve(word)
    check(h, f"'{word}' -> the player's current sector")
s, sug, here = sectors.resolve("Argon Prime")
check(s is not None and s.key == "argon prime" and not here, "resolve exact (case-insensitive)")
s, sug, here = sectors.resolve("argon")
check(s is not None and s.key == "argon prime", "resolve unique prefix")
s, sug, here = sectors.resolve("atiya's misfortune i")
check(s is not None and s.macro == "Cluster_26_Sector001_macro", "apostrophes are accepted")
s, sug, here = sectors.resolve("grand exchange")
check(s is None and len(sug) >= 2,
      f"ambiguous prefix -> suggestions ({[x.key for x in sug]})")
s, sug, here = sectors.resolve("zzzznope")
check(s is None and sug == [] and not here, "miss -> nothing")

check(len(sectors.listing()) == len(sectors.SECTORS), "listing covers the registry")

print("\n" + ("ALL PASS" if ok else "SOME FAILED"))
sys.exit(0 if ok else 1)
