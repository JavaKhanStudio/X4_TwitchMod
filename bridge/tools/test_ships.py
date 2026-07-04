#!/usr/bin/env python3
"""Ship registry (ships.py + generated ships.json) unit tests."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from twitch_bridge import ships  # noqa: E402

ok = True


def check(c, m):
    global ok
    print(("PASS: " if c else "FAIL: ") + m)
    ok = ok and c


check(len(ships.SHIPS) > 20, f"registry loaded from ships.json ({len(ships.SHIPS)} ships)")
check("nemesis" in ships.SHIPS, "nemesis present")
check("katana" in ships.SHIPS, "katana present")

nem = ships.SHIPS["nemesis"]
check(nem.macro.startswith("ship_par_m_corvette"), f"nemesis macro is a paranid corvette ({nem.macro})")
check(nem.coins == max(ships.SHIP_MIN_COINS, round(nem.credits / ships.SHIP_COIN_DIVISOR)),
      "coin price = credits / divisor (floored)")
kat = ships.SHIPS["katana"]
check(kat.macro == "ship_ter_m_corvette_01_a_macro", "katana macro is the terran corvette")
check(kat.coins > nem.coins, "pricier ship costs more coins (katana > nemesis)")

# resolve: exact / unique-prefix / miss / ambiguous
s, sug = ships.resolve("katana")
check(s is not None and s.key == "katana" and sug == [], "resolve exact match")
s, sug = ships.resolve("nemes")
check(s is not None and s.key == "nemesis", "resolve unique prefix")
s, sug = ships.resolve("  KATANA ")
check(s is not None and s.key == "katana", "resolve is case/space-insensitive")
s, sug = ships.resolve("zzzzznope")
check(s is None and sug == [], "resolve miss -> no ship, no suggestions")
s, sug = ships.resolve("ra")   # rapier/raptor/rattlesnake/ray ...
check(s is None and len(sug) >= 2, f"ambiguous prefix -> suggestions ({[x.key for x in sug]})")

check(len(ships.sample(6)) == 6, "sample returns a 6-ship spread")
check(ships.sample(6)[0].credits <= ships.sample(6)[-1].credits, "sample spans cheap -> pricey")

print("\n" + ("ALL PASS" if ok else "SOME FAILED"))
sys.exit(0 if ok else 1)
