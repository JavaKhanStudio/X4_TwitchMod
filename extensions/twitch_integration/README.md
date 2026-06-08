# twitch_integration (X4 extension)

The in-game half of the Twitch integration. Install into `<X4>/extensions/`.

## Files
```
content.xml                     manifest; depends on sn_mod_support_apis
md/Twitch_Integration.xml       game logic: pipe read loop, typed-event dispatch, outbound 'say'
ui/ui.xml                       loads the Lua into X4's menu environment
ui/twitch_integration.lua       JSON decode + re-emit each line to MD as a typed event
```

## How it fits together
```
bridge ──Unix socket── Named Pipes API ──raw line──▶ MD Twitch_OnPipeData
                                                       └▶ raise 'Twitch.Decode' ─▶ Lua onDecode
                                                                                     └▶ json_decode
                                                                                     └▶ signal_md(type,line)
                                                       ┌─ MD Twitch_On<Type> ◀───────┘ (event_ui_triggered)
                                                       └▶ game effect (TODO)
game effect ─▶ MD Twitch_Say ─▶ Named Pipes API ─Write─▶ bridge ─▶ Twitch
```
MD owns transport + effects; Lua does only JSON. See `../../docs/06-ecosystem-survey.md`.

## Prerequisites (native Linux)
1. Install the **bekopharm `linux-compat`** `sn_mod_support_apis` (SN API ≥ 1.93).
2. `sudo dnf install lua5.1-socket`; copy `socket/core.so` + `socket/unix.so` into the
   game lua path (`game/ui/core/lualibs/` or `.../sn_mod_support_apis/ui/c_library/socket/`).
   **Copy, don't symlink** (X4 ≥7.x rejects symlinks).
3. Settings → Extensions → **disable Protected UI Mode**.
4. Set the Named Pipes API **"Pipe Prefix Linux"** option to the savegame path so pipe
   `twitch` maps to `~/.config/EgoSoft/X4/save/twitch...`. Point the bridge `--socket` there.

## Status / `[VERIFY]` markers (confirm on first run with the game)
- Exact `content.xml` / `ui.xml` attribute schemas.
- `Named_Pipes.Read` continuous-mode param keys and `Named_Pipes.Write` keys.
- The `AddUITriggeredEvent(...)` argument shape and which `event.paramN` carries the payload
  (isolated in `signal_md()` in the Lua, and `event.param3` in the MD cues).
- `<debug_text>` is the placeholder effect; replace the `TODO`s with real gameplay.

The Lua `json_decode` is unit-tested against the bridge's real output (see
`bridge/` testing) — the parsing logic is known-good; only the X4 glue needs live VERIFY.
