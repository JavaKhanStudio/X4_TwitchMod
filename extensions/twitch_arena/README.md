# Twitch Arena — the world-affecting companion mod

A **separate** X4 extension from `twitch_integration`, on purpose:

| | `twitch_integration` | `twitch_arena` (this) |
|---|---|---|
| Touches the world? | No | **Yes** (adds a sector + gamestart) |
| `content.xml` `save` | `save="0"` | `save="true"` |
| Add to existing save? | ✅ yes | ❌ needs a **new game** |
| Use on its own? | ✅ the bridge alone | ✅ a sandbox sector (Twitch optional) |

Keeping them apart means people can run the save-safe bridge by itself, and opt
into the arena only when they want a fresh, contained playthrough. `twitch_arena`
declares an **optional** dependency on `twitch_integration`, so if both are on,
Twitch chat drives the spawns here.

## What it is
A single-sector "arena" galaxy plus a **new-game option** ("Twitch Arena", in the
custom/creative group) that drops you into it. Built from the game's own macro
hierarchy (galaxy → cluster → sector → zone), verified against
`maps/demo_universe/*` and registered in `index/macros.xml`.

## Status — iteration 1 (foundation)
- ✅ custom galaxy: 1 cluster / 1 sector / 1 zone, with a backdrop
- ✅ gamestart: start in one Nemesis (Paranid M corvette) at the sector origin
- ✅ vanilla economy disabled (jobs + god off) so nothing intrudes

### Planned — iteration 2 (once iteration 1 loads in a new game)
- second Nemesis (a player-owned wingman) + weapon loadouts (plasma / lasers)
- a friendly dock to repair/rearm/build
- a jump gate linking the arena to the vanilla galaxy

## Test it
1. `install.ps1` (repo root) deploys this alongside `twitch_integration`.
2. In X4 → **Settings → Extensions**: enable **Twitch Arena** (Protected UI Mode
   can stay as-is; that's only needed for the bridge's pipe).
3. **New Game** → custom/creative group → **Twitch Arena** → start.
4. You should load into the arena sector in a Nemesis named *Twitch One*.

## Files
```
content.xml                         manifest (save="true", opt. dep on twitch_integration)
index/macros.xml                    diff: register the 4 map macros
libraries/gamestarts.xml            diff: add the "Twitch Arena" new-game option
maps/twitch_arena/galaxy.xml        galaxy macro (1 cluster)
maps/twitch_arena/clusters.xml      cluster macro (1 sector + backdrop)
maps/twitch_arena/sectors.xml       sector macro (1 zone)
maps/twitch_arena/zones.xml         zone macro (player start anchor)
```
