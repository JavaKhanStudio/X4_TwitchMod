# Custom factions: the five things one needs before it can own a working station

A `<faction>` added in `libraries/factions.xml` is enough to **own ships**. It is nowhere
near enough to **own a station**. A custom faction starts with no people, no economy, no
goods and no permission to sell them, and every one of those gaps fails **silently and
differently** — the station builds fine each time and is simply useless in a new way.

This is the checklist, in the order the failures surface, each with the symptom that
identifies it. Discovered the hard way building `!buy wharf` for the Twitch Allies
(2026-08-06); every item cost one live test round.

| # | Needs | File | Symptom when missing |
|---|---|---|---|
| 1 | People | `libraries/characters.xml` | Station has no manager, ship dealer or trader; `FindNPCGenerator` errors in the log |
| 2 | Staffing call | your MD | Posts empty even *with* people defined — you pre-empted the base game |
| 3 | Goods | `libraries/wares.xml` | Ship hulls list, **no equipment at all** |
| 4 | Permission | `<licences>` in `factions.xml` | Stock exists but nothing is buyable |
| 5 | Logistics | `libraries/jobs.xml` + `<account>` | Shelves start empty and never refill |

---

## 1. People — `libraries/characters.xml`

X4 resolves the NPC for a control post by looking up **(tags, faction)** in
`libraries/characters.xml`, where each entry carries
`<category tags="[…]" faction="[…]" race="…"/>`. A faction named in no entry can have no
staff at all.

```
CharacterDB::FindNPCGenerator(): unable to find NPC generator for tags shiptrader,
  race null, factions Twitch Allies
md.NPC_Instantiation.PlaceItemTrader: Twitch Wharf has a trader corner but the faction
  has no character definition for a suitable trader [Owen]
```

Note **`race null`** — `primaryrace="argon"` on the faction does *not* feed this lookup.

Fix: add the faction to the `faction="[…]"` list of every character entry the equivalent
vanilla faction can draw on — manager, ship trader, platform (trader-corner) trader, plus
service crew, marines, pilots and casuals so the place looks inhabited.
`bridge/tools/gen_characters.py` generates it.

**Caveat:** an XML diff cannot *append* to an attribute, only `<replace>` it whole, so this
file necessarily copies vanilla's faction lists — re-run the generator after a game update
or an Egosoft addition to one of those lists gets overwritten. DLC-defined character ids
are emitted `silent="true"` so the diff doesn't error for someone who lacks that DLC.

## 2. Staffing — let `'init station'` do it

```xml
<signal_objects object="player.galaxy" param="'init station'" param2="$Station" param3="true"/>
```

This runs `inituniverse.xml`'s `InitStationActions`, which adds workforce, trade wares,
ammo, the defence and engineer NPCs, **and the ship dealer and trade manager**. Two traps:

- **`param3`** is named `$gamestartstation` but *means* "arrived complete rather than built
  over time". It gates the entire workforce block — with `false` the station hires
  **nobody, ever**. `finalisestations.xml`, the base game's own build-it-complete path,
  passes `true`.
- **Creating a manager yourself poisons it.** `CreateTradeManagerEntity` is guarded by
  `not $controllable.tradenpc.exists`, and `signal_objects` is *queued* while your
  remaining actions run immediately — so your manager always wins the race and vanilla
  skips the trader's corner and never reaches the ship dealer.

`InitStation` deliberately skips `owner == faction.player` (vanilla staffs player stations
from `event_player_built_station`, which an MD-created station never fires), so
**player-owned stations, and only those, must be staffed by hand.**

## 3. Goods — `libraries/wares.xml`

Every ware lists the factions that have it via `<owner faction="…"/>`. A faction in no list
stocks nothing. Symptom is distinctive: **ship hulls all list** (they are built to order)
while **equipment lists nothing** (it has to exist).

Scope the grant by the game's own `<restriction licence="…">` — `generaluseequipment`,
`militaryequipment`, optionally `capitalequipment` for L/XL — rather than a hard-coded ware
list, so it follows future ware additions. Exclude wares owned only by `xenon`/`khaak`
unless alien hardware on the shelves is intended. `bridge/tools/gen_ware_owners.py`
generates it.

