# 10 — Adopted ships (the fleet subsystem)

A viewer claims one of the **player's existing ships** as theirs. It is renamed after
them, they can see how it is doing, and when it dies they can pay to have it rebuilt.
This is the first feature where the game reports *state* back to the companion rather
than just accepting orders, so most of the design here is about that direction of flow.

Code: `bridge/twitch_bridge/fleet.py` (roster, adoptions, record) ·
`economy.py` (the chat commands) · MD cues `Twitch_PublishFleet`, `Twitch_OnAdoptShip`,
`Twitch_OnAbandonShip`, `Twitch_OnResurrectShip`, `Twitch_ShipWatch`.
Tests: `bridge/tools/test_fleet.py`.

## 1. Chat surface

| Command | What it does |
|---|---|
| `!fleet` / `!fleet L` | Adoptable ships, optionally one hull class (S/M/L/XL) |
| `!buy adopt <ID>` | Claim it. Priced per hull. **One ship per viewer** |
| `!myship` | Your ship: type, hull, shields, where it is |
| `!myship <ID>` | The detail card for any ship, adopted by anyone |
| `!abandon [ID]` | Give it up. Free, no refund. Mods may release anyone's |
| `!resurrect [ID]` | Rebuild your wreck at the player's HQ, at 1.5× the adopt price |

Pricing comes from the same `ships.json` that prices `!buy ship`: adoption is
`credits / 1200` (a claim, not a purchase — buying is `/300`), rebuilding is
`adopt × 1.5`. Hulls the generator doesn't cover fall back to a size price.

## 2. Who owns which truth

| Fact | Owner | Why |
|---|---|---|
| What ships exist | **the game** | It is the only one that knows |
| Who adopted what | **the bridge** (`adoptions.json`) | It knows viewers; MD does not |
| Which ships to watch for death | **MD** (a group) | The event needs live object refs |

MD is otherwise *stateless about adoption*: it renames the ship it is told to and
reports what it sees. That keeps the MD side small, at one cost — loading an **older
savegame** leaves adoptions in the registry that never happened in that timeline. Those
ships simply fail to appear in the roster and become wrecks (§5), which is recoverable;
the alternative, releasing them, is not.

## 3. The roster (game → bridge, every 45s)

```
{"t":"fleet","total":42,"sent":42,"data":"IDCODE|MACRO|SIZE|HULL|SHIELD|SECTORMACRO;…"}
```

**Every field is an engine token.** Ship names are deliberately *never* transmitted:
they are player- and viewer-editable, MD builds this JSON by string concatenation, and
one ship called `foo"bar` would corrupt the whole line. The bridge resolves the display
name from the macro (`ships.json`) and the sector name from its macro (`sectors.json`).
The same rule is why the killer in §5 is reported as a *faction* name — game text, not
player-editable.

- `total` vs `sent`: the line carries at most 60 ships. `!fleet` says "showing 60 of
  300" rather than implying that is the whole fleet.
- Hull/shield are the engine's `hullpercentage` / `shieldpercentage`. A missing value is
  **-1, not 0** — an older mod build sends only three columns, and rendering that as
  "hull 0%" reads as a ship about to explode.

### The ID code is the join key
`object.idcode` ("PSF-481") is stable, unique and token-safe. It is what chat types,
what the registry stores, and what MD matches a ship on. Names are display only.

## 4. Adoption

`!buy adopt` → the bridge charges, claims the ship **optimistically**, and sends
`adopt_ship` with two args: the id code and the **finished name** (`"ana's Nemesis"`).

The name is composed bridge-side because that is the only side that knows both the
viewer's handle and the hull's type — and it means MD never concatenates
viewer-controlled text. Two args need two slots, which is why this command rides the
two-string event form (`screen='Twitch_adopt_ship'`, no `control` filter; see the
x4-modding skill). MD cannot split a string, so there is no other way.

The claim is optimistic because the roster is up to 45s stale: only X4 can say whether
the ship is still there. If it is not, `cmdfail` releases the claim and refunds.

**One ship per viewer** (`MAX_ADOPTIONS_PER_VIEWER`). Checked before price and balance
so the message is the useful one. A wreck still counts as held — which is what gives
`!abandon` a purpose. Viewers holding several from before the limit are grandfathered.

## 5. Death and resurrection

`<event_object_destroyed>` takes a **`group`**, and members may be added and removed
after the event is armed — so ONE cue (`Twitch_ShipWatch`) watches every adopted ship.
Adopt adds to the group, abandon removes, and X4 drops destroyed objects from groups
automatically. A destroyed object is still readable in the handler, which is where the
macro needed to rebuild it is captured — the last moment it is knowable.

```
{"t":"shipdown","idcode":"PSF-481","macro":"…","killer":"Xenon"}
```

The ship becomes a **wreck**: still adopted, no longer flying, rebuildable indefinitely.
`prune_missing()` turns any adoption that silently leaves the roster into a wreck too
(companion was down, sold, captured) — those just have no killer. This is why it must
never *release*: releasing is irreversible, and a wreck is the whole point.

Rebuilding creates a **new object with a new id code**, so the registry has to be
re-keyed. Only MD learns that code, so it reports back and the bridge answers by issuing
an ordinary `adopt_ship` for the new one — the rename runs through the one path that is
already tested rather than a second copy inside the resurrect cue.

```
{"t":"shipnew","old":"PSF-481","idcode":"NEW-014"}
```

Abandoning uses `<clear_object_name>` ("revert to default") rather than writing the type
name back: identical on a stock ship, but writing would destroy a name the *player*
chose before a viewer ever adopted it.

## 6. The record

Every lifecycle step is appended to `adoptions.json` (capped at 1000):

```json
{"at": 1754500000, "event": "adopted",   "user": "simondakhan", "idcode": "PSF-481", "label": "Kyd"}
{"at": 1754500063, "event": "destroyed", "user": "simondakhan", "idcode": "PSF-481", "label": "Kyd", "killer": "Xenon"}
```

Events: `adopted`, `abandoned`, `destroyed`, `rebuilt` (carries `was`), `released` (a
rollback). The **ship type is resolved at write time** so the log still reads sensibly
after the ship and its roster entry are long gone.

Shown in the companion dashboard: the moderation table carries an **Adopted ship**
column per viewer, and an **Adoption record** card shows the history. Both are fed by
`Fleet.card()` so the two views cannot disagree about a ship's state. A card has three
states — `flying`, `destroyed`, and `missing` (fell off the roster with no reported
death; deliberately distinct, since calling it destroyed would invent a killer).

## 7. Gotchas

- **Bridge-only changes need the companion restarted**; MD changes need a save loaded.
  An unknown `!command` is silently ignored by design (other bots use `!` too), so a
  stale companion looks *exactly* like a broken feature — that cost a debugging round on
  `!abandon`. The MD build stamp (`Twitch_Say`) covers the game side; there is no
  equivalent signal on the bridge side yet.
- **A wreck reports no condition.** Hull/shields from the last roster predate its death.
- **`resolve()` searches what is available; `resolve_adopted()` searches the opposite
  set** and includes ships gone from the roster — otherwise a destroyed ship could never
  be abandoned.
