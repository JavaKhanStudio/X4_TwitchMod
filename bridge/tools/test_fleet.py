#!/usr/bin/env python3
"""Fleet roster + ship adoption (headless).

Covers the wire format X4 sends, per-hull pricing, the claim/rollback dance around
a command X4 might refuse, and persistence of adoptions across a restart."""
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from twitch_bridge import protocol, ships  # noqa: E402
from twitch_bridge.catalog import StoreEvent  # noqa: E402
from twitch_bridge.economy import Economy  # noqa: E402
from twitch_bridge.fleet import Fleet, FleetShip  # noqa: E402
from twitch_bridge.wallet import EconomySettings, Wallet  # noqa: E402

ok = True


def check(c, m):
    global ok
    print(("PASS: " if c else "FAIL: ") + m)
    ok = ok and c


def chat(user, msg, badges=None):
    return {"t": "chat", "user": user, "msg": msg, "badges": badges or []}


def kinds(outs):
    return [o["t"] for o in outs]


# A known hull from the real registry, so pricing is checked against live data.
known = next(iter(ships.SHIPS.values()))

# ---- the wire format ------------------------------------------------------
f = Fleet()
check(not f.seen, "a fresh fleet knows the game has not published yet")
n = f.update(protocol.fleet(f"PSF-481|{known.macro}|{known.size};"
                            f"ABC-123|ship_xxx_l_miner_99_a_macro|L", total=2, sent=2))
check(n == 2 and not f.truncated, "roster parses two rows")
check(f.ships["PSF-481"].label == known.label, "known macro -> ships.json label")
check(f.ships["PSF-481"].coins == max(100, round(known.credits / 1200)),
      f"known hull priced from its value ({f.ships['PSF-481'].coins}c)")
check(f.ships["ABC-123"].coins == 1800, "unknown macro falls back to its size price (L)")
check("Miner" in f.ships["ABC-123"].label, f"unknown macro gets a readable label "
      f"({f.ships['ABC-123'].label!r})")

# malformed rows must not take the whole roster down with them
n = f.update(protocol.fleet(f"PSF-481|{known.macro}|S;;GARBAGE;|no-idcode|M", total=4, sent=4))
check(n == 1, "malformed rows are skipped, valid ones kept")

# a capped roster must be visible as capped
f.update(protocol.fleet(f"PSF-481|{known.macro}|S", total=300, sent=1))
check(f.truncated, "total > sent reads as truncated")

# ---- pricing scales with the hull ----------------------------------------
rows = ";".join(f"{c}|ship_zzz_{sz.lower()}_hull_01_a_macro|{sz}"
                for c, sz in [("AAA-001", "S"), ("BBB-002", "M"),
                              ("CCC-003", "L"), ("DDD-004", "XL")])
f.update(protocol.fleet(rows, total=4, sent=4))
prices = [f.ships[c].coins for c in ("AAA-001", "BBB-002", "CCC-003", "DDD-004")]
check(prices == sorted(prices) and len(set(prices)) == 4,
      f"price rises strictly with hull size {prices}")

# ---- adoption through the economy ----------------------------------------
ev = StoreEvent(id="adopt_ship", buy_key="adopt", fleet_picker=True, karma="good",
                tier=0, args=["idcode", "name"], label="Adopt", enabled=True)
store = Path(tempfile.mkdtemp()) / "adoptions.json"
fl = Fleet(store)
fl.update(protocol.fleet(f"PSF-481|{known.macro}|{known.size};"
                         f"ABC-123|ship_xxx_s_scout_01_a_macro|S", total=2, sent=2))
w = Wallet(tempfile.mktemp(suffix=".json"), EconomySettings(min_purchase_price=10),
           clock=lambda: 0)
econ = Economy(w, [ev], clock=lambda: 0.0, fleet=fl)
w.get("ana").coins = 100000

o = econ.handle_chat(chat("ana", "!buy adopt"))
check(kinds(o) == ["say"] and "PSF-481" in o[0]["msg"], "'!buy adopt' lists ID codes + prices")

