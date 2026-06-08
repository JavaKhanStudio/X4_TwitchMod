# 06 — X4 Modding Ecosystem Survey (verified, decision-oriented)

> Synthesized from a deep-research pass: ~75 claims adversarially fact-checked (3-vote),
> **59 upheld / 16 refuted**. The 16 refutations were almost all the same over-reach —
> "Linux needs Proton" — repeatedly disproven by the bekopharm native fork. Every fact
> below is from upheld, primary-sourced claims. (The research harness's synthesis step
> crashed on output size; this report was hand-synthesized from the verified verdicts.)
> Verdicts archived in the run journal; sources consolidated in `references.md`.

## Headline corrections to earlier docs (read these first)

1. **X4 is at the 8.x era** (8.0 "Diplomacy"), not 7.x. Pin everything to 8.x.
2. **The "Community Edition" Mod Support APIs fork is DEAD for our purposes.** The CE fork
   (`iomatix/x4-projects`, forked from Chryssie) was **archived read-only on 2025-09-18**
   and only ever targeted **X4 7.X**. Its own maintainer says it's **no longer needed** for
   8.x — the **original SirNukes/bvbohnen API resumed being the most-updated working
   version**. → For 8.x, use the **original**, not CE. (This reverses doc 02's old advice.)
3. **Fedora DOES package `lua5.1-socket`** (`packages.fedoraproject.org/pkgs/lua-socket/
   lua5.1-socket`). My earlier "we'll have to build it ourselves" worry was wrong. This is
   a big de-risk for the Linux transport.
4. **The native-Linux two-way bridge already exists, is MIT-licensed, and is maintained to
   8.x** (bekopharm fork). We do **not** need to write our own C/C++ native lib. The whole
   "C++ route" question (doc 05) is settled: not needed.

## The landscape, ranked for OUR use (native-Linux two-way bridge)

### Tier 1 — what we should actually depend on

**`bekopharm/x4-projects` (branch `linux-compat`) — the Linux LuaSocket fork** ✅
- **What:** a fork of `bvbohnen/x4-projects` `sn_mod_support_apis` that ports the **Named
  Pipes API to native Linux** by side-loading **LuaSocket** and running a **Unix-domain-
  socket server inside X4** (no Windows pipes, no Python mediator needed).
- **Mechanism (verified from source):** `pipes.lua` OS-detects via
  `package.config:sub(1,1)` — `"\\"` → `winpipe` (Windows), `"/"` → `linpipe` (Linux).
  `linpipe.lua` does `require("socket.unix")`, `server:bind(file)`, `server:listen()` —
  **X4 acts as the socket SERVER**. `linux_pipe.lua` exposes `write()` (`client:send`) and
  `read()` (`client:receive("*l")`) — **genuinely bidirectional**. Modules are registered
  via `Register_Require_Response(...)` (the 8.x-compatible replacement for `return`).
- **Socket location:** defaults to `/tmp/`, **prefers the savegame folder**
  `~/.config/EgoSoft/X4/save/` (the only dir X4 Lua can `unlink`). Socket file uses a
  `.xml` extension so X4's own file-delete can clean it up. Quick test: `nc -U <file>`.
- **Maintenance:** last commits **2025-09-13/14**, wiki titled **"Quick install manual for
  X4 8.x"**, commit "Update linux pipe for X4 8.x changes". **Caveat:** activity is bursty
  (gap July 2024 → Sept 2025), **no 2026 activity** as of this writing, no tagged releases.
  Not abandoned (it tracks the current gen), but not high-cadence — budget for the chance
  we maintain our own vendored copy.
- **License:** **MIT** (both `x4-projects` fork and `x4-simpit`). → We may **depend on OR
  vendor** it freely.
- **Linux:** this IS the native-Linux solution. Requires **`lua5.1-socket`**
  (`lua5.4-socket` does NOT work — X4 is LuaJIT/Lua-5.1 ABI), available on Fedora; copy
  `socket/*.so` into `game/ui/core/lualibs/` or `.../sn_mod_support_apis/ui/c_library/
  socket/`. **No symlinks** (X4 ≥7.x rejects them) — copy files. Disable **Protected UI**.

### Tier 2 — the upstream it forks from (reference + the Windows story)

**`bvbohnen/x4-projects` — `sn_mod_support_apis` (SirNukes Mod Support APIs)** — the
canonical bundle. **Six APIs (verified):** Lua Loader (legacy since 7.5), Simple Menu,
Interact Menu, **Named Pipes**, Hotkey, Time. (Also ships a `Chat_Window_API` doc.)
- Named Pipes upstream is **Windows-only** (`winpipe.lua` wraps a Windows DLL). X4 = client;
  an external **Python** server *creates* the pipe (Py 3.6+ + `pywin32` + `pynput`, or a
  provided `.exe`). Not for native Linux — that's exactly why the bekopharm fork exists.
- **For 8.x, the original is the most-current line** — actively updated Sep–Dec 2025 for
  X4 8.0. **Version note:** SN API **v1.91/1.92 had a main-menu regression bug on 8.0;
  v1.93 fixed it** → **pin ≥ 1.93**.
- We rely on this for the **MD-side API surface** (`Named_Pipes.Read/Write`, Simple Menu for
  our config UI), which the bekopharm fork preserves on Linux.

### Tier 3 — relevant building blocks & prior art (learn from, maybe reuse)

- **`djfhe/x4_http` — an HTTP/HTTPS client *inside* X4 Lua.** Wraps **LuaSocket + LuaSec**,
  non-blocking callback interface (polls every 50 ms), JSON. Proves you can do **outbound
  HTTPS REST from X4 Lua directly**. Loads native `.dll`/`.so` + needs Protected UI off;
  WIP; ships Windows binaries (Linux needs `.so` builds of luasocket/luasec). **Relevance:**
  a fallback path to call **Twitch Helix REST straight from X4** without the bridge — but
  EventSub (WebSocket+TLS, persistent) is still far better handled in an external process.
- **`mycumycu/X4-External-App` (Nexus 818)** — read-only companion (logbook/missions/player
  info → Node.js → Vue SPA). **Current transport: HTTP/REST on TCP 8080 via `djfhe/x4_http`**
  (migrated **off** named pipes in v3.0.0). Works with X4 8.0. On Linux its README says run
  X4 under **Proton** — but that's a *mod-specific* binary-packaging limitation, **not** a
  native-Linux limitation (the research repeatedly refuted the generalization). Good
  reference for MD↔Lua↔socket plumbing and JSON framing.
- **`bekopharm/x4-simpit`** — the flagship app on the Linux fork: streams ship telemetry out
  via the Unix socket → node-red → WebSocket/MQTT. Demonstrated flow is **outbound-only**,
  but the transport is two-way. Best concrete example of the socket in action on Linux.

### Tooling (not transport, but useful)

- **X4 Customizer** (`bvbohnen`, Python) — read/transform/diff game files, pack catalogs.
- **Official "X Tools"** (Steam → Tools) — asset/XML/packing; **not** a C++ code SDK.
- **ioTools** (Nexus 1420) — unpack + a docs/XML browser WebApp.
- **XRCatTool** — cat/dat pack/unpack.
- LuaLS addon / XSD schemas for MD/AI XML + X4 Lua exist for editor support (see refs).

### The C++ / native route (settled — see doc 05)

`carrascodev/x4-mods` (HenMod.Commons + NakamaX4Client) proves C++-via-LuaJIT-FFI works and
can even do multiplayer — but it's **Windows-only** (VS2022, PowerShell, `.dll`). We don't
need it: LuaSocket (through the bekopharm fork) already gives us the native seam, MIT, on
Linux. **Decision: no custom C++ lib.**

## Decisive answers to the key questions

| Question | Verified answer |
|----------|-----------------|
| **SOTA two-way native-Linux bridge in 2026?** | **bekopharm `linux-compat` fork**: LuaSocket Unix-domain-socket server inside X4, exposing the Named Pipes MD API. Ranked above (a) writing our own C shim, (b) upstream Windows pipes under Wine, (c) in-Lua HTTP via djfhe. |
| **Any existing X4 Twitch/chat-stream integration to build on?** | **No.** None found. We're building something new. (`Chat_Window_API` is an in-game chat window, unrelated.) Closest prior art for plumbing: X4-External-App + x4-simpit. |
| **LuaSocket fork solid enough to depend on, or build our own .so?** | **Depend on (or vendor) the fork.** It's MIT, maintained to 8.x, and `lua5.1-socket` is packaged on Fedora. Writing our own native lib is unjustified. Keep a vendored copy because cadence is bursty. |
| **Licensing to depend on / vendor `sn_mod_support_apis` + forks?** | bekopharm fork & x4-simpit are **MIT** → depend or vendor freely (keep attribution). Confirm the exact upstream `bvbohnen` license before vendoring upstream specifically. |

## Revised architecture (supersedes the TCP/"X4 listens, we roll our own Lua" sketch)

```
Twitch ⇄ Python bridge (twitchAPI: EventSub WS + Helix + OAuth)
        ⇄ Unix domain socket  ~/.config/EgoSoft/X4/save/<name>.xml   ← X4 hosts it (linpipe)
        ⇄ bekopharm linux-compat LuaSocket layer (in X4)
        ⇄ Named Pipes MD API  (Named_Pipes.Read / Named_Pipes.Write cues)
        ⇄ our MD scripts (twitch_integration)  →  game effects
```

Key change: **X4 is the socket server** (the fork already implements this on Linux), and
**our MD code uses the documented Named Pipes API** rather than custom Lua — far less code
to own. Our Python bridge connects in as a client.

## Net effect on the build plan
- D1 native-Linux ✅, D3 Python ✅ (unchanged).
- **D2 → Unix domain socket** (savegame folder), not TCP — that's the fork's proven path.
- **D4 → depend on, and vendor a pinned copy of, the bekopharm `linux-compat` fork** (MIT).
  No custom C shim, no custom Lua transport.
- New prerequisite: `lua5.1-socket` on Fedora + copy `.so`s into the game lualibs; SN API
  **≥ 1.93**; Protected UI **off**.
- Milestone-1 "hello socket" spike now means: stand up the fork, confirm a `nc -U` round-trip
  to the savegame socket, then a `Named_Pipes.Write/Read` round-trip from an MD test cue.
