---
name: x4-modding
description: Modding the X4 Foundations extensions in this repo (twitch_arena world content, twitch_integration bridge). Use when a task needs to know how the BASE GAME does something — gamestarts, god.xml station/HQ placement, building stations from construction plans, Mission Director scripts, maps/galaxy/sectors/gates, custom FACTIONS (their NPCs, licences, wares, jobs/economy), HQ research & mentors, map reveal — or when editing, deploying, testing, or DEBUGGING the mod (a cue doing nothing, null values, an empty or unstaffed station, "my change had no effect"). Bundles a .cat/.dat extractor so you inspect real vanilla files instead of guessing, plus the MD schema-validation and x4debug.txt recipes.
---

# X4 Foundations modding (this repo)

**READ THE SHARED GUIDE FIRST: `../X4_Mods/.claude/skills/x4-modding/SKILL.md`.** It holds
everything that is true for any X4 mod: the golden rule (extract the vanilla file, never
guess), the base-game-only survey, the MD expression traps, cue conditions, two values in
one cue, comm popups and voices, vanilla properties, what reloads when, x4debug.txt, and
the mechanisms proven here (HQ, gates, map reveal, complete stations, custom factions in
`references/custom-factions.md`, diffs). It moved to X4_Mods (board x4, r5) because every
X4 board shares it; this file keeps only what is specific to X4_TwitchMod.

## Tools (shared, run from this repo's root)
- Extract vanilla files: `py .claude/skills/x4-modding/extract_x4.py --list <name>` (a shim
  over `../X4_Mods/.claude/skills/x4-modding/extract_x4.py`; same arguments).
- MD checks: `python3 bridge/tools/test_md_lint.py` and `py.exe bridge/tools/validate_md.py`
  (shims over `../X4_Mods/tools/`, which check this repo's extensions and `$Build`).
- `py bridge/tools/check_macros.py "<X4>"` audits every `macro.<name>` and `macro="<name>"`
  in our MD against the base archives + `extensions/ego_dlc_*` only; run it after touching
  any macro reference.
- Running X4 for a test: `py.exe bridge/tools/x4_run.py run` (a shim over
  `../X4_Mods/tools/x4_run.py` that runs `deploy.ps1` first).

## Deploy
- Edit in the repo, then run **`./deploy.ps1`** — it mirrors both extensions into `E:\steam\…\extensions` (preserving twitch_integration's `companion/`). `install.sh` is Linux-only **and never deployed twitch_arena**, so on Windows always use `deploy.ps1`. A stale deploy looks exactly like "my changes do nothing" — the #1 time-sink; verify the deployed file after copying.
- **Build stamp**: bump the `$Build` literal in `Twitch_Say` on EVERY edit of
  `twitch_integration.xml`; `test_md_lint.py` fails an MD edit that did not.

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
