# Dev Log

Chronological engineering log — decisions, milestones, and the bugs we hit, in the repo so
they're versioned and auditable (not just in a private assistant's memory). Newest first.
Reference docs (`00`–`09`) hold the durable detail; this log is the narrative + dates.

**Content rule:** public repo — no secrets, no personal paths/IDs. Use `<X4>`, `<SAVE>`,
`<id>` placeholders. See `SECURITY.md`.

---

## 2026-08-06 — Boso Ta calls you: the comm popup as an event reaction
Twitch events now put **Boso Ta on the cockpit monitor** — live-rendered, lip-synced,
speaking a real vanilla voice line with its own subtitle. `!boso` (subscriber and up)
walks through the moods one per call; `!boso angry` picks one; `!boso random` draws from
every recording he has. Raids, subs and cheers each fire a tonally-matched mood.

- **There is no video in X4.** Not one `.ogv`/`.bik`/`.mp4`/`.webm` in any archive — the
  "video call" is the comm popup, so the task is "make an actor speak", not "play a file".
  One call does it: `md.LIB_Dialog.Speak_Actor_Run` with the actor and a line id.
- **Nothing had to be spawned or tracked.** Named characters are globals
  (`md.$PersistentCharacters.$BosoTa`, set by vanilla `md/setup.xml:324`), and vanilla
  already tags him with the monitor cutscene at `setup.xml:452`
  (`$cutscenekey = table[$key='ShowCharacterBoron']`), which LIB_Dialog reads itself.
- **Finding his clips.** A character macro's `<identification page="…"/>` is its *voice
  page* — Boso Ta is 10201 — and audio is one file per line at
  `voice-l044/10201/comm/<line>.ogg`. 64 of the 72 line ids vanilla uses for him resolve
  there, which is what confirmed the mapping. **An id with no `.ogg` plays silently**, so
  presence in that folder is a hard requirement: a missing recording looks exactly like a
  cue that never fired.