o = econ.handle_chat(chat("ana", "!buy adopt PSF-481"))
check(kinds(o) == ["cmd", "say"], "adopting emits a cmd + a confirmation")
check(o[0]["id"] == "adopt_ship" and o[0]["argv"] == ["PSF-481", f"ana's {known.label}"],
      f"cmd carries (idcode, composed name) IN ORDER — got {o[0]['argv']}")
check(fl.owner_of("PSF-481") == "ana", "adoption recorded")
check(w.get("ana").coins < 100000, "coins were taken")

# a second viewer cannot take the same ship
o = econ.handle_chat(chat("bo", "!buy adopt PSF-481"))
check(kinds(o) == ["say"] and "taken" in o[0]["msg"], "an adopted ship is refused to others")

# lowercase / by type name both resolve
o = econ.handle_chat(chat("bo", "!buy adopt abc-123"))
check(kinds(o) == ["cmd", "say"], "ID code matching is case-insensitive")

# ---- !fleet size filter ---------------------------------------------------
mix = ";".join(["SSS-001|ship_zzz_s_hull_01_a_macro|S",
                "SSS-002|ship_zzz_s_hull_01_a_macro|S",
                "MMM-001|ship_zzz_m_hull_01_a_macro|M",
                "XXX-001|ship_zzz_xl_hull_01_a_macro|XL"])
fl.update(protocol.fleet(mix, total=4, sent=4))

o = econ.handle_chat(chat("ana", "!fleet XL"))
check("XXX-001" in o[0]["msg"] and "SSS-001" not in o[0]["msg"],
      "!fleet XL shows only the XL ship")
o = econ.handle_chat(chat("ana", "!fleet s"))
check("SSS-001" in o[0]["msg"] and "XXX-001" not in o[0]["msg"],
      "the filter is case-insensitive")
o = econ.handle_chat(chat("ana", "!fleet capital"))
check("XXX-001" in o[0]["msg"], "word aliases resolve (capital -> XL)")
o = econ.handle_chat(chat("ana", "!fleet L"))
check("no L-class" in o[0]["msg"] and "S x2" in o[0]["msg"],
      f"an empty class says so and lists what IS there — {o[0]['msg']}")
o = econ.handle_chat(chat("ana", "!fleet banana"))
check("isn't a hull class" in o[0]["msg"], "a non-class token is rejected, not silently ignored")
o = econ.handle_chat(chat("ana", "!fleet"))
check(all(c in o[0]["msg"] for c in ("SSS-001", "MMM-001", "XXX-001")),
      "bare !fleet still shows every class")
check("!fleet S" in o[0]["msg"], "bare !fleet advertises the filter")

# with only one class left, the hint would be noise
fl.update(protocol.fleet("SSS-001|ship_zzz_s_hull_01_a_macro|S", total=1, sent=1))
o = econ.handle_chat(chat("ana", "!fleet"))
check("filter with" not in o[0]["msg"], "no filter hint when there is only one class")

fl.update(protocol.fleet(f"PSF-481|{known.macro}|{known.size};"
                         f"ABC-123|ship_xxx_s_scout_01_a_macro|S", total=2, sent=2))
o = econ.handle_chat(chat("ana", "!myship"))
check("PSF-481" in o[0]["msg"], "!myship lists what you adopted")
o = econ.handle_chat(chat("ana", "!fleet"))
check("already adopted" in o[0]["msg"] or "PSF-481" not in o[0]["msg"],
      "!fleet no longer offers adopted ships")

# ---- abandoning ------------------------------------------------------------
w.get("ana").coins = 100000
fl.update(protocol.fleet(f"PSF-481|{known.macro}|{known.size};"
                         f"ABC-123|ship_xxx_s_scout_01_a_macro|S;"
                         f"NEW-777|ship_xxx_s_scout_01_a_macro|S", total=3, sent=3))
paid = w.get("ana").coins

o = econ.handle_chat(chat("ana", "!abandon"))
check(kinds(o) == ["cmd", "say"], "abandon emits a cmd + a confirmation")
check(o[0]["id"] == "abandon_ship" and o[0]["argv"] == ["PSF-481"],
      f"abandon sends ONE arg, the id code — got {o[0]['argv']}")
check(fl.owner_of("PSF-481") is None, "the claim is released")
check(w.get("ana").coins == paid, "abandoning is free and does NOT refund")
check(any(s.idcode == "PSF-481" for s in fl.available()), "the ship is adoptable again")

