---
name: x4-modding
description: Modding the X4 Foundations extensions in this repo (twitch_arena world content, twitch_integration bridge). Use when a task needs to know how the BASE GAME does something — gamestarts, god.xml station/HQ placement, Mission Director scripts, maps/galaxy/sectors/gates, HQ research & mentors, map reveal — or when editing, deploying, or testing the mod. Bundles a .cat/.dat extractor so you inspect real vanilla files instead of guessing.
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

## Deploy + test
- Edit in the repo, then run **`./deploy.ps1`** — it mirrors both extensions into `E:\steam\…\extensions` (preserving twitch_integration's `companion/`). `install.sh` is Linux-only **and never deployed twitch_arena**, so on Windows always use `deploy.ps1`. A stale deploy looks exactly like "my changes do nothing" — the #1 time-sink; verify the deployed file after copying.
- Gamestart / map / god changes only take effect on a **NEW game** (arena + main sector are `save="true"`). Loading a save keeps the old start.
- To see MD `debug_text` and diff/load errors: Steam → X4 → Launch Options `-debug all -logfile x4debug.txt`; log at `C:\Users\Simon\Documents\Egosoft\X4\x4debug.txt`. Reach for this before a 3rd guess.

## Mechanisms proven this project (see also memory: arena-hq-mechanism, windows-deploy)
- **Player HQ**: god.xml `<station type="headquarters" owner="player">` + `<quota gamestart="…"/>` + `constructionplan='x4ep1_playerheadquarters_with_dock'` `<level exact="1.0"/>`. Requires **god ENABLED** in the gamestart (`<god enabled="true"/>`) or the entry is silently ignored. Then assign a manager in MD: `create_control_entity post="controlpost.manager"` (SetupHQ adds defence/engineer, not a manager).
- **Research/teleport + Boso/Dal mentors are hard-gated to the main galaxy** (`player.galaxy.macro == macro.xu_ep2_universe_macro`). A sealed custom galaxy can't have them. Fix: put the sector **in** the main galaxy via a same-path `<diff>` on `maps/XU_ep2_universe/galaxy.xml` (attach a new cluster).
- **Trigger mentors the proper way**: gamestart `<universe><stories><story ref="story_hq_boso" state="1"/><story ref="story_hq_dal" state="1"/></stories></universe>`. The base scripts read `gamestart.storystate.*`, find the player HQ, and install everything. Don't poke their namespace.
- **Pre-set ANY story situation** on a custom start the same way — one `<story ref="…" state="…"/>` per situation. Refs come from the custom-start catalog: base ones in `libraries/gamestarts.xml` under the `custom_creative`/`custom_budgeted` gamestarts (groups: hq_and_staff, diplomacy_network_situation, envoy_situation, timelines_situation, paranid_situation, …); DLC ones from that DLC's `gamestarts.xml` diff. Single-state stories use `state="1"` = done (cross-check the value the game sets via `set_userdata storystate="'…'" value="…"`). Refs used here: `story_diplomacy_network` (base), `story_envoy` (mini_02), `story_timelines_grandmother` / `story_timelines_quettanaut` (timelines). Add the DLC as an optional `<dependency>` in content.xml.
- **Gates**: `<connection ref="gates">` with a `props_gates_anc_gate_macro` in a zone on each end + a bidirectional `<connection ref="destination">` in the galaxy. Mirror a real vanilla gate's `../` path depth exactly (outer path 1×`..`, inner `<macro>` path 5×`..` for galaxy→cluster→sector→zone→gate).
- **Reveal the map**: `find_sector multiple="true"` (all sectors) → `set_known` on sector, `.cluster`, and gates. Compare sectors by **object identity** (`player.sector == $sector`), not macro compare (`player.sector.macro == macro.X` did not gate reliably). Put it in its own cue so an unrelated failure can't skip it.
- **Extensions patch base files** by placing a file at the same relative path with a `<diff>` root (used for `index/macros.xml`, `maps/XU_ep2_universe/galaxy.xml`, etc.). Diff `sel` string-matches attribute values → **match the exact case** in the base file.
