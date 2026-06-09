# 08 — Viewer Economy & Event Design

> The **gameplay-design layer** of the mod, distinct from the plumbing in docs 00–07.
> Docs 00–06 answer *"how does a Twitch event physically reach X4?"*. This doc answers
> *"what can a viewer **do**, what does it **cost**, and how do we keep the stream playable?"*
>
> Ported and adapted from **TwitchToolkit** (hodlhodl1132, RimWorld — deprecated, MIT-ish,
> studied for *concepts only*; no code copied). TwitchToolkit is the reference design for
> "viewers spend a watch-time currency to inject events into a streamer's game." We take its
> proven loop and re-fit it to X4's economy-sim stakes.
>
> Where this lives architecturally: per **D6** (doc 04), the **Bridge owns the economy**
> (wallets, karma, store validation, cooldowns, caps, voting tally) and **X4/MD owns the
> effects**. The Bridge only ever emits an already-vetted `cmd` line to X4. This doc is the
> spec for extending `bridge/twitch_bridge/` (`commands.py` + `catalog.py`) into a full
> economy, and for the matching MD effect cues.

---

## 1. The core loop (why TwitchToolkit works)

```
 watch the stream ──▶ passively earn COINS every interval
        ▲                         │
        │                         ▼
   karma rewards            spend coins in the !buy STORE
   "good" buying                  │
        │                         ▼
        └──── event fires in X4 ◀─ Bridge validates (coins? karma? cooldown? cap?)
                  │
                  └──▶ X4 reports outcome ──▶ chat feedback
```

The genius is the **parallel currency**: it works without Twitch Affiliate (no channel
points needed), it is fully tunable by the streamer (unlike fixed channel-point costs), and
it creates a self-regulating market — expensive catastrophes are *rare* because they cost a
lot of watch-time, and the **karma** governor punishes anyone who only ever buys pain.

**Decisions locked in (2026-06-09):** Full coin economy + store ✅ · Full karma governor ✅ ·
Voting/"democracy" mode as an opt-in toggle ✅ · 4 severity tiers, destructive events
off-by-default ✅.

---

## 2. The viewer wallet (points distribution)

Each viewer the Bridge has ever seen gets a persistent record:

```jsonc
// bridge state, e.g. ~/.config/x4-twitch-bridge/viewers.json  (gitignored, like tokens)
{
  "viewer42": { "coins": 430, "karma": 100, "last_seen": 1736459000,
                "sub": false, "vip": false, "mod": false, "banned": false }
}
```

> **New Bridge responsibility.** Today the Bridge is stateless between events. The economy
> requires a small persisted store. Keep it dead simple: a JSON file written atomically
> (temp-file + rename) on a debounce, loaded at startup. No DB. Mirrors the existing
> `tokens.json` pattern (D7).

### 2.1 Earning coins — the award loop

A timer in the Bridge (not in X4 — X4 must stay dumb) awards coins every `coin_interval`
to every **active** viewer:

```
reward = round_up( coin_amount
                   × (karma / 100)                       # reputation multiplier
                   × role_multiplier                     # sub/vip/mod
                   × activity_multiplier )               # 1.0 / 0.5 / 0.0
       + role_flat_bonus
```

**Who counts as "active":** anyone who sent a chat message recently, plus the live chatter
list. TwitchToolkit polled the now-dead `tmi.twitch.tv/.../chatters` endpoint; **we
modernize** — track activity from EventSub `channel.chat.message` events, and optionally
top up from the **Helix Get Chatters** endpoint (`moderator:read:chatters` scope) which the
`twitchAPI 4.5` client (doc 03) already supports.

**Activity decay** (keeps lurker-bots from minting coins): full coins if seen within
`half_coins_after` minutes; half coins past that; nothing past `no_coins_after`.

### 2.2 Starting defaults (ported from TwitchToolkit, tune later)

| Setting | TT default | Note for X4 |
|---|---|---|
| `starting_balance` | 150 | one cheap "name a ship" + change |
| `coin_interval` | 2 min | award cadence |
| `coin_amount` | 30 / interval | base, before multipliers |
| `min_purchase_price` | 60 | floor on any store item |
| `half_coins_after` | 30 min idle | activity decay knee |
| `no_coins_after` | 60 min idle | activity decay floor |
| `sub`  flat / mult | +10 / ×1.25 | subscriber perk |
| `vip`  flat / mult | +5  / ×1.15 | vip perk |
| `mod`  flat / mult | +3  / ×1.05 | mod perk |

Admin overrides (chat or in-game menu): `givecoins @user N`, `giveallcoins N`
(negative = tax), `togglecoins`, `togglestore`, `setkarma`, `checkuser`, `resetviewers`.