- **`!boso random` needed a generated pool.** Page 10201 is a *shared* voice page ("Boron
  NPC 1 / Boron rep / Misc Plot Characters"), 2422 entries. `tools/gen_boso_lines.py`
  filters to 1263 usable lines — id ≥ 99901, has audio, no `(* … *)` headers, no
  `{page,line}` redirects, no `$PLACEHOLDER$`, ≤120 chars, and no stage directions
  mid-string (a leading `(annoyed)` is stripped by the game, anything later is drawn in
  the subtitle) — and writes `md/twitch_boso_lines.xml`.
- **Why the pool lives in MD, not the bridge.** A line id can only ever be chosen
  game-side: numbers don't marshal Lua→MD and MD has no string→number conversion. So the
  bridge can say `random` but can never name a line. Split into 4 chunks because the whole
  list is ~14k chars and the largest list literal in vanilla MD is 8674.

**The bug worth remembering.** Calls were first queued in a sub-cue whose `<conditions>`
were bare `<check_value>`s — polled until the player was free. That is correct and
idiomatic for an ordinary cue (vanilla's own Boso call does it) but **illegal inside an
`instantiate="true"` cue's subtree**, and the game says so at load:

```
twitch_integration.xml(1944): Found non-event condition 'check_value', event condition required!
```

A rejected cue is simply *absent*, so it failed silently: `x4debug.txt` showed
`boso_call queued mood=random line=30222178` and then nothing, forever. `md.xsd` validates
the file happily — it is a load-time rule, not a schema rule. Two things came out of it:

- the wait is now a **signalled loop** (`Twitch_BosoPump`: `event_cue_signalled` + delay +
  re-signal while work remains), the idiom `Twitch_RetryRead` already proved here, with the
  queue on a plain top-level cue so one name resolves it from anywhere;
- `tools/test_md_sync.py` now **walks the cue tree** and fails if any cue under an
  instantiated cue lacks an event condition. Schema validation and that walk catch disjoint
  classes of bug.

Also corrected while in there: the give-up timer started as a retry *count*, which with N
queued calls expires ~N× early (every loop touches the same head entry). It is a wall-clock
`player.age + 15min` deadline stamped at dispatch. Blocked calls otherwise wait
indefinitely and are never refunded for the player merely being busy.

**Known-bad, untouched:** `Twitch_RankWatch` re-arms with `signal_cue … param="$metrics"`,
but `signal_cue` accepts neither `param` nor `delay` — the baseline is silently dropped
every tick. Flagged, not fixed: it is a self-signalling loop and a blind change risks a hot
loop.

---

## 2026-08-06 — Station building: chat can build a station in any sector
Viewers can now buy a **complete station** and place it in the player's sector or in any
sector they name: `!buy wharf`, `!buy defence argon prime`, `!buy solar black hole sun iv`.
Eight types (defence platform, solar plant, trading station, equipment dock, wharf, shipyard;
plus a hostile Raider den and a Kha'ak hive, both off by default like the other destructive
tiers).

- **MD (`Twitch_SpawnStation` library + one cue per type).** `create_station` with a
  `constructionplan` id from vanilla `libraries/constructionplans.xml` and
  `state="componentstate.operational"` arrives **fully built** — shape copied verbatim from
  `md/scenario_advanced.xml`, `md/story_paranid.xml` and `md/x4ep1_mentor_subscription.xml`.
  The library then does what the base game does around such a station: `signal_objects
  'init station'` (hands it to the economy/station manager), manager + defence control posts,
  and a paid build plot (the `SetupHQ` idiom) so the player can extend it.
- **Why one cue per station type.** A command carries exactly ONE string to MD (the ui lua
  ';'-joins the arg values into `event.param3`) and **MD has no string operations at all** —
  the `string` datatype in `scriptproperties.xml` has a single property, so there is no split
  and no substring. Of the two things a station spawn needs — which station, which sector —
  only one can be the argument. Types are few and fixed, sectors are 155+, so the TYPE became
  the command id (= the cue's `control`) and the SECTOR became the argument.
- **`tools/gen_sectors.py` → `sectors.json` → `sectors.py`.** Same shape as the ship
  registry: the generator reads `maps/xu_ep2_universe/*sectors.xml` (sector macros, base +
  every installed DLC), `libraries/mapdefaults.xml` (each sector's `{page,line}` name ref) and
  `t/0001-l044.xml`, and emits 155 rows of `{key, label, macro}`. `sectors.py` resolves viewer
  text to one of them (exact → unique prefix → substring, apostrophes ignored, `here`/omitted
  = the player's sector) and the bridge sends the **macro name**, which MD turns back into a
  sector with `find_sector macro="macro.{$m}"`. Re-run the generator after installing a DLC.
- **`arg_domain="sector"`** joins the whole tail of the `!buy` line into one value (sector
  names are multi-word), so a typo or an ambiguous name is refused *before* the charge —
  `!buy wharf grand exchange` answers "which sector? Grand Exchange I, III, IV".
  New `!sectors <name>` info command checks a name; `!buy station` prints the menu.
- **Refund on failure (`cmdfail`).** A build can fail in-game — `safepos` finds no room —
  after the bridge has already charged. New X4→bridge message `{"t":"cmdfail","id":…,
  "reason":…}`: MD's `Twitch_Fail` cue emits it, the bridge gives the coins back, restores
  the pre-purchase karma (restored, not re-derived — `new_karma()` clamps, so an inverse
  would drift a viewer at the floor/cap), releases the cooldown and the window cap, and
  posts the apology. MD names only the ACTION because it never learns the buyer — the
  command's `by` field stops at the bridge, since the ui lua forwards only arg values — so
  the bridge matches the id against its own record of what it charged, oldest-first.
  Failed disarm/loot ("no station in this sector") refund the same way.
- **Ownership (2026-08-06, same day).** Stations are built for the **Twitch Allies**
  faction by default, not the player: friendly, they defend the sector and trade, but
  they are not free real estate on the player's account. The streamer flips the default
  with a dashboard switch (`Runtime.stations_to_player`), and a viewer overrides it for
  one buy by ending the line with `player` or `ally`. `twitchally` LOST its
  `noresupply notradeoffer privateloadout privateship` tags — correct while it owned
  nothing, but they would have left a built wharf docked with an empty shelf. The
  Raider den and the Kha'ak hive declare no `owner` arg and so cannot be redirected.
  This is the first consumer of the ui lua's 2-arg form: a station buy now carries WHERE
  and WHO, and MD reads them from `event.param2`/`param3` on the `Twitch_<id>` screen —
  no string splitting, which MD still cannot do.
- **Staffing (first live test).** Stations built fine but were GHOST TOWNS: no workforce,
  nobody at the manager office, the trader's corner or the ship dealership. Two causes,
  both ours. (a) `signal_objects 'init station'` was sent with `param3="false"`. That flag
  is named `$gamestartstation` but means "arrived complete rather than built over time",
  and it gates the whole workforce block in `inituniverse.xml` — so the station hired
  nobody, ever. The base game's own build-it-complete path, `finalisestations.xml`, passes
  `true`. (b) We created the manager control entity OURSELVES, which poisoned the base
  game's setup: `CreateTradeManagerEntity` is guarded by `not $controllable.tradenpc.exists`,
  and `signal_objects` is queued while our actions are not — so our manager always won the
  race and vanilla skipped the trader's corner AND never got to the ship dealer.
  Fix: an NPC-owned station is now staffed entirely by `'init station'` (workforce, trade
  wares, ammo, defence + engineer, ship dealer, trade manager). Only PLAYER-owned stations
  are staffed by hand, because `InitStation` deliberately skips them and the
  `event_player_built_station` path that normally covers them never fires for an
  MD-created station; that branch now mirrors it properly (defence + engineer +
  `create_ai_unit`, plus a manager).
- **A faction with no people (second live test).** With the staffing fixed, the log named
  the real blocker: `CharacterDB::FindNPCGenerator(): unable to find NPC generator for tags
  shiptrader, race null, factions Twitch Allies`, and
  `PlaceItemTrader: Twitch Wharf has a trader corner but the faction has no character
  definition for a suitable trader`. X4 resolves the NPC for a post by looking up
  (tags, faction) in `libraries/characters.xml`; a faction named in NO entry can have no
  people at all — note `race null`, so `primaryrace="argon"` in factions.xml does not feed
  this lookup. New generated diff `libraries/characters.xml` (`tools/gen_characters.py`)
  adds both Twitch factions to every character entry the Argon factions can draw on:
  manager, ship trader, platform (trader-corner) trader, service crew, marines, pilots,
  casuals. DLC-defined entries are emitted `silent="true"` so the diff doesn't error for
  someone who lacks that DLC. An XML diff can't append to an attribute, only replace it
  whole, so the file copies vanilla's lists — hence the generator: re-run it after a game
  update, like `gen_ships.py` / `gen_sectors.py`.
- **An owner faction needs an ECONOMY (third live test).** With staff on board, a
  twitchally wharf listed every ship hull and no equipment — no shields, engines,
  weapons or software. Not blueprints and not licences (the log is silent when that
  menu opens): a dock does not conjure equipment, it makes it from COMPONENTS flown in
  by the owning faction's equipment traders. Vanilla has exactly twelve such jobs, an
  L and an M per economic faction, and the log even shows one working
  (`job: 'holyorder_equipment_trader_m'`). twitchally had none, no traders, and no
  money — so the shop had no raw material and nothing was ever going to bring it any.
  New `libraries/jobs.xml` diff clones `argon_equipment_trader_m`/`_l` for twitchally
  with three changes: `buildatshipyard="false" gate="true"` (vanilla builds traders at
  a shipyard OF THE OWNING FACTION — twitchally has none, so the quota could never be
  filled; the Kha'ak jobs use the same escape hatch), an Argon HULL with a twitchally
  OWNER (ship selection by faction goes through the ware `<owner>` lists, which name
  no Twitch faction), and no `relation="ally"` location filter (twitchally is +1 with
  everyone, so it would be a no-op). Quotas well under Argon's. `twitchally` also
  gained an `<account>` — its traders have to BUY before they can deliver.
  Plus a **kickstart**: a station that can build or equip ships is seeded with starter
  stock at spawn (energycells, hullparts and the equipment-basket components), so it is
  useful the moment it appears instead of waiting on the first trader run. Sized off the
  station's OWN `cargo.{$ware}.free` — a quarter of free space, capped at 1500 — because a
  defence platform and a shipyard have wildly different holds, and free space is already 0
  for anything a station cannot store, so wrong wares cost nothing.
- **A macro that isn't vanilla.** `station_arg_defence_base_01_macro` looked exactly like
  every other station hull and was picked for the defence platform from a survey that
  scanned every `.cat` in the install — including installed third-party mods. It ships in
  `faction_fix_pack`, not the base game, so on load: `Property lookup failed: macro.
  station_arg_defence_base_01_macro`, a null macro, and a station that silently never
  builds. The only vanilla `*_defence_base_*` is the Xenon one; vanilla pairs the
  `arg_defence` PLAN with `station_gen_factory_base_01_macro` (md/scenario_tutorials.xml),
  which is the library default, so the override just went away. New
  `tools/check_macros.py` audits every `macro.<name>` / `macro="<name>"` in our MD against
  the base archives + `extensions/ego_dlc_*` ONLY — the standard the mod has to meet, since
  it must work on a plain X4 + DLC install.
- **Equipment, both halves.** Two independent gates stood between a twitchally dock and
  a sellable shield. (1) OWNERSHIP: every ware lists the factions that have it via
  `<owner faction="…"/>`; twitchally was in none. New generated `libraries/wares.xml`
  (`tools/gen_ware_owners.py`) grants it every ware restricted by `generaluseequipment`
  or `militaryequipment` — 449 across base + DLC — scoped by the game's own restriction
  licence rather than a hard-coded list, and excluding the 53 owned only by xenon/khaak
  (alien hardware on an Argon-flavoured ally's shelves). It uses `<add>`, which APPENDS
  an `<owner>`, so unlike characters.xml it never rewrites a vanilla list and cannot
  drift. (2) LICENCES: a faction may only sell a restricted ware to someone holding a
  licence of that type ISSUED BY THAT FACTION, and twitchally had no `<licences>` block
  at all — every vanilla faction owning a tradeable station has one, and the ones without
  (civilian, criminal, outlaw, smuggler, xenon, khaak) are exactly those that sell
  nothing. It now issues generaluseequipment / generaluseship / militaryequipment /
  capitalequipment at `minrelation="-0.01"`, granted on sight since it starts allied,
  with names on this mod's own text page rather than borrowed Argon wording. The patched
  faction document was validated against the game's `factions.xsd`, not just eyeballed.
- Verified: whole bridge suite green (new `test_sectors.py`, station + refund + ownership
  cases in `test_economy.py`, and end-to-end cases in `test_lua_decode.py` pinning
  `("Twitch_station_wharf", "<macro>", "<owner>")`, the empty-sector = current-sector
  contract, and the literal `cmdfail` line — all through the real Lua). The MD file
  validates against the game's own `libraries/md.xsd` apart from one pre-existing
  `signal_cue param` in the rank watcher. Station building confirmed working in-game;
  ownership and refunds are not yet exercised live.

## 2026-08-06 — Two silent-failure bugs, MD schema validation, and adopted ships
A long session that started as "the faction incident is a bit buggy" and ended with a
whole subsystem. The through-line: **every bug found today failed silently**, and the
fixes are as much about making failure visible as about the code.

- **`$var?` means "is DEFINED", not "is non-null".** `<set_value exact="null"/>` *defines*
  the variable, so `$facA?` was true while `$facA` was null, every `not $facA?` guard was
  skipped, and `Twitch_OnFactionIncident` reached `add_faction_relation` with two nulls —
  "Relations between null and null". It had never worked on any path. Diagnosed from
  `x4debug.txt`, and specifically from what was **absent**: no error above the failing
  action proved the guards had evaluated true. Vanilla always compares (`== null`).
  The same trap was in the station cue and the rank cues' "coalesce to 0" guards.
- **Lua `pairs()` order is undefined**, so multi-arg commands silently swapped —
  `{"ware","qty"}` arrived as `"50;energycells"`. Commands now carry `argv`, an ordered
  array; `args` stays for logs. This is what "can't send multiple variables" actually was.
- **MD schema validation** (`_scratch/md.xsd` + lxml) is the cheapest bug-per-minute tool
  we have. It found `reason` being `use="required"` on `add_faction_relation` (so the
  action was a no-op — switched to `set_faction_relation`, which is what vanilla uses for
  NPC↔NPC anyway), and `signal_cue` accepting neither `param` nor `delay` — an ignored
  `delay="2s"` had turned a pipe retry into a ~60/second hot loop. Also caught `--` inside
  an XML comment, which makes the *entire* mdscript unparseable.
- **Build stamp.** MD only reloads on save load, so a correct fix looks broken. Every
  outbound chat line now carries a build tag set in one place (`Twitch_Say`). This
  resolved a round of "still broken" that was purely a stale script. The bridge has no
  equivalent yet — a stale companion silently ignores unknown `!commands`, which cost a
  round on `!abandon`.
- **Adopted ships** (see `docs/10`). Viewers claim a real ship out of the player's fleet;
  it is renamed after them, they can check its hull and location, and they can pay to
  rebuild it when it dies. Two X4 findings made it possible: `<event_ui_triggered>`
  carries three strings and `control` is optional (the only way to get two values into a
  cue, since MD cannot split a string), and `<event_object_destroyed>` takes a `group`
  whose membership can change after the event is armed (one cue watches every adopted
  ship). Design rule that fell out of it: **only tokens cross the pipe** — id codes and
  macros, never names — because MD builds its JSON by concatenation.
- **X4 acknowledges failure only.** So `cmdfail` now carries `ref`, naming what failed.
  Without it the bridge guessed "oldest outstanding charge", which rolled back an
  *earlier successful* adoption and refunded the wrong viewer.
- Also: Twitch Allies are a pickable incident faction; `!buy stance <faction>
  ally|neutral|war` sets standing by the game's own relation *bands* (`relation.<range>.mid`)
  rather than hardcoded numbers; one ship per viewer; an append-only adoption record
  surfaced in the moderation table.
- The x4-modding skill absorbed the reusable half of all this (expression traps, the
  two-string event, group death-watch, schema + log recipes, reload semantics).

## 2026-06-10 — Catalog becomes the interactions roadmap (status field + shareable page)
With the bridge proven, the next phase is implementing the actual interactions — which needs
a tracker for done / in-progress / suggested. Per doc 08 §10 ("no second catalog, ever") the
tracker IS the catalog: no separate TODO list.
- **`catalog.py`** — new `status` field on `StoreEvent` (`live | wip | planned | suggested`),
  orthogonal to `enabled` (dev progress vs streamer config); projected by `display()`. Every
  interaction idea now enters as a catalog entry (`suggested`), gets designed (`planned` —
  the entry IS the design: cost/tier/karma/cooldown), built (`wip`), shipped (`live`).
- **`docs/catalog/index.html`** — the catalog page moved out of `dashboard.py` into a real
  file with TWO homes: served live at `/catalog` (data: `/api/catalog?all=1`), and published
  as-is on **GitHub Pages** (Settings → Pages → `main`/`docs`), where it falls back to the
  committed `catalog.json` (regenerated by `tools/export_catalog.py`). Added status filter
  chips + status badges + live/wip/planned/suggested counts; default sort puts live first.
- **`tools/test_md_sync.py`** — the roadmap can't lie: an event counts as implemented iff
  `twitch_integration.xml` has a cue dispatching on its action id (`control='<id>'`) with no
  TODO marker. `live` without such a cue FAILS; an implemented cue whose catalog status isn't
  `live` FAILS (catalog lagging the game). Current truth: `spawn` live, `reinforcements` wip
  (stub cue), rest planned/suggested.
- Verified: unit tests + Playwright in both modes (live `/catalog`; static via `http.server`
  in `docs/catalog/` with the companion down → falls back to `catalog.json`, back-link
  auto-hidden). README screenshots regenerated.
- **Same-day follow-up:** `kind` field (`info` chat answers vs `effect` game changes — both
  on the page, with filter chips; info syntax renders as a direct `!cmd`, not `!buy`);
  `nicknames` field shown in a Nick column and accepted by the `!buy` lookup; new tier **-1
  Debug** (dev plumbing — the spawn test moved there, out of the viewer economy);
  `satellite_web`/`sats` renamed to `vision` and promoted to Minor. The live info commands
  (`balance`, `karma`, `shop`) are now catalog entries; `test_md_sync.py` verifies info
  liveness against `COMMAND_ALIASES` (id must be canonical, aliases must equal
  buy_key+nicknames) so chat shortcuts can't drift from the public list.

## 2026-06-09 — Repo hygiene for going public
- Hardened `.gitignore` (tokens, `viewers.json`, saves, `debuglog`, sockets, `*.so`, `*secret*`).
- Added `SECURITY.md` — content-leak policy + pre-commit checklist.
- Sanitized PII out of source/docs (home paths, the X4 numeric user-id) → placeholders; made
  the Lua spawn-proof derive the save dir via `GetSaveFolderPath()` instead of a hardcoded path
  (also makes it portable to a second test machine).
- **This file is now where project notes live.**

## 2026-06-09 — Companion OAuth setup panel (the RimWorld-like Connect button) ✅
Built the one-click Twitch onboarding in the companion dashboard.
- `setup_store.py` — persists the Twitch app creds (client id/secret/channel) to a gitignored,
  chmod-600 `~/.config/x4-twitch-bridge/setup.json` (tokens stay separate). `tools/test_setup.py`.
- `sources/twitch.py` — now starts **idle** (no creds required up front) with a runtime
  `connect(id, secret, channel)` / `disconnect()` + connection state (`connected`/`connecting`/
  `login`/`error`) and a status callback. Env creds still auto-connect (backward compatible).
- `dashboard.py` — a **① Connect to Twitch** panel: 3 clear steps (create app + redirect URL,
  paste creds, authorize), a form + Connect button → `POST /api/connect`. Shows when the twitch
  source is idle; flips to "connected as <login>" when live. Twitch state added to `/api/status`.
- `app.py` — loads persisted creds (auto-connect), mirrors source state into the dashboard, and
  routes the Connect button to `source.connect()` across the thread boundary via
  `run_coroutine_threadsafe`. `run-companion.sh` now defaults to `--source twitch`.
- Verified: setup_store + POST plumbing unit-tested; idle source constructs w/o creds; **Playwright
  screenshot confirms the panel renders** (3 steps + Connect button). Full suite green.
- **Live-gated (the user's next test):** the actual OAuth browser flow + EventSub (real Twitch).

## 2026-06-09 — Autonomous build: full bridge-side economy + views ✅
Built M3.5 + M3.6 + the M4.0 bridge half + the item-list view in one pass — all headless,
all tested, nothing in the live-game/Twitch path touched.
- `wallet.py` — `Wallet` + `Viewer` + `EconomySettings` + `new_karma`: persistent `viewers.json`
  (atomic), starting balance/karma, coins, the award loop (karma × role × activity-decay), the
  karma governor (good/neutral/bad/doom curve, clamped). `tools/test_wallet.py`.
- `economy.py` — `Economy.handle_chat`: the `!buy` pipeline (resolve → cost incl. variable →
  role → coins → karma-type cap → per-event cooldown/cap → debit + karma + vetted `cmd` w/ tier +
  confirmation say), plus `!balance`/`!karma`/`!shop`/`!gift` and mod admin. `tools/test_economy.py`.
- `protocol.py` — added `say`/`status`/`control` constructors + `tier` on `command`.
- `app.py` — wired wallet+economy: award timer task, chat routed through economy AND the command
  engine (disjoint), a `dispatch()` that sends `say`→chat / `cmd`→X4; wallet saved on tick/shutdown.
  `--no-economy` / `--wallet` flags; smoke test opts out.
- `dashboard.py` — Economy card (viewers/coins) on the status page + a **`/catalog` item-list**
  page (search, tier filters, sort) backed by `/api/catalog` (= `catalog_view()`). The local twin
  of TT's item-list. **Playwright-verified with screenshots** (status + catalog).
- Suite: 9 test modules + smoke + playwright, ALL GREEN. Left for the live loop: MD cues + real
  X4 effects per catalog event, live Twitch OAuth, and the in-game Enable-Twitch panel.

## 2026-06-09 — StoreEvent schema locked in (catalog.py stub)
- Added the forward economy schema to `bridge/twitch_bridge/catalog.py` so a future session
  inherits the shape: `StoreEvent` dataclass (id, buy_key, cost/cost_per_unit+unit, karma, tier,
  cooldown, event_cap, on_event/reward, args, label/description/category, default_enabled/enabled)
  + `TIERS`/`KARMA` constants + `.display()` (the item-list projection) + `catalog_view()` (what
  `/catalog` and the export emit) + a representative `CATALOG` (all 4 tiers, fixed+variable cost,
  event-triggered). **Additive — the live `STARTER`/`CommandEngine` path is untouched**; the
  `!buy` dispatcher + coin/karma gating are still M4.0. Tested (`tools/test_catalog.py`, 28 checks);
  full suite green. Schema will evolve, but "rich record → many projections" is fixed.

## 2026-06-09 — Catalog as single source of truth + the "item-list" view (noted)
- Studied TwitchToolkit's **item-list** (`github.com/twitchtoolkit/item-list`): a static GitHub
  Pages site (Bootstrap + List.js) that renders flat JSON catalog data (`{abr, price, karmatype,
  category}`) as searchable/sortable tables, shared with viewers as a link. Data cleanly split
  from presentation — a great, simple pattern.
- **Design rule recorded in `docs/08` §10:** our `catalog.py` `StoreEvent` is ONE source of truth
  that must carry display metadata (label, description, category, tier, karma, cost/syntax,
  cooldown) so the SAME data drives the `!buy` engine AND any view. No second catalog.
- **Two surfaces, one schema:** a live local `/catalog` page on the companion dashboard server
  (enabled-only, current prices/cooldowns) + a shareable static export (the online TT twin, the
  `!purchaselist` link). Same JSON → same page code renders either. Slots into M4.0/M4.3.

## 2026-06-09 — Dashboard fix: survive source EOF (was: connection refused)
- Bug: a manually-started companion exited the instant its stdin source hit EOF, tearing down
  the dashboard → `ERR_CONNECTION_REFUSED`. Fix: when the dashboard is on, the process lingers
  (X4 link keeps retrying, UI shows source state) until Ctrl-C; tests pass `--no-dashboard` and
  keep the old exit-on-EOF behaviour. Launcher also made interpreter-robust (python3/python).
  Verified: after `</dev/null`, `GET /` → 200.

## 2026-06-09 — Companion dashboard (the "cute little UI") — BUILT ✅
A self-contained status UI for the companion, **stdlib only**, served as a localhost web page
(cross-platform, no GUI toolkit, reuses a browser tab; opens itself with `--open`).
- `status.py` — thread-safe `Status`: Twitch source state, X4 link state, counters
  (events in / commands / say-out), a newest-first activity feed, uptime, last error.
- `dashboard.py` — `ThreadingHTTPServer` in a daemon thread; embedded dark-theme HTML that
  polls `/api/status` every 1s with live dots + activity feed. Binds `127.0.0.1:17564`.
- Wired into `app.py` (records events/commands/actions; a poller mirrors the X4 link state)
  with `--no-dashboard` / `--dashboard-port` / `--open` flags and `X4_TWITCH_*` env vars.
- **Manual start option:** `bridge/run-companion.sh` (opens the UI). The other start path is
  the Steam launch wrapper. Both supported — per "give an option to start it manually."
- Tests: `tools/test_dashboard.py` (13 checks) + live-verified against the real bridge
  process (GET / and /api/status → 200). Full existing suite still green.

## 2026-06-09 — In-game process spawn via FFI — ❌ BLOCKED by X4 (tested, ruled out)
- **Hypothesis (wrong):** the mod could auto-launch the companion via LuaJIT FFI → libc
  `system()`, the same seam native mods use. We tested it directly.
- **Result:** X4 **restricts dangerous FFI calls even with Protected UI off.** Live error:
  `Access to FFI function 'system' is restricted!`, and `ffi.load("c")` / `ffi.load("libc.so.6")`
  are blocked too. Engine functions (`GetSaveFolderPath`, etc.) are whitelisted; libc is not.
  Lesson: the FFI "seam" is real but **guarded** — the multiplayer mod escapes it by shipping
  its *own* native lib (loaded via the Lua C-module path like LuaSocket), whose internal C is
  not subject to the whitelist. Plain `ffi.C.system` from Lua is a dead end.
- **Action:** removed the FFI spawn code from `ui/twitch_integration.lua` (kept a NOTE).
- **New direction for auto-start (no in-game spawn, no native code):** a **Steam launch-option
  wrapper** — `companion-launcher.sh %command%` co-launches the companion (single-instance
  guarded) and then X4. One-time paste in Steam → Launch Options (same place as the debug flag).
  Optional future: a tiny native Lua C `spawn` module (auditable source) for a no-launch-option
  experience, but that reintroduces the per-platform native build we deliberately avoided.
- **Testing-loop automation (deferred):** Wayland box, no input tools installed, X4 has no
  load-save launch arg. Can launch X4 + verify loads via the shared `<SAVE>/twitch.xml` signal
  without vision, but can't navigate the menu. Plan: install `xdotool`, script launch →
  "Continue" → poll for the socket. Fully headless impossible (Vulkan game needs GPU+display).

## 2026-06-09 — 🎉 Milestone 1 COMPLETE: bidirectional socket bridge proven live (X4 8.00)
The hardest, least-documented risk of the whole project — getting a socket open between
native-Linux X4 and an external process — is **retired**. `tools/socket_roundtrip.py` sent a
`ping` into the live `<SAVE>/twitch.xml`; X4 accepted the client, decoded the JSON, fired the
right MD cue, and wrote `{"t":"say","msg":"pong"}` back, which the probe printed. Full detail +
log in `docs/07` Track C.

**Six bugs only the live game exposed (all fixed):**
1. Bridge socket filename `x4_twitch.xml` → `twitch.xml` + autodiscover the `<id>` save dir.
2. content.xml dependency `id="sn_mod_support_apis"` → **`ws_2042901274`** (X4 matches the
   dependency's content *id*, not the folder name; every SN companion mod uses this).
3. `ui.xml` belongs at the **extension root**, with `<file name="ui/<name>.lua"/>` (full path).
4. **Protected UI Mode** must be OFF (else Lua `package` is nil + non-whitelisted `require` blocked).
5. MD filename must be **lowercase** (`twitch_integration.xml`) — X4's Linux VFS lowercases
   paths, so a capitalized file isn't found on a case-sensitive disk. *The main unlock.*
6. Start the read on **`md.Named_Pipes.Reloaded`** (not `event_game_started`, which is too
   early); and X4 pipe writes have **no trailing newline** → append `'\n'` in `Twitch_Say`.

## 2026-06-09 — X4 installed; filesystem bring-up
- Confirmed native ELF **X4 8.00**, not Proton. Installed bekopharm `linux-compat`
  `sn_mod_support_apis` + our mod into `<X4>/extensions/`. LuaSocket 5.1 obtained without root
  (`dnf download` + `rpm2cpio | cpio`) into `c_library/socket/`. Details: `docs/07` Track B.

## 2026-06-09 — Knowledge base: design layers added
- **`docs/08`** — viewer economy & events, ported from RimWorld's TwitchToolkit (coin wallet,
  karma governor, `!buy` store, 4 severity tiers, voting). Two-axis model (severity × karma)
  improves on TT's single field.
- **`docs/09`** — onboarding/OAuth/companion UX: why Twitch can't live fully in-game (sandbox
  has no network, unlike RimWorld's C# mod), where OAuth happens, the in-game-setup primary flow.

## (pre-2026-06-09) — Architecture resolved; bridge + mod scaffolded
See `docs/00`–`06`: native-Linux + LuaSocket path, Unix-domain socket in the savegame folder,
Python `twitchAPI` bridge, newline-JSON line protocol, command/policy engine. Milestones 2–3
scaffolded and headless-tested before the game was installed.