o = econ.handle_chat(chat("ana", "!abandon"))
check(kinds(o) == ["say"] and "haven't adopted" in o[0]["msg"],
      "abandoning with nothing adopted just says so")

# Holding two ships is no longer reachable through chat (one per viewer), but it is
# still reachable as GRANDFATHERED data — anyone who adopted several before the limit
# existed keeps them until they let them go. Seeded directly, because that is exactly
# how such a registry arrives: loaded from disk, not built by a purchase.
econ.handle_chat(chat("ana", "!buy adopt PSF-481"))
fl.adoptions["NEW-777"] = "ana"
o = econ.handle_chat(chat("ana", "!abandon"))
check(kinds(o) == ["say"] and "which one" in o[0]["msg"] and "PSF-481" in o[0]["msg"],
      "with two ships, a bare !abandon asks which")
o = econ.handle_chat(chat("ana", "!abandon new-777"))
check(kinds(o) == ["cmd", "say"] and fl.owner_of("NEW-777") is None,
      "!abandon <ID> is case-insensitive")
# you cannot disown someone else's ship, but a moderator can
w.get("bo").coins = 100000
econ.handle_chat(chat("bo", "!abandon"))     # bo still holds ABC-123 from earlier
o = econ.handle_chat(chat("bo", "!buy adopt NEW-777"))
check(kinds(o) == ["cmd", "say"], "(setup) bo adopts NEW-777")
o = econ.handle_chat(chat("ana", "!abandon NEW-777"))
check(kinds(o) == ["say"] and "belongs to @bo" in o[0]["msg"],
      "a viewer cannot abandon someone else's ship")
check(fl.owner_of("NEW-777") == "bo", "...and the claim survives the attempt")
o = econ.handle_chat(chat("mod", "!abandon NEW-777", badges=["moderator"]))
check(kinds(o) == ["cmd", "say"] and fl.owner_of("NEW-777") is None,
      "a moderator can release anyone's ship")
check("@bo's" in o[1]["msg"], "...and chat is told whose it was")

# a ship that has left the roster entirely must still be releasable — that is
# exactly the ship someone wants to let go of
fl.adoptions["GONE-01"] = "ana"
o = econ.handle_chat(chat("ana", "!abandon GONE-01"))
check(kinds(o) == ["cmd", "say"] and fl.owner_of("GONE-01") is None,
      "an adoption whose ship is gone can still be abandoned")

o = econ.handle_chat(chat("ana", "!abandon ZZZ-000"))
check(kinds(o) == ["say"] and "no adopted ship" in o[0]["msg"],
      "abandoning something you never had is explained, not silent")

# ---- one ship per viewer ---------------------------------------------------
fl.update(protocol.fleet(f"ONE-001|{known.macro}|{known.size};"
                         f"ONE-002|{known.macro}|{known.size}", total=2, sent=2))
w.get("eve").coins = 100000
o = econ.handle_chat(chat("eve", "!buy adopt ONE-001"))
check(kinds(o) == ["cmd", "say"], "(setup) eve adopts her first ship")
before = w.get("eve").coins
o = econ.handle_chat(chat("eve", "!buy adopt ONE-002"))
check(kinds(o) == ["say"] and "you already have a ship" in o[0]["msg"],
      f"a second adoption is refused — {o[0]['msg']}")
check(w.get("eve").coins == before, "the refused second adoption costs nothing")
check(fl.owner_of("ONE-002") is None, "...and does not claim the ship")

# a WRECK still counts as held: you resurrect it or let it go first
econ.handle_ship_down(protocol.shipdown("ONE-001", known.macro, "Xenon"))
o = econ.handle_chat(chat("eve", "!buy adopt ONE-002"))
check(kinds(o) == ["say"] and "already have a ship" in o[0]["msg"],
      "a destroyed ship still counts against the limit")
econ.handle_chat(chat("eve", "!abandon ONE-001"))
o = econ.handle_chat(chat("eve", "!buy adopt ONE-002"))
check(kinds(o) == ["cmd", "say"], "after abandoning, a new adoption is allowed")
econ.handle_chat(chat("eve", "!abandon ONE-002"))

