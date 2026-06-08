# 01 — X4: Foundations Modding Basics

Distilled reference for how X4 mods (called **extensions**) are structured and how code
runs. Sources in `references.md`. **[VERIFY]** = confirm against a real install/wiki.

## Extension folder layout

A mod is a folder under `<X4>/extensions/<your_mod_id>/`. The game overlays every
extension's files on top of the base game (a virtual filesystem merge). Typical layout:

```
extensions/twitch_integration/
├── content.xml          # REQUIRED — mod manifest/metadata + dependencies
├── md/                  # Mission Director scripts (XML game logic)
│   └── Twitch_Integration.xml
├── aiscripts/           # AI behaviour scripts (XML) — optional
├── ui/                  # Lua UI code (the only place real code runs)
│   ├── ui.xml           # registers/loads our Lua files
│   └── twitch_socket.lua
├── libraries/           # XML game data (wares, etc.) — optional
├── assets/              # ship/station/visual components — optional
└── t/                   # text/localization files (0001.xml, page IDs) — optional
```

During development you can keep the folder loose (unpacked). For distribution it gets
packed into `ext_01.cat` / `ext_01.dat` catalog files (the WorkshopTool / X4 Customizer
or `XRCatTool` does this). Unpacked is fine for our whole dev cycle.

## content.xml (the manifest)

Minimal shape **[VERIFY exact attributes against wiki]**:

```xml
<?xml version="1.0" encoding="utf-8"?>
<content id="twitch_integration"
         name="Twitch Integration"
         description="Two-way Twitch chat/events integration for X4."
         author="Simon"
         version="100"            <!-- integer: 100 = v1.00 -->
         date="2026-06-08"
         save="0">                <!-- 1 if the mod must be flagged in savegames -->
  <!-- Depend on the Mod Support APIs (LuaSocket-enabled fork) -->
  <dependency id="sn_mod_support_apis" version="..." optional="false"/>
  <text language="44" .../>       <!-- per-language name/description -->
</content>
```

- `version` is an **integer**; UI shows it as version/100.
- `dependency` controls load order and warns if the dependency is missing.
- `id` must match the folder name and be globally unique.

## Mission Director (MD) — the game-logic layer

MD scripts are XML living in `md/`. The core concepts:

- **`<cue>`** — a named event handler. Has `<conditions>` (when it fires) and
  `<actions>` (what it does, run top to bottom).
- **`instantiate="true"`** — make a fresh instance each time conditions match (vs. a
  one-shot library cue).
- **`<conditions>`** typically contain an **event** node, e.g. `<event_cue_signalled/>`,
  `<event_object_destroyed/>`, `<event_player_..."/>`, or a timed `<check_value>` loop.
- **`<actions>`** can run game commands: spawn objects, create missions, set variables
  (`<set_value>`), do maths/strings, and crucially **`<raise_lua_event>`** to talk to the
  Lua side, and receive `event_ui_triggered` back.

Minimal MD skeleton:

```xml
<?xml version="1.0" encoding="utf-8"?>
<mdscript name="Twitch_Integration" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
  <cues>
    <cue name="Init" instantiate="false">
      <conditions>
        <event_game_loaded/>     <!-- runs once when a save loads -->
      </conditions>
      <actions>
        <set_value name="$started" exact="1"/>
        <!-- kick off the socket connect on the Lua side -->
        <raise_lua_event name="'Twitch.Connect'"/>
      </actions>
    </cue>
  </cues>
</mdscript>
```

### MD ⇄ Lua bridge (the key mechanism)
- **MD → Lua**: `<raise_lua_event name="'SomeName'" param="'payload'"/>`. The Lua side
  registers with `RegisterEvent("SomeName", handlerFn)`.
- **Lua → MD**: Lua calls `SignalToMD` / the engine `AddUITriggeredEvent(...)`, and MD
  catches it with a cue whose condition is `<event_ui_triggered screen="..." control="..."/>`.

This MD↔Lua loop is exactly how the Mod Support APIs (and our socket layer) move data.
Twitch event arrives on socket → Lua reads it → Lua raises a UI-triggered event → MD cue
fires → MD spawns a ship. And the reverse for game→Twitch.

## UI / Lua layer — where real code runs

Lua is X4's only general-purpose scripting. It powers the HUD/menus and, for us, the
socket I/O. Lua files are registered via a `ui/ui.xml` that the game reads.

**Loading Lua — important gotcha:** the old `Lua_Loader.Load` MD-event method
(SirNukes) **no longer works** on current patches; load via `ui.xml` `<addon>` instead
(the X-Rebirth-style mechanism that still works in X4). Example `ui/ui.xml`
**[VERIFY exact schema]**:

```xml
<?xml version="1.0"?>
<addon name="twitch_integration" id="twitch_integration">
  <environment type="menus">
    <file name="twitch_socket"/>          <!-- loads ui/twitch_socket.lua -->
  </environment>
  <dependency id="sn_mod_support_apis"/>
</addon>
```

### The Lua sandbox — what's missing
- **No `io`, no `os.execute`, no built-in sockets, no `require` for arbitrary modules**
  in "protected UI mode."
- **Protected UI Mode must be DISABLED** (Settings → Extensions) to allow `require` and
  side-loaded native libraries like LuaSocket. This is mandatory for our networking and
  for the Mod Support APIs' pipe/socket features. (Disabling it is the standard ask of
  every external-integration mod.)
- Available to us: the engine's `ffi`/C bindings exposed by Mod Support APIs, the FFI to
  read game state, timers, and (once side-loaded) `socket.core`.

## Useful tooling

- **X4 Customizer** (`bvbohnen/X4_Customizer`) — Python tool to read/transform game files,
  generate diffs/patches, and pack catalogs. Good for inspecting vanilla files.
- **XRCatTool / XR Catalog tools** — unpack/pack `.cat`/`.dat`.
- **X Community Wiki** (`wiki.egosoft.com`) — authoritative MD/AI script + UI reference.
- **ratilicus/x4**, **kuertee/x4-mod-ui-extensions** — example mod repos to crib patterns.

## XML patching vs. new content
To change a vanilla file, ship a same-path file using **XML diff/patch** (`<diff>` with
`<add>/<replace>/<remove sel="xpath"/>`). To add new content, just include new files.
Our mod is mostly *new* MD/Lua, so we mostly add; we may patch a gamestart or wares only
if we add custom Twitch-spawned content.
