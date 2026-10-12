---
name: x4-modding
description: Modding the X4 Foundations extensions in this repo (twitch_arena world content, twitch_integration bridge). Use when a task needs to know how the BASE GAME does something — gamestarts, god.xml station/HQ placement, building stations from construction plans, Mission Director scripts, maps/galaxy/sectors/gates, custom FACTIONS (their NPCs, licences, wares, jobs/economy), HQ research & mentors, map reveal — or when editing, deploying, testing, or DEBUGGING the mod (a cue doing nothing, null values, an empty or unstaffed station, "my change had no effect"). Bundles a .cat/.dat extractor so you inspect real vanilla files instead of guessing, plus the MD schema-validation and x4debug.txt recipes.
---

# X4 Foundations modding (this repo)

## Golden rule: read the vanilla file, don't guess
X4 modding is unforgiving — a wrong macro-name case, diff `sel`, or connection path fails silently or **crashes new-game generation at ~90%**. Whenever you need to know how the base game does something, **extract the real file and mirror it exactly** (names, attribute case, structure, `../` path depth).

### Extract vanilla game data
Data lives in `E:\steam\steamapps\common\X4 Foundations\NN.cat` (text index) + `NN.dat` (blob). No `XRCatTool.exe` is installed here. Use the bundled script:

```bash
# find the in-archive path for something
py .claude/skills/x4-modding/extract_x4.py --list headquarters
# extract files to inspect
py .claude/skills/x4-modding/extract_x4.py libraries/god.xml libraries/gamestarts.xml md/gs_boso.xml --out ./_scratch
```

**Survey the BASE GAME ONLY — never "every .cat in the install."** Third-party mods are
installed here too, and a macro of theirs looks exactly like a vanilla one.
`station_arg_defence_base_01_macro` is indistinguishable from a base-game station hull and
ships in `faction_fix_pack`; referencing it gave `Property lookup failed:
macro.station_arg_defence_base_01_macro` at load, a null macro, and a station that silently
never built. The mod has to work on a plain X4 + DLC install, so that is the only bar that
counts. `py bridge/tools/check_macros.py "<X4>"` audits every `macro.<name>` and
`macro="<name>"` in our MD against the base archives + `extensions/ego_dlc_*` only — run it
after touching any macro reference.

**DLC content is in separate archives** — `extensions/ego_dlc_*/ext_NN.cat` (Timelines, Terran, Boron, Split, Pirate, `ego_dlc_mini_02` = Hyperion, …), not the base `NN.cat`. Point the extractor at the DLC folder to inspect it: `py extract_x4.py --x4 "E:/steam/.../extensions/ego_dlc_timelines" --list gamestarts`. Each DLC's `libraries/gamestarts.xml` is a `<diff>` that adds its story situations to the base custom-start catalog.

High-value vanilla files:
- `libraries/gamestarts.xml` — gamestart defs (location, ship, `<research>`, `<universe><stories>` storystates). `libraries/gamestarts.xsd` = schema.
- `libraries/god.xml` — station/object placement. Player HQ = `<station type="headquarters">` gated by `<quota gamestart="…"/>`.
- `libraries/constructionplans.xml` — e.g. `x4ep1_playerheadquarters_with_dock`.
- `md/x4ep1_mentor_subscription.xml` — Boso HQ mentor, research unlock (`$x4ep1_hq_research_unlocked`), tank room. **Hard-gated to the main galaxy.**
- `md/gs_scientist.xml`, `md/gs_boso.xml` — HQ-start setup (find HQ, assign manager, uncover map).
- `md/lib_generic.xml` — `UncoverMap_SectorsAndGates`.
- `maps/XU_ep2_universe/{galaxy,clusters,sectors,zones}.xml` — the main galaxy (macro name in file is `XU_EP2_universe_macro`).
- `md/*.xml` in bulk when hunting a mechanism (`--list md/` then grep the dump).
- `libraries/md.xsd` + `libraries/common.xsd` — the MD **schema**. See next section.