# ---- the adoption record ---------------------------------------------------
events = [h["event"] for h in fl.history if h["user"] == "eve"]
check(events == ["adopted", "destroyed", "abandoned", "adopted", "abandoned"],
      f"every lifecycle step is recorded in order — {events}")
rec = next(h for h in fl.history if h["user"] == "eve" and h["event"] == "destroyed")
check(rec["killer"] == "Xenon" and rec["label"] == known.label,
      "the record keeps the ship TYPE and the killer, not just an id code")
check(all(h.get("at") for h in fl.history), "every entry is timestamped")

# the record outlives the adoption AND the companion
fl5 = Fleet(store)
kept = [h for h in fl5.history if h["user"] == "eve"]
check(len(kept) == 5, "the record survives a companion restart")
check(fl5.owner_of("ONE-002") is None, "...even though the adoption itself is gone")

# ---- live status on the roster ---------------------------------------------
from twitch_bridge import sectors as sectorreg  # noqa: E402

somesector = next(iter(sectorreg.SECTORS.values()))
fl.update(protocol.fleet(f"STA-001|{known.macro}|{known.size}|87|100|{somesector.macro};"
                         f"OLD-001|{known.macro}|{known.size}", total=2, sent=2))
st = fl.ships["STA-001"]
check(st.hull == 87 and st.shield == 100, "hull/shield come off the roster")
check(st.sector == somesector.label,
      f"the sector MACRO is named from sectors.json ({st.sector!r})")
check(st.condition == "hull 87%, shields 100%", f"condition reads well ({st.condition!r})")
old = fl.ships["OLD-001"]
check(old.hull == -1 and old.condition == "",
      "a 3-field row (older mod build) leaves status unknown, NOT 0%")

fl.update(protocol.fleet(f"STA-001|{known.macro}|{known.size}|13|0|{somesector.macro}",
                         total=1, sent=1))
w.get("dee").coins = 100000
econ.handle_chat(chat("dee", "!buy adopt STA-001"))
o = econ.handle_chat(chat("dee", "!myship"))
check("hull 13%" in o[0]["msg"] and somesector.label in o[0]["msg"],
      f"!myship shows condition and location — {o[0]['msg']}")
o = econ.handle_chat(chat("dee", "!myship STA-001"))
check("adopted by @dee" in o[0]["msg"] and known.role in o[0]["msg"],
      f"!myship <ID> gives the detail card — {o[0]['msg']}")
o = econ.handle_chat(chat("ana", "!myship STA-001"))
check("adopted by @dee" in o[0]["msg"], "anyone can look up any ship by ID")
o = econ.handle_chat(chat("ana", "!myship NOPE-99"))
check("no ship" in o[0]["msg"], "an unknown ID is explained")
econ.handle_chat(chat("dee", "!abandon STA-001"))

# ---- the companion-UI projection (moderation table + /api/adoptions) --------
fl.update(protocol.fleet(f"CRD-001|{known.macro}|{known.size}|55|20|{somesector.macro}",
                         total=1, sent=1))
w.get("fay").coins = 100000
econ.handle_chat(chat("fay", "!buy adopt CRD-001"))
c = fl.card("CRD-001")
check(c["state"] == "flying" and c["hull"] == 55 and c["label"] == known.label
      and c["sector"] == somesector.label,
      f"a flying ship's card carries type, hull and location — {c}")
check(c["rebuild"] == 0, "a flying ship has no rebuild price")

econ.handle_ship_down(protocol.shipdown("CRD-001", known.macro, "Xenon"))
c = fl.card("CRD-001")
check(c["state"] == "destroyed" and c["killer"] == "Xenon" and c["rebuild"] > 0,
      f"a wreck's card carries the killer and what it costs to rebuild — {c}")
check(c["hull"] == -1 and c["shield"] == -1,
      "a wreck reports no condition — the last hull reading predates its death")

# a ship that just fell off the roster is MISSING, not destroyed: nothing reported a
# death, so the card must not invent a killer
fl.adoptions["MIS-001"] = "fay"
c = fl.card("MIS-001")
check(c["state"] == "missing" and c["killer"] == "",
      f"a ship that merely vanished is 'missing', not 'destroyed' — {c}")
del fl.adoptions["MIS-001"]
econ.handle_chat(chat("fay", "!abandon CRD-001"))