Unlike #1 this diff uses `<add>`, which **appends** an `<owner>` element (vanilla always
keeps `<owner>` last inside `<ware>`), so it never rewrites a vanilla list and cannot drift.

## 4. Permission — `<licences>` in `factions.xml`

A faction may only sell a restricted ware to someone holding a licence **of that type,
issued by that faction**. A faction with no `<licences>` block cannot issue one, so its
stock is unbuyable no matter how full the shelves are.

Every vanilla faction that owns a tradeable station has this block. The ones without it —
`civilian`, `criminal`, `outlaw`, `smuggler`, `xenon`, `khaak` — are exactly the factions
that sell nothing. That correlation is the tell.

```xml
<licences>
  <licence type="generaluseequipment" name="{90042,21}" minrelation="-0.01" tags="basic"/>
  <licence type="generaluseship"      name="{90042,25}" minrelation="-0.01" tags="basic"/>
  <licence type="militaryequipment"   name="{90042,23}" minrelation="-0.01"/>
  <licence type="capitalequipment"    name="{90042,27}" minrelation="-0.01"/>
</licences>
```

`minrelation` is what the player must reach to hold it. Put the names on **your own text
page**, not a borrowed vanilla ref. Child order is fixed by `factions.xsd`:
**color, account, icon, licences, relations**.

The second `<licence type="…" factions="a b c"/>` form is different — it means "this
faction honours licences of that type granted by those factions". Don't confuse the two;
the `name` attribute is documented as *"Do not use with 'faction' attribute"*.

## 5. Logistics — `libraries/jobs.xml` + `<account>`

A dock does not conjure equipment: it **builds it from components**, hauled in by the
owning faction's equipment traders. `<basket basket="equipment"/>` is the 11 wares that
feed exactly this (advancedelectronics, antimatterconverters, claytronics,
dronecomponents, fieldcoils, missilecomponents, shieldcomponents, smartchips,
turretcomponents, weaponcomponents, khaakalloy). Vanilla defines twelve such jobs — an L
and an M per economic faction.

Clone `argon_equipment_trader_m`/`_l`, with three changes that are each a silent no-op if
missed:

- **`buildatshipyard="false" gate="true"`.** Vanilla builds traders *at a shipyard of the
  owning faction*; a custom faction has none, so the quota can never fill and not one
  trader ever exists. Spawning at a gate is the escape hatch the Kha'ak jobs use.
- **Vanilla hull, custom owner.** `<select faction="…">` for a ship goes through the ware
  `<owner>` lists, which name no custom faction — so select an `argon` hull and set
  `<owner exact="twitchally" overridenpc="true"/>`.
- **Drop `relation="ally"` from `<location>`** if the faction is allied with everyone; it
  would be a no-op written out longhand.

Give the faction an **`<account amount="…"/>`** too: traders must *buy* before they can
deliver. Vanilla only writes `<account>` on the player, so NPC balances may be
engine-managed — harmless if redundant, decisive if not.

**Jobs take time.** Traders must spawn, fly to a producer, buy and deliver before anything
appears. For a station that should be useful immediately, seed starter stock at spawn:
size it off the station's own `cargo.{$ware}.free` (a fraction, capped) rather than a flat
number — free space is already `0` for anything the station cannot store, so listing a
ware it has no use for costs nothing and needs no per-station-type ware lists.

---

## Validating faction work

`<diff>` files validate against `libraries/diff.xsd`, which only checks the patch grammar.
To check the *content*, merge the diff onto the vanilla document and validate that against
the real schema:

```python
from lxml import etree
doc  = etree.fromstring(vanilla_factions_bytes)          # base game libraries/factions.xml
ours = etree.parse('extensions/<mod>/libraries/factions.xml').getroot()
for add in ours.findall('add'):
    for child in add:
        doc.append(child)
schema = etree.XMLSchema(etree.parse('_scratch/xsd/factions.xsd'))
print(schema.validate(etree.ElementTree(doc)))
```

That is what caught the child-order requirement above, rather than a failed game load.