### Validate MD against the game's own schema
Cheapest bug-per-minute in this repo. The extractor flattens `libraries/`, so the
schema's own `<xs:include schemaLocation="common.xsd"/>` resolves:

```bash
py.exe bridge/tools/validate_md.py            # every extensions/*/md/*.xml; extracts the xsd on first use
py.exe bridge/tools/validate_md.py --plant    # + a planted signal_cue param that must FAIL
py.exe bridge/tools/validate_md.py --serve &  # optional: compile once (~2 min), later runs take 0.2 s
```
Windows `py` has lxml; WSL's python3 does not. Compiling the schema costs ~2 min each
time (common.xsd's content model; lxml cannot pickle it), hence the optional server.

Real bugs it caught here that reading vanilla by eye did not:
- `add_faction_relation` has `reason` **`use="required"`** (77/77 vanilla calls pass one).
  Omitting it made the action a no-op. `set_faction_relation` does NOT require it — and
  set_ is what vanilla diplomacy uses for NPC↔NPC standing (add_ is a *decaying boost*).
- `signal_cue` accepts **neither `param` nor `delay`** (vanilla writes neither, ever).
  Only `signal_cue_instantly` takes `param`; a delay must live in a `<delay>` element on
  the **target** cue. An ignored `delay="2s"` turned a retry into a ~60/second hot loop.

Well-formedness is a separate, brutal failure mode: **`--` is illegal anywhere inside an
XML comment**, so one `<!-- ---- section ---- -->` makes the whole mdscript unparseable
and X4 loads *none* of it. Draw comment rules with `=`. `py -c "import
xml.etree.ElementTree as ET; ET.parse('<file>')"` catches it in a second.

## MD expression traps (each of these cost a full debugging round)
- **`$var?` asks "is this variable DEFINED", not "is it non-null".** `<set_value
  name="$x" exact="null"/>` *defines* `$x`, so `$x?` is **true** while `$x` is null and
  every `not $x?` guard silently never fires. Same for `<set_value exact="@anything"/>`
  — the `@` yields null on failure and the variable still ends up defined. Vanilla never
  writes `?` after a null assignment; it compares (`== null` / `!= null`, ~195 uses).
  Use `?` **only** for a variable that may never have been assigned at all (an unpassed
  `<param>`, a `create_*` output on the failure path).
- **`and` inside a `do_while` condition** broke a whole cue here. Nest `do_if`s instead;
  `and` in a `do_if` is fine.
- **String `+` with a float** is fragile — use the format form `'…%s…'.[$val]`.
- Numbers/tables do **not** marshal Lua→MD via `AddUITriggeredEvent`; only strings do.
  Join multi-value payloads into one string, and build that string from an **ordered JSON
  array** — a JSON object decodes to a Lua hash table whose `pairs()` order is undefined
  and will silently swap your args.
  Corollary: MD also has **no string→number conversion**, so the bridge can never name a
  numeric thing (a text line id, a quantity). Anything numeric must be resolved MD-side —
  either from a string via `indexof` on a parallel list, or held entirely in MD (see
  the generated `md/twitch_boso_lines.xml` pool).
  Second corollary: MD **cannot split a string** (the `string` datatype has exactly one
  property, `format`), so ONE joined payload = ONE usable value. See *Getting TWO values
  into one MD cue* below; the other way out is to put one value in the **command id** —
  one cue per value, best when that axis is small and fixed (station TYPE in the cue,
  SECTOR in the arg).
- **A same-script `<library>` is called by BARE name**: `run_actions ref="MyLib"`. The
  `md.<Script>.<Lib>` form is for CROSS-script calls only — vanilla never uses it on its
  own libraries (0 occurrences in 223 files, vs 24 scripts calling their own libraries
  bare). Getting this wrong is a silent no-op.

## Cue conditions: what may be polled and what may not
- **A cue inside an `instantiate="true"` cue's subtree MUST have an event condition.**
  A cue whose `<conditions>` are bare `<check_value>`s is *polled* until they come true —
  correct and idiomatic for an ordinary cue (vanilla's own Boso call does exactly this,
  `story_paranid.xml` `Uni_3_Boso_Call`) — but **not** under an instantiated parent. The
  game rejects it at load:
  ```
  twitch_integration.xml(1944): Found non-event condition 'check_value', event condition required!
  ```
  and **a rejected cue is simply absent**, so the failure is silent in game: work handed
  to it disappears. Here a Boso call logged `boso_call queued …` and then nothing, forever.
- **`md.xsd` validates this file happily** — it is a load-time rule, not a schema rule.
  The cheap guard is a structural test: `bridge/tools/test_md_sync.py` walks the cue tree
  and fails if any cue under an instantiated cue lacks an `event_*` condition. Schema
  validation and that walk catch disjoint classes of bug; run both.
- **To wait for a state under an instantiated cue**, use a signalled loop instead:
  `<event_cue_signalled/>` + a `<delay>` + re-`signal_cue` itself while work remains
  (`Twitch_RetryRead`, `Twitch_BosoPump`). Keep the queue/state on a separate **top-level**
  cue so one name resolves it from anywhere; `static.$var` inside the instantiated cue
  works for a plain counter shared across its instances (vanilla idiom, ~20 uses).
- **A self-signalling loop cannot carry state in the signal.** `signal_cue` takes neither
  `param` nor `delay`; only `signal_cue_instantly` takes `param`, and it does not wait for
  the target's `<delay>`. So a delayed re-arm must park its state on a cue variable.
  `Twitch_RankWatch` once re-armed with `signal_cue … param="$metrics"`; the param was
  **silently dropped**, its baseline never carried and no rank-up was ever announced.
  It now keeps the snapshot in `static.$prev` (Start nulls it to force a seed tick).
- **Timeouts in such a loop must be wall-clock**, not a pass counter: N queued items mean
  N loops all touching the same head entry, so a counter expires ~N× early. Stamp
  `player.age + <timeout>` on the entry and compare against `player.age`.
- **MD cannot split a string.** `scriptproperties.xml`'s `string` datatype has exactly
  ONE property: the format operator `'…%s…'.[$x]`. No split, no substring, no indexof.
  Plan every payload around that — see the two-string trick below.

## Getting TWO values into one MD cue
The event carries **three** strings — common.xsd on `<event_ui_triggered>`: *"param =
screen ID, param2 = control ID, param3 = screen parameters"* — and **`control` is
optional** (vanilla ships the control-less form, e.g. `screen='DockedMenu'`). So a 2-arg
command is emitted on a screen of its own with the args in the control and value slots:

```lua
AddUITriggeredEvent("Twitch_" .. control, vals[1], vals[2])   -- ui lua
```
```xml
<event_ui_triggered screen="'Twitch_adopt_ship'"/>   <!-- NO control filter -->
<!-- event.param2 = arg1, event.param3 = arg2 -->
```

Three or more values have nowhere to go — there is no fourth slot. Either compose them
bridge-side into one string, or split the work into two commands.

## Watching a SET of objects with one cue
`<event_object_destroyed>` (and its family) takes **`group=`** instead of `object=`, and
common.xsd promises *"Adding/removing group members is possible even after the event is
set up."* So one cue watches N objects — the group IS the subscription list:

```xml
<cue name="Watch">                       <!-- static parent owns the group -->
  <actions><add_to_group groupname="$Watched" list="[]"/></actions>   <!-- must EXIST -->
  <cues>
    <cue name="Died" instantiate="true">
      <conditions><event_object_destroyed group="parent.$Watched"/></conditions>
```
- Children reach the parent's group as `parent.$Watched` (vanilla: `parent.$InteriorGroup`).
- Create it **empty up front** — the event requires the group to exist ("may be empty").
- X4 removes a destroyed object from its groups automatically; no cleanup needed.
- `check="false"` on `add_to_group` when re-arming from a list that may contain dead
  objects, or every stale entry logs an error.

## Making an NPC "video call" the player (comm popup + real voice)
**X4 ships no pre-rendered video at all** — there is not one `.ogv`/`.bik`/`.mp4`/`.webm`
in any archive. The "video call" is the comm popup: the NPC is **live-rendered and
lip-synced** on the cockpit monitor, playing a recorded `.ogg`, captioned with that line's
own text. So "play a clip" always means "make an actor speak", never "show a file".

One call does the whole thing (`md/lib_dialog.xml:776` documents every param):
```xml
<run_actions ref="md.LIB_Dialog.Speak_Actor_Run">
  <param name="Actor" value="md.$PersistentCharacters.$BosoTa"/>
  <param name="Lines" value="[[30202113]]"/>   <!-- [[id, delay, signalcue], …] -->
  <param name="ForceCutscene" value="true"/>   <!-- $ignoredistance: monitor even if near -->
  <param name="IsInMission" value="false"/>
</run_actions>
```
- **Named characters are globals**: `md.$PersistentCharacters.$BosoTa` / `$DalBusta`, set by
  vanilla `md/setup.xml`. Never spawn or track them. Null if that story never ran.
- **The monitor cutscene key is already on them** — `setup.xml` sets
  `$BosoTa.$cutscenekey = table[$key='ShowCharacterBoron']` and LIB_Dialog reads that tag
  itself (`lib_dialog.xml:97`), so you rarely pass `CutsceneKey`. Keys live in `cutscenes/`
  (`show character *.xml`, `show_npc_face*.xml`).
- For a **ringing call the player accepts**, drop to `play_cutscene targetmonitor="true"` +
  `<interaction>` + `event_player_interaction`, then `start_conversation` — vanilla's shape
  at `md/story_paranid.xml:14350`.
- **Guard it** the way vanilla does (`story_paranid.xml:14344`): skip while
  `player.isinconversation or player.isinfullscreenmenu or player.isscreenshotmode`, or the
  cutscene is swallowed. Better: queue and retry (see the cue-conditions section).

### Finding an actor's voice lines
- A character macro's `<identification page="NNNNN"/>` (`libraries/character_macros.xml`) is
  its **voice page**. Boso Ta = `character_boron_hq_mentor_macro`, page **10201**.
- Audio is one file per line: **`voice-l044/<page>/comm/<line>.ogg`** (l044 = English; also
  `normal/`, `comm_npc/`, and a `lipsync/*.xpm`). Extract with `--list` to enumerate.
- Text for the same id is page `<page>` in `t/0001-l044.xml`. Line ids are `<page><line>`
  concatenated, so `<speak>`'s `line="30202113"` resolves against the *speaker's* page.
- **A line id with no `.ogg` plays silently** — indistinguishable in game from the cue not
  firing. Verify presence in the voice folder before using an id, always.
- Voice pages are **shared per voice, not per character** (10201 is "Boron NPC 1 / Boron rep
  / Misc Plot Characters"), so they mix plot dialogue with generic NPC chatter. All of it is
  in that actor's voice. Filter out `(* … *)` headers, `{page,line}` redirects, `$PLACEHOLDER$`
  text, and lines with stage directions mid-string (`"…EMPs.(pronounced Ee-Em-Pees)"`) — a
  leading `(annoyed)` tag is stripped by the game, anything later is drawn in the subtitle.
- Worked example: `bridge/tools/gen_boso_lines.py` → `md/twitch_boso_lines.xml` (1263 lines).
  Chunk big literals — the largest list literal in vanilla MD is 8674 chars.
- A destroyed object is still READABLE in the handler — vanilla's
  `ObjectInvincibilityManager` logs `event.object.macro/.sector/.position` there. Capture
  what you need at that moment; it is the last one. `event.param` is the killer.

## Useful vanilla properties (verified this project)
- `object.idcode` — "AAA-123", a stable, unique, token-safe handle. The right join key
  when an external process needs to name a ship; names are display-only.
- `destructible.hullpercentage` / `.shieldpercentage` — 0..100, ready to show.
- `player.headquarters` — the player HQ, `.exists`-guardable. `$Faction.headquarters` too.
- `faction.relation.<range>.min|mid|max` (`kill`, `enemy`, `neutral`, `friend`, `ally`,
  `dock`) — ask a faction where its OWN bands are instead of hardcoding a number, which
  is "war" for one faction and merely rude to another. Prefer `.mid`: scriptproperties
  notes the bounds are exclusive for some ranges.
- `<clear_object_name object="$x"/>` — "revert to default". Use this to undo a rename;
  writing the type name back looks identical on a stock ship but destroys a name the
  PLAYER chose.
- `find_ship_by_true_owner faction="…" space="player.galaxy" multiple="true"` — the
  efficient fleet scan (the docs say so explicitly vs `find_ship` with a trueowner filter).

## Deploy + test
- Edit in the repo, then run **`./deploy.ps1`** — it mirrors both extensions into `E:\steam\…\extensions` (preserving twitch_integration's `companion/`). `install.sh` is Linux-only **and never deployed twitch_arena**, so on Windows always use `deploy.ps1`. A stale deploy looks exactly like "my changes do nothing" — the #1 time-sink; verify the deployed file after copying.
- **What reloads when** — get this wrong and a correct fix looks broken:
  | changed | takes effect on |
  |---|---|
  | `md/*.xml`, `ui/*.lua` | **loading a save** (or restarting X4) |
  | gamestart / map / god / galaxy | a **NEW game** (arena + main sector are `save="true"`) |
  | the bridge/companion (Python) | restarting the companion only — the game side is untouched |

  Copying files into `extensions\` while X4 runs changes nothing in the running session.
- **Put a build stamp in the mod's chat output** (one literal, in `Twitch_Say`, bumped on
  every MD edit). "Stale script" and "broken fix" are indistinguishable from chat
  otherwise — that ambiguity ate two full rounds here. If the tag in chat isn't the tag
  in the file, the game is on an old script; load a save.
- To see MD `debug_text` and diff/load errors: Steam → X4 → Launch Options `-debug all -logfile x4debug.txt`; the log lands under the **numeric user-id folder**: `<HOME>\Documents\Egosoft\X4\<id>\x4debug.txt` — there is normally exactly one `<id>` directory, so `ls ~/Documents/Egosoft/X4/` finds it. (Placeholders, not the real path: this file is committed to a public repo, see `SECURITY.md`.)
  **Read it FIRST when a cue misbehaves, not after a third guess.** It names the failing
  expression, action and line:
  ```
  grep -n "Twitch_OnFactionIncident" x4debug.txt | tail -20
  [=ERROR=] Error in MD cue …: Evaluated value 'null' is not of type faction
  * Expression: $facA   * Action: <add_faction_relation>, line 568
  ```
  The **absence** of an error is evidence too: no error before the failing action means
  the code above it ran and its guards evaluated the way the engine wanted, not the way
  you read them. That is what pinned the `$var?` trap above.
  A cue's `debug_text` also tells you which build is live — an old expression in the log
  means an old script in memory, no matter what is on disk.

## Mechanisms proven this project (see also memory: arena-hq-mechanism, windows-deploy)
- **Player HQ**: god.xml `<station type="headquarters" owner="player">` + `<quota gamestart="…"/>` + `constructionplan='x4ep1_playerheadquarters_with_dock'` `<level exact="1.0"/>`. Requires **god ENABLED** in the gamestart (`<god enabled="true"/>`) or the entry is silently ignored. Then assign a manager in MD: `create_control_entity post="controlpost.manager"` (SetupHQ adds defence/engineer, not a manager).
- **Research/teleport + Boso/Dal mentors are hard-gated to the main galaxy** (`player.galaxy.macro == macro.xu_ep2_universe_macro`). A sealed custom galaxy can't have them. Fix: put the sector **in** the main galaxy via a same-path `<diff>` on `maps/XU_ep2_universe/galaxy.xml` (attach a new cluster).
- **Trigger mentors the proper way**: gamestart `<universe><stories><story ref="story_hq_boso" state="1"/><story ref="story_hq_dal" state="1"/></stories></universe>`. The base scripts read `gamestart.storystate.*`, find the player HQ, and install everything. Don't poke their namespace.
- **Pre-set ANY story situation** on a custom start the same way — one `<story ref="…" state="…"/>` per situation. Refs come from the custom-start catalog: base ones in `libraries/gamestarts.xml` under the `custom_creative`/`custom_budgeted` gamestarts (groups: hq_and_staff, diplomacy_network_situation, envoy_situation, timelines_situation, paranid_situation, …); DLC ones from that DLC's `gamestarts.xml` diff. Single-state stories use `state="1"` = done (cross-check the value the game sets via `set_userdata storystate="'…'" value="…"`). Refs used here: `story_diplomacy_network` (base), `story_envoy` (mini_02), `story_timelines_grandmother` / `story_timelines_quettanaut` (timelines). Add the DLC as an optional `<dependency>` in content.xml.
- **Gates**: `<connection ref="gates">` with a `props_gates_anc_gate_macro` in a zone on each end + a bidirectional `<connection ref="destination">` in the galaxy. Mirror a real vanilla gate's `../` path depth exactly (outer path 1×`..`, inner `<macro>` path 5×`..` for galaxy→cluster→sector→zone→gate).
- **Reveal the map**: `find_sector multiple="true"` (all sectors) → `set_known` on sector, `.cluster`, and gates. Compare sectors by **object identity** (`player.sector == $sector`), not macro compare (`player.sector.macro == macro.X` did not gate reliably). Put it in its own cue so an unrelated failure can't skip it.
- **Build a COMPLETE station at runtime**: `create_station` with a `constructionplan` id
  from `libraries/constructionplans.xml` **and** `state="componentstate.operational"` — it
  arrives fully built instead of as an empty construction site (vanilla shape:
  `md/scenario_advanced.xml`, `md/story_paranid.xml`, `md/x4ep1_mentor_subscription.xml`).
  `macro=` is the base HULL: `station_gen_factory_base_01_macro` is the universal one and
  is what vanilla pairs with most plans, including `arg_defence`; only tradestation and
  piratebase have their own. Landmark stations (Kha'ak hive) take **no** plan.
  Then hand it to the base game with `signal_objects object="player.galaxy"
  param="'init station'" param2="$Station" param3="true"` — see
  [references/custom-factions.md](references/custom-factions.md) §2 for what that does and
  the two ways it silently doesn't.
- **A custom faction cannot run a station out of the box.** It needs five separate things —
  people, staffing, goods, licences, logistics — and each gap fails silently and
  differently, with the station building fine every time. Full checklist, symptoms and
  generators: **[references/custom-factions.md](references/custom-factions.md)**.
- **Extensions patch base files** by placing a file at the same relative path with a `<diff>` root (used for `index/macros.xml`, `maps/XU_ep2_universe/galaxy.xml`, etc.). Diff `sel` string-matches attribute values → **match the exact case** in the base file.
  `<add sel="…">` **appends children** and never rewrites vanilla data — prefer it.
  `<replace sel="…/@attr">` is the only way to extend an attribute *list*, but it copies
  vanilla's value, so anything Egosoft later adds to that list is lost — those files must
  be **generated** and re-run after a game update. `silent="true"` makes an unmatched `sel`
  a no-op, which is what you want for DLC-only ids. Validate diffs against
  `libraries/diff.xsd` — but that only checks the patch grammar; to check the *content*,
  merge the diff onto the vanilla document and validate that against its real schema.

## Generated registries (never hand-maintain game data)
Anything the mod needs to know about game content is generated from the install, so names,
prices, macros and ids are the game's own. All live in `bridge/tools/`, all take the X4
path, all are re-runnable after a DLC install or game update:

| tool | writes | what it is |
|---|---|---|
| `gen_ships.py` | `twitch_bridge/ships.json` | every buyable warship + real credit value |
| `gen_sectors.py` | `twitch_bridge/sectors.json` | every sector of the playable galaxy + macro |
| `gen_characters.py` | `twitch_integration/libraries/characters.xml` | opens Argon NPC pools to the Twitch factions |
| `gen_ware_owners.py` | `twitch_integration/libraries/wares.xml` | makes twitchally an owner of equipment wares |
| `check_macros.py` | — | audits MD macro refs against base + official DLC only |