# ---- destroyed ships + resurrection ----------------------------------------
w.get("cara").coins = 100000
fl.update(protocol.fleet(f"DIE-001|{known.macro}|{known.size}", total=1, sent=1))
econ.handle_chat(chat("cara", "!buy adopt DIE-001"))
adopt_price = FleetShip("DIE-001", known.macro, known.size).coins

# a ship that is NOT adopted dying is nobody's business
check(econ.handle_ship_down(protocol.shipdown("NOT-ADOPTED", known.macro, "Xenon")) == [],
      "an unadopted ship's death is ignored")

out = econ.handle_ship_down(protocol.shipdown("DIE-001", known.macro, "Xenon"))
check(out and "@cara" in out[0]["msg"] and "Xenon" in out[0]["msg"],
      f"the owner is told, with the killer — {out[0]['msg'] if out else None}")
check("DIE-001" in fl.lost and fl.lost["DIE-001"].owner == "cara", "the wreck is recorded")
check(fl.owner_of("DIE-001") == "cara", "a destroyed ship is STILL adopted (not released)")

# the roster no longer lists it; prune must not quietly release the wreck
fl.update(protocol.fleet(f"OTHER-01|{known.macro}|{known.size}", total=1, sent=1))
fl.prune_missing()
check(fl.owner_of("DIE-001") == "cara" and "DIE-001" in fl.lost,
      "prune_missing leaves a known wreck alone")

o = econ.handle_chat(chat("cara", "!myship"))
check("DESTROYED" in o[0]["msg"] and "!resurrect" in o[0]["msg"],
      "!myship flags the wreck and the way to rebuild it")

want_cost = round(adopt_price * 1.5)
check(fl.resurrect_cost(fl.lost["DIE-001"]) == max(100, want_cost),
      f"rebuilding costs 1.5x the adoption price ({want_cost})")

before = w.get("cara").coins
o = econ.handle_chat(chat("cara", "!resurrect"))
check(kinds(o) == ["cmd", "say"] and o[0]["id"] == "resurrect_ship",
      "!resurrect emits the rebuild command")
check(o[0]["argv"] == ["DIE-001", known.macro],
      f"it carries (old id, macro) — got {o[0]['argv']}")
check(w.get("cara").coins == before - fl.resurrect_cost(fl.lost["DIE-001"]),
      "the rebuild was charged")
check(fl.owner_of("DIE-001") == "cara", "the claim is held until X4 confirms")

# X4 reports the new hull: the adoption is re-keyed and the new ship renamed
fl.update(protocol.fleet(f"NEW-001|{known.macro}|{known.size}", total=1, sent=1))
out = econ.handle_ship_new(protocol.shipnew("DIE-001", "NEW-001"))
check(fl.owner_of("NEW-001") == "cara" and fl.owner_of("DIE-001") is None,
      "the adoption moves to the new id code")
check("DIE-001" not in fl.lost, "the wreck record is cleared")
check(any(o["t"] == "cmd" and o["id"] == "adopt_ship"
          and o["argv"] == ["NEW-001", f"cara's {known.label}"] for o in out),
      "the rebuilt hull is renamed through the ordinary adopt path")

# a rebuild X4 refuses refunds, and the wreck stays claimed so it can be retried
econ.handle_ship_down(protocol.shipdown("NEW-001", known.macro, "Xenon"))
paid = w.get("cara").coins
econ.handle_chat(chat("cara", "!resurrect"))
check(w.get("cara").coins < paid, "(setup) a second rebuild was charged")
econ.handle_x4_failure({"t": "cmdfail", "id": "resurrect_ship", "ref": "NEW-001",
                        "reason": "the shipyard could not be reached"})
check(w.get("cara").coins == paid, "a refused rebuild refunds")
check(fl.owner_of("NEW-001") == "cara" and "NEW-001" in fl.lost,
      "a refused rebuild leaves the wreck claimed, so it can be retried")

# abandoning a wreck gives up on it entirely
econ.handle_chat(chat("cara", "!abandon NEW-001"))
check(fl.owner_of("NEW-001") is None and "NEW-001" not in fl.lost,
      "abandoning a wreck clears the claim AND the wreck")