---

## 3. Karma — the reputation governor

Karma is a **per-viewer percentage** (default 100, cap 140, floor 10) that *multiplies their
coin income*. It is the self-balancing heart of the system:

- Buying **Good** events nudges karma **up**, **Bad** events nudge it **down**, **Doom**
  events tank it hard. So a viewer who only ever spawns Xenon slowly goes broke; a viewer
  who gifts the player ships earns faster.
- The karma change scales with **price** and with the viewer's **current karma tier** — at
  high karma a bad purchase costs you more (you had more to lose); at low karma good
  purchases recover you faster. (TwitchToolkit's 4-tier curve; see `Store_Karma.cs`.)
- Optional auto-ban / karma-floor for viewers who *only* ever buy "always-bad" events.

> **Two orthogonal axes — our improvement over TT.** TwitchToolkit overloaded one
> `karmaType` field to mean *both* "how nasty is this" and "how does it affect the buyer's
> reputation." We split them (see §5): **severity tier** is the streamer's experience dial;
> **karma type** is the reputation effect. A *gift a destroyer* event is **Major** severity
> but **Good** karma; a *Kha'ak swarm* is **Major** severity but **Bad** karma.

### 3.1 Per-window event caps (the other governor)

Independent of karma, the Bridge caps how many events of each kind fire per rolling window,
so chat can't dogpile catastrophes even if everyone is rich:

| Cap | TT default | Purpose |
|---|---|---|
| `max_bad_events_per_interval`    | 3  | hard ceiling on incoming pain |
| `max_good_events_per_interval`   | 10 | gifts are fine, but not infinite |
| `max_neutral_events_per_interval`| 10 | |
| per-event `event_cap` + cooldown | 1 / 15 min | each event has its own re-buy cooldown |

When something is capped, the Bridge replies in chat with the time remaining ("@viewer42
Xenon raid is maxed, wait 12 min").

---

## 4. The store — how viewers buy events

Two product kinds, both ported from TwitchToolkit:

1. **Simple events** — fixed effect, fixed cost. `!buy tornado` → fires.
2. **Variable events** — take arguments. `!buy nameship Serenity` (name a ship),
   `!buy ware energycells 200` (gift wares with a quantity → cost scales).

### 4.1 Purchase pipeline (Bridge-side, extends `commands.py`)

```
chat "!buy <key> [args]"  ─▶  CommandEngine
   1. resolve <key> → catalog entry (simple or variable)
   2. cost ≥ 1 ? and not already mid-purchase ?
   3. viewer has enough coins ?                         ── else: reply "not enough"
   4. karma-type not maxed this window ?                ── else: reply "maxed, wait N"
   5. event not on cooldown ?                           ── else: reply "cooldown, wait N"
   6. (variable) args parse & validate ?                ── else: reply syntax help
   7. effect is POSSIBLE in current game state ?  ← needs a round-trip to X4 (see §7)
   8. debit coins, recompute karma, log purchase
   9. emit vetted  {"t":"cmd","id":"<action>","tier":"minor","payload":{...}}
  10. optional purchase-confirmation message in chat
```

Steps 1–6, 8–9 are pure Bridge logic (testable headless, like the existing
`tools/test_commands.py`). Step 7 ("is this even possible right now?") is the one place we
may want X4 to veto — see §7. To start, we can skip 7 and let MD silently no-op impossible
effects.

### 4.2 Viewer-facing chat commands (port these)

| Command | Effect |
|---|---|
| `!balance` / `!bal` / `!coins` | show coins + karma% |
| `!buy <key> [args]` | purchase (the workhorse) |
| `!karma` / `!whatiskarma` | explain the karma system |
| `!store` / `!purchaselist` | link to the live pricing sheet / in-game store |
| `!gift @user N` | transfer coins (optional karma-gating to stop abuse) |
| `!instructions` / `!modinfo` | how the mod works |

Pricing sheet: TwitchToolkit links viewers to an external **Google-Sheet-style price list**
(`custom_pricing_sheet_link`). Cheap and effective — the streamer curates one URL. We keep
that, and *additionally* expose the catalog in-game via the **Simple Menu API** (doc 04,
Milestone 4) so the streamer can toggle/price events without editing files.

---

## 5. The four severity tiers (X4 catalog)

The streamer's primary dial. **Every event is individually triggerable**, but is **tagged
with a tier** so the streamer can enable/disable and price by *experience*, not one event at
a time. **Destructive tiers ship OFF by default.**

| Tier | Feel | Default | Typical karma |
|---|---|---|---|
| **0 · Pure Interaction** | cosmetic / identity, no stakes | ON | Good/Neutral |
| **1 · Minor Distraction** | survivable annoyance | ON | Bad(minor)/Good |
| **2 · Major Distraction** | a real fight or a real gift | OFF | Bad/Good |
| **3 · Doom** | fleet/station-threatening | OFF (+ high price, low cap) | Doom |

Mapping the user's own examples: *name a ship* = **Pure** · *one small pirate to annoy* =
**Minor** · *a group of Kha'ak* = **Major** · *a Xenon K spawns in the sector* = **Doom**.

### 5.1 Draft X4 event catalog

> Costs are first-draft, balanced against §2.2 income (≈900 coins/hour for an active
> non-sub at 100 karma). Treat as starting points. `id` = the MD action id.

**Tier 0 — Pure Interaction** (identity & flavour; the engagement on-ramp)
| id | `!buy` | what happens | karma |
|---|---|---|---|
| `name_ship` | `nameship <name>` | rename one of the player's ships (viewer's chosen text) | Neutral |
| `adopt_ship` | `adoptship` | a player ship is tagged as "owned by @viewer"; their name shows on it, and game→chat pings when it kills/dies (the X4 analog of TT's *viewer-named colonist queue*) | Good |
| `name_station` | `namestation <name>` | rename a station / set a billboard line | Neutral |
| `comm_message` | `comm <text>` | viewer's text appears as an in-game comms/log message | Neutral |
| `salute` | `salute` | a friendly ship does a flyby / signal near the player | Good |

**Tier 1 — Minor Distraction** (survivable; the bread-and-butter)
| id | `!buy` | what happens | karma |
|---|---|---|---|
| `pirate_harass` | `pirate` | spawn **one** S/M pirate to harass the nearest player ship | Bad |
| `police_scan` | `scan` | a police ship demands a scan / small fine | Bad |
| `cargo_pinch` | `pinch` | small amount of cargo "goes missing" from one ship | Bad |
| `rep_ding` | `repding <faction>` | small reputation hit with one faction | Bad |
| `gift_small` | `gift` | a small resource/credit drop near the player | Good |
| `escort_gift` | `escort` | a single friendly fighter joins as a temporary escort | Good |
| `ware_drop` | `ware <ware> <qty>` | gift wares, cost scales with qty (variable event) | Good |

**Tier 2 — Major Distraction** (a real moment; OFF by default)
| id | `!buy` | what happens | karma |
|---|---|---|---|
| `khaak_swarm` | `khaak` | a **cluster** of Kha'ak fighters jumps in and attacks | Bad |
| `pirate_squadron` | `raidpirate` | a pirate squadron (several M ships) attacks | Bad |
| `enemy_patrol` | `patrol` | a hostile faction patrol diverts into the player's sector | Bad |
| `rep_hit` | `rephit <faction>` | meaningful reputation loss with a faction | Bad |
| `gift_ship` | `giftship <class>` | gift the player a ship (M/L, class = price) | Good |
| `merc_wing` | `mercs` | a mercenary wing spawns to defend the player | Good |
| `rare_cache` | `cache` | drop a cache of rare/expensive wares | Good |

**Tier 3 — Doom** (fleet/station-threatening; OFF, expensive, hard-capped)
| id | `!buy` | what happens | karma |
|---|---|---|---|
| `xenon_k` | `xenonk` | a **Xenon K** destroyer jumps into the player's sector | Doom |
| `xenon_i` | `xenoni` | a **Xenon I** battleship — the nuclear option | Doom |
| `xenon_wave` | `invasion` | a coordinated Xenon attack wave | Doom |
| `station_sabotage` | `sabotage` | sabotage / module damage on a player station | Doom |
| `faction_war` | `war <faction>` | provoke a faction into open war with the player | Doom |

> Positive "doom-scale" events (e.g. *gift a destroyer*) live in Tier 2/3 by **price** but
> are **Good** karma — the two-axis split (§3) makes that natural.

### 5.2 Catalog data shape (extends `catalog.py`)

```python
# each entry adds: tier, karma_type, cost, event_cap, cooldown, default_enabled, args
StoreEvent(id="khaak_swarm", buy_key="khaak", tier=2, karma="bad",
           cost=900, event_cap=2, cooldown=600, default_enabled=False)
StoreEvent(id="ware_drop", buy_key="ware", tier=1, karma="good",
           cost_per_unit=2, args=["ware", "qty"], default_enabled=True)
```

The existing `Command` dataclass in `commands.py` grows these fields (or a `StoreEvent`
subclass). The MD side gains one `<cue>` per `id` (as today), reading the payload from
`event.param3`, now also branching on `tier` for shared safety logic.

---

## 6. Voting / "democracy" mode (opt-in toggle)

A second, group-scale way for chat to interact — **off by default**, streamer toggles on.

**Mechanic (from TwitchToolkit `Vote*` + `VoteHandler`):** periodically the Bridge opens a
**vote** offering N candidate events. Viewers vote by typing a **number** in chat. After
`vote_time` minutes the Bridge tallies (one vote/viewer; **subs/vips/mods get extra vote
weight**, ties broken at random) and fires the winner.

Two flavors worth specing:
1. **Storyteller mode** — the Bridge periodically *picks* a random event automatically (no
   chat input), so the world stays alive on a slow stream. (TT's `StorytellerComp_*`.)
2. **Democracy mode** — the Bridge offers a *poll* of candidates and chat votes. More
   engaging; the headline feature.

X4 fit: present the poll as an in-game notification ("Sector event vote: 1) Trader convoy
2) Pirate raid 3) Xenon scout — vote in chat!") driven by a `{"t":"vote_open",...}` line,
collect votes in the Bridge, emit the winning `cmd`. **The Bridge owns the entire tally**;
X4 only renders the prompt and fires the result. Vote weighting reuses the role data already
in the wallet (§2).

Defaults to port: `vote_time` ≈ 2 min, `sub_extra_votes` 1, `vip/mod_extra_votes` 0.

---

## 7. Protocol additions (extends doc 00 §5)

The wire format stays newline-JSON. New message types this layer needs:

```jsonc
// Bridge → X4
{"t":"cmd","id":"khaak_swarm","tier":2,"viewer":"viewer42","payload":{}}      // a purchase fired
{"t":"vote_open","id":"v17","prompt":"Sector event","options":["Trader","Raid","Xenon"]}
{"t":"vote_result","id":"v17","winner":1}
{"t":"notify","msg":"@viewer42 named the Behemoth 'Serenity'"}                 // chat→game flavour

// X4 → Bridge
{"t":"possible","id":"khaak_swarm","ok":true}     // optional veto for pipeline step 7 (§4.1)
{"t":"owned_ship_event","viewer":"viewer42","event":"kill","detail":"Xenon P"} // adopt-a-ship feedback
{"t":"game_state","paused":true,"player_sector":"Argon Prime"}                 // gate events on state
```

The Bridge maps `owned_ship_event` / outcomes back into chat (`{"t":"say",...}`), closing
the game→Twitch loop (doc 04 Milestone 5). Adopt-a-ship is the high-engagement payoff: a
viewer's name rides a real ship and chat hears when it scores a kill or dies.

---

## 8. What to build, in order (new milestones)

Slots after the current Milestone 3 (command engine) — economy is the **feature layer** on
the proven pipe.

- **M3.5 — Wallet & award loop.** Persisted `viewers.json`; coin-award timer; activity
  tracking from chat events; `!balance`/`!coins`. *Test headless* (extend
  `tools/test_commands.py`). No new X4 work.
- **M3.6 — Karma governor.** Karma field + tiered curve + good/bad/doom effect on buys +
  per-window caps. Headless-testable.
- **M4.0 — Store + Tier 0/1 catalog.** `!buy`, purchase pipeline (§4.1 steps 1–6, 8–10),
  `StoreEvent` catalog, MD cues for Pure + Minor events. First real in-game purchases.
- **M4.1 — Tier 2/3 + safety.** Major/Doom events (default OFF), optional X4 "possible?"
  veto (step 7), severity-aware MD safety.
- **M4.2 — Voting/democracy mode** (toggle), reusing wallet role weights.
- **M4.3 — In-game store menu** via Simple Menu API (toggle/price events live) + the
  external pricing-sheet link.

Everything in M3.5–M3.6 and the Bridge half of M4.0 is **testable now, headless, with no X4
installed** — it slots directly onto the existing `bridge/` test harness.

---

## 9. Concepts deliberately **not** ported

- **RimWorld-specific events** (weather, diseases, mental breaks, colonist traits) — replaced
  wholesale by the X4 catalog in §5.1.
- **TwitchToolkit's IRC plumbing & `tmi/chatters` polling** — dead Twitch APIs; we use
  EventSub + Helix (doc 03). Only the *economy concepts* port, never the transport.
- **The single overloaded `karmaType`** — we split severity vs. reputation (§3).
- **In-game money-as-coins coupling** — coins are a Bridge-side viewer currency, fully
  decoupled from the player's in-game credits.

## 10. The catalog as single source of truth — the viewer "item-list" view

TwitchToolkit shipped a separate **item-list** site (`github.com/twitchtoolkit/item-list`) — a
brilliant, simple idea we should copy: a static, **searchable/sortable** web page that renders
the buyable catalog from plain JSON data, shared with viewers as a link so they always know
*what they can do and what it costs*. Studied 2026-06-09; its shape:

- **Data, separated from presentation.** Two JSON files (`StoreEvents.json`, `StoreItems.json`),
  each a flat list of entries: `{ "abr": "tornado", "price": 800, "karmatype": "Bad" }` (items add
  `category`). The streamer drops in their own JSON → their own pricing site.
- **Presentation.** One `index.html` (Bootstrap + List.js) fetches the JSON and renders
  **searchable, sortable tables** — sort by name / price / karma, plus a command cheat-sheet
  (`!bal`, `!whatiskarma`, …).

### 10.1 The design rule this imposes on us

**The catalog is one source of truth that must drive *both* the runtime engine and the display.**
So `bridge/twitch_bridge/catalog.py` entries (the `StoreEvent` from §5.2) must carry **display
metadata**, not just runtime fields. Canonical entry:

```python
StoreEvent(
    id="khaak_swarm",            # internal action id (the MD cue that fires)
    buy_key="khaak",             # the !buy <key> abbreviation  (TT's "abr")
    label="Kha'ak swarm",        # human name (display)
    description="A cluster of Kha'ak fighters jumps in and attacks the nearest player ship.",
    category="Combat",           # grouping for the list view
    tier=2,                      # Pure/Minor/Major/Doom — the streamer's experience dial (§5)
    karma="bad",                 # good/neutral/bad/doom — reputation effect (§3)
    cost=900,                    # fixed; OR cost_per_unit=2, unit="ware" for variable events
    args=[], syntax="!buy khaak",# variable events list their args + a usage string
    cooldown=600, event_cap=2,   # limits (§3.1)
    default_enabled=False,       # ships off (Major/Doom default off)
    enabled=False,               # current streamer setting (runtime, overridable)
)
```

Everything the item-list needs (label, description, category, price, tier, karma, syntax,
cooldown) lives on the same object the engine already uses to validate `!buy`. **No second
catalog, ever** — the list view is just a *projection* of `catalog.py`.

### 10.2 Local view vs. shareable export (ours differs from TT here)

TT's was purely online (a hosted site). Ours is **local-first**, because the companion already
serves a localhost web app (the dashboard, doc 09). Two surfaces, one data source:

1. **Live local view** — a `/catalog` JSON endpoint + a browsable page on the companion's
   dashboard server (same server as `/api/status`). It reflects *reality*: only **enabled**
   events, **current** prices, live cooldown/cap state. The streamer reads it; it can also be
   shown in-game (doc 08 §4.2 / doc 09).
2. **Shareable static export** — a `companion → export` that writes a `catalog.json` (+ a
   self-contained `index.html` like TT's) the streamer can publish (GitHub Pages, Neocities,
   anywhere) and drop in chat as the **purchase-list link** (the `!purchaselist` / pricing-sheet
   analog, §4.2). This is the online twin of the local view — same JSON schema, so the *same*
   page code renders either.

### 10.3 What to build (slots into the milestones)

- **Now (cheap, do with the catalog):** define the `StoreEvent` schema above so display metadata
  is captured from day one — costs nothing and unblocks every view later. (M4.0, doc 08 §8.)
- **With the store (M4.0):** add the `/catalog` JSON endpoint to the dashboard server; render a
  searchable/filterable list page (filter by **tier** and **karma**, sort by price) — the
  local item-list.
- **Polish (M4.3/M6):** the static **export** + a viewer-facing command (`!shop` / `!purchaselist`)
  that links to it; optional in-game catalog via Simple Menu API.

> Schema discipline now = both a live local catalog page *and* a shareable viewer pricing site
> later, for free. Record elements richly; project them many ways.

## 11. Source

TwitchToolkit (hodlhodl1132), RimWorld, deprecated — studied 2026-06-09 for concepts only.
Key files that informed this doc: `Viewer.cs`/`Viewers.cs` (wallet + award loop),
`Ticker.cs` (the interval timer), `Store/Purchase_Handler.cs` (purchase pipeline),
`Store/Store_Karma.cs` + `Settings/ToolkitSettings.cs` (karma curve + all default numbers),
`Commands/ViewerCommands.cs` (chat commands), `Votes/Vote.cs` + `Votes/Vote_Handler.cs`
(voting), `Defs/StoreIncidents/StoreIncidents.xml` (the event-catalog data shape).
Repo: https://github.com/hodlhodl1132/twitchtoolkit (concepts only — code is dead).
