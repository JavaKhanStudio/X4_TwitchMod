# 04 — Build Plan & Open Decisions

A staged plan that de-risks the hard parts first. Each milestone is independently testable.

## Guiding principle
**Prove the pipe before building the features.** The riskiest, least-documented part is
getting a socket open between native-Linux X4 and an external process via LuaSocket. Spike
that with a "hello world" *before* writing any Twitch or gameplay logic.

## Milestone 0 — Environment & facts to confirm
- [x] **Runtime decided: native-Linux X4 → Path B (LuaSocket).** X4 is owned on Steam but
      **not yet downloaded** (2026-06-08). Steam on Linux installs the native build by
      default — verify it's NOT forced to Proton in the game's Compatibility settings.
- [ ] After download: locate the X4 install + `~/.config/EgoSoft/X4/` savegame dir.
- [ ] Confirm X4 patch version (7.x?) → pick matching Mod Support APIs (CE fork for patch 7).
- [ ] Get a **LuaSocket built for Lua 5.1** working on Fedora (build `.so` if no package).

## Milestone 1 — "Hello socket" spike (THE de-risk)
Goal: text typed in an external process appears in X4, and vice-versa. **No Twitch yet.**
- [ ] `dnf install lua5.1-socket`; copy `socket/core.so` + `socket/unix.so` into the game
      lua path (`game/ui/core/lualibs/` or `.../sn_mod_support_apis/ui/c_library/socket/`).
- [ ] Install the bekopharm `linux-compat` `sn_mod_support_apis` (SN API ≥1.93); set the
      "Pipe Prefix Linux" option to the savegame path. Disable Protected UI Mode.
- [ ] Confirm the in-game socket appears in `~/.config/EgoSoft/X4/save/` and round-trips
      with `nc -U <socketfile>` (raw transport check, no MD yet).
- [ ] MD test cue: `Named_Pipes.Write` a line + `Named_Pipes.Read` (continuous) and print
      received lines to the in-game event log — proves the documented MD API works on Linux.
- [ ] Python client connects to the Unix socket, exchanges lines both ways.
- **Exit criteria:** reliable bidirectional line exchange via the Named Pipes MD API, no
      frame stalls.

## Milestone 2 — The Bridge ⇄ X4 line protocol  ✅ SCAFFOLDED (2026-06-08)
- [x] Bridge skeleton (`bridge/`, stdlib-only) with a **fake stdin Twitch source**.
- [x] Wire format locked (newline-JSON, `protocol.py`); `ready`/`hello` handshake;
      reconnect in `x4link.py`. **End-to-end smoke test passes** (`tools/smoke_test.sh`,
      both directions via `tools/mock_x4.py`).
- [x] X4 MD dispatcher cues per type (`md/Twitch_Integration.xml`) + Lua `json_decode`
      (`ui/twitch_integration.lua`, **unit-tested via lupa** against real bridge output).
- [ ] Remaining: validate the X4 side live (the `[VERIFY]` markers) once the game is in.

## Milestone 3 — Twitch read path (chat → game)  🟡 CODE DONE, pending live creds
- [x] Bridge: real EventSub source (`sources/twitch.py`) via **twitchAPI 4.5**.
      Auth + refresh via `UserAuthenticationStorageHelper` (token file, not in the mod).
      Subscribes chat / redeem / sub / cheer / raid / follow → normalized protocol lines.
      Helix `send_chat_message` for the `say` action. **Every method/scope/event-field
      name verified against the installed library** (`tools/test_twitch_api.py`).
- [ ] LIVE: create a Twitch dev app, set `TWITCH_CLIENT_ID/SECRET/CHANNEL`, run
      `--source twitch`, do the one-time OAuth, confirm events flow. (Needs creds.)
- [ ] X4: first real effect — e.g. `!ping` in chat → in-game notification naming the user.
- [x] **Permission/cooldown policy engine** built Bridge-side (`commands.py` + editable
      `catalog.py`): roles from chat badges, global + per-user cooldowns, chat-prefix and
      event triggers, arg parsing → emits vetted `cmd` messages. Unit-tested
      (`tools/test_commands.py`); X4 dispatch (`cmd`→action-id cue) tested via lupa.
- [ ] LIVE: one real gameplay command — `!spawn fighter` → MD actually spawns a ship.
- [x] **X4-side integration de-risked**: Named Pipes Read/Write syntax, `event.param3`,
      and `AddUITriggeredEvent(screen,control,value)` all verified against real source;
      `[VERIFY]` markers downgraded accordingly.

## Milestone 4 — Richer Twitch events
- [ ] Channel-point redemptions → in-game events (`channel_points_custom_reward_redemption.add`).
- [ ] Subs / bits / raids → scaled events (reinforcements, pirate attacks, economy shifts).
- [ ] A config menu in-game via **Simple Menu API** (toggle features, set channel, cooldowns).

## Milestone 5 — Game → Twitch feedback
- [ ] X4 emits events (player died, big kill, station built) → `{"t":"say",...}` → Bridge
      → `POST /helix/chat/messages`.

## Milestone 6 — Packaging & docs
- [ ] Startup story: one script to launch the Bridge; X4 auto-connects on load.
- [ ] README for install (deps, Protected UI off, tokens), and a `content.xml` ready for
      Nexus/Workshop if we ever publish.
- [ ] Decide distribution: depend on bekopharm fork vs. vendor LuaSocket loader.

## Open decisions (resolve as we go)
| # | Decision | Notes |
|---|----------|-------|
| D1 | Native-Linux X4 vs Proton | ✅ **RESOLVED: native-Linux (Path B / LuaSocket).** |
| D2 | Transport: localhost TCP vs Unix socket | ✅ **RESOLVED: Unix domain socket** in the savegame folder — the bekopharm fork's proven, maintained path. See doc 06. |
| D3 | Bridge language: Python vs Node | ✅ **RESOLVED: Python + `twitchAPI`** (ecosystem fit, EventSub+Helix+OAuth built in). |
| D4 | Transport native lib | ✅ **RESOLVED: depend on + vendor a pinned copy of bekopharm `linux-compat` fork** (MIT, 8.x-maintained). No custom C shim. `lua5.1-socket` is on Fedora. See docs 05 & 06. |
| D5 | Wire format: JSON lines vs `|`-delimited | ✅ **RESOLVED: newline-JSON, decoded in Lua** (`ui/twitch_integration.lua` `json_decode`, unit-tested). MD branches on a typed event, never parses strings. |
| D6 | Where command policy lives | ✅ **RESOLVED (direction): Bridge owns perms/cooldowns/rate-limits; X4/MD owns effects.** To implement in Milestone 3. |
| D7 | Token storage | ✅ **RESOLVED: Bridge-owned file** `~/.config/x4-twitch-bridge/tokens.json` (`config.py`); gitignored; never in the extension. |

## What to build first, concretely
When we resume coding: **Milestone 0 → Milestone 1 spike.** Don't touch Twitch until the
socket round-trips. The spike is ~1 small Lua file + ~1 MD file + ~20 lines of client.