o = econ.handle_chat(chat("cara", "!resurrect"))
check(kinds(o) == ["say"] and "none of your ships are destroyed" in o[0]["msg"],
      "!resurrect with no wreck says so")

# wrecks survive a companion restart (the chosen policy is 'forever')
fl.adoptions["KEEP-01"] = "cara"
fl.mark_lost("KEEP-01", known.macro, "Xenon")
fl4 = Fleet(store)
check("KEEP-01" in fl4.lost and fl4.lost["KEEP-01"].macro == known.macro,
      "wrecks persist across a restart, with the hull needed to rebuild them")

# ---- X4 refuses the command -> refund AND release --------------------------
before = w.get("cy").coins = 100000
fl.update(protocol.fleet("ZZZ-999|ship_xxx_s_scout_01_a_macro|S", total=1, sent=1))
o = econ.handle_chat(chat("cy", "!buy adopt ZZZ-999"))
check(kinds(o) == ["cmd", "say"] and fl.owner_of("ZZZ-999") == "cy", "claim is optimistic")
# The failure names the ship (MD sends $ref). Without that, "roll back the oldest
# pending adoption" would release ana's PSF-481 — X4 acknowledges only failures, so
# successful adoptions are never retired from the pending list.
out = econ.handle_x4_failure({"t": "cmdfail", "id": "adopt_ship", "ref": "ZZZ-999",
                              "reason": "that ship is no longer in the fleet"})
check(fl.owner_of("ZZZ-999") is None, "a refused adoption releases the claim")
check(fl.owner_of("PSF-481") == "ana", "an EARLIER successful adoption is left alone")
check(w.get("cy").coins == before, "a refused adoption refunds the coins")
check(w.get("ana").coins < 100000, "the earlier buyer is not refunded by someone else's failure")
check(out and "refunded" in out[0]["msg"], "chat is told about the refund")

# A ref-less failure must not guess at which claim to drop.
w.get("di").coins = 100000
fl.update(protocol.fleet(f"YYY-777|{known.macro}|{known.size}", total=1, sent=1))
econ.handle_chat(chat("di", "!buy adopt YYY-777"))
econ.handle_x4_failure({"t": "cmdfail", "id": "adopt_ship", "reason": "unknown"})
check(fl.owner_of("YYY-777") == "di", "a ref-less failure releases nothing rather than the wrong ship")

# ---- persistence + reconciliation -----------------------------------------
fl2 = Fleet(store)
check(fl2.owner_of("PSF-481") == "ana", "adoptions survive a companion restart")
# Own store: the shared one above has already been pruned by the resurrection tests,
# and prune_missing deliberately reports each wreck once.
pstore = Path(tempfile.mkdtemp()) / "adoptions.json"
fp = Fleet(pstore)
fp.adoptions["VAN-001"] = "ana"
fp.save()
fp.update(protocol.fleet("QQQ-000|ship_xxx_s_scout_01_a_macro|S", total=1, sent=1))
dropped = fp.prune_missing()
# NOT released — that is what used to happen, and it made resurrection impossible:
# a destroyed ship was un-adopted within one 45s poll, so by the time its owner typed
# !resurrect there was nothing to rebuild. Lost is recoverable; released is not.
check("VAN-001" in dropped and "VAN-001" in fp.lost,
      "a vanished adoption becomes a WRECK, not a release")
check(fp.owner_of("VAN-001") == "ana", "...and stays claimed by its owner")
check(fp.prune_missing() == [], "a wreck is only reported once, not every poll")
fl3 = Fleet(store)
fl3.update(protocol.fleet("QQQ-000|ship_xxx_s_scout_01_a_macro|S", total=99, sent=1))
check(fl3.prune_missing() == [], "a TRUNCATED roster never prunes (absence isn't proof)")

# ---- adoption is unavailable before the game publishes ---------------------
econ2 = Economy(w, [ev], clock=lambda: 0.0, fleet=Fleet())
o = econ2.handle_chat(chat("ana", "!buy adopt PSF-481"))
check(kinds(o) == ["say"] and "hasn't arrived" in o[0]["msg"],
      "adopting before the first roster is refused, not charged")

print("\n" + ("ALL PASS" if ok else "SOME FAILED"))
sys.exit(0 if ok else 1)
