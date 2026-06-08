# 02 — The Network Bridge (getting data in/out of X4)

> **⚠️ Updated by `docs/06-ecosystem-survey.md` (verified research).** Key deltas: X4 is at
> **8.x** (not 7.x); the **Community Edition** fork is **archived/dead** — use the original
> for 8.x; **Fedora packages `lua5.1-socket`** (no need to build it); and the bekopharm
> `linux-compat` fork is the **MIT-licensed, 8.x-maintained** thing we depend on. Read doc 06
> alongside this.

This is the crux of the whole project. X4's Lua sandbox has no networking by default, so
we must establish a socket between the game and an external process. Two routes:

## Path A — SirNukes/bvbohnen Named Pipes API (Windows-only)

**Repo:** `bvbohnen/x4-projects` → `extensions/sn_mod_support_apis`.

The "Mod Support APIs" bundle several sub-APIs:

| API | Purpose |
|-----|---------|
| **Lua Loader API** | Load custom Lua, support `require`, defer init until after game load. |
| **Simple Menu API** | Build options/standalone menus from MD scripts (great for our config UI). |
| **Interact Menu API** | Add right-click context-menu actions. |
| **Named Pipes API** | **Two-way IPC** over a Windows named pipe. X4 = client, external = server. |
| **Hotkey API** | Capture keypresses (via the external server). |
| **Time API** | Real (wall-clock) time, alarms, timers (system time via the pipe server). |

### Named Pipes API — protocol
Components: a **C DLL + Lua plugin** (low-level pipe access), an **MD wrapper**
(`Named_Pipes.xml`), and an optional **external Python pipe server**. X4 connects as a
**client**; the external app **creates and hosts** the pipe.

MD-level operations (signal these cues, get a callback):

- **Write** — `md.Named_Pipes.Write` with `$pipe`, `$msg`, `$cue` (callback), `$time`
  (timeout). Callback param = `'SUCCESS'` / `'ERROR'`.
- **Read** — returns the server's response string, or `'ERROR'`/`'TIMEOUT'`/`'CANCELLED'`.
  Supports a **continuous** mode (keep delivering messages) — ideal for a chat stream.
- **Check** — is the pipe connected? `'SUCCESS'`/`'ERROR'`.
- **Close** — drop the pipe, kill pending accesses.
- **Cancel_Reads** — stop pending/continuous reads.
- **Write_Special** — engine-side specials (e.g. `"package.path"`).

Round-trip MD example (verified shape from the API docs):

```xml
<signal_cue_instantly cue="md.Named_Pipes.Write"
  param="table[$pipe='mypipe', $msg='hello', $cue=Write_Callback]"/>

<cue name="Write_Callback" instantiate="true">
  <conditions><event_cue_signalled/></conditions>
  <actions><set_value name="$result" exact="event.param"/></actions>
</cue>
```

- Pipe is referenced **by name only**, no OS path prefix (the Lua/DLL adds the
  `\\.\pipe\` prefix on Windows).
- Reads return to MD with **≥1 frame of delay** (async via Lua callback).
- The **exact message semantics are defined by the external server**, not the API — i.e.
  *we* design the protocol (see `00-overview` §5).

**Platform reality:** "Currently, pipes are only set for Windows, not Linux." The pipe
server is Python + `pywin32` + `pynput` (or a PyInstaller `.exe`). On Linux this path
only works under Wine/Proton with extra pain.

## Path B — LuaSocket inside X4 (native Linux) ✅ recommended for us

**Repo:** `bekopharm/x4-projects` (the `linux-compat` branch) + `bekopharm/x4-simpit`,
documented at `bekopharm/x4-projects` wiki "Quick-manual".

### The idea
Instead of a DLL + Windows pipe, **side-load `LuaSocket`** (the ubiquitous Lua sockets
library, shipped as native `.so` modules) into X4's Lua VM and **open a real socket from
inside the game**. X4 then *is* a socket endpoint (TCP, UDP, **or Unix domain socket**).
An external app connects to it. No Windows APIs involved.

### Setup steps (native-Linux X4) — from bekopharm's Quick-manual
1. **Use the LuaSocket-enabled Mod Support APIs**: take `sn_mod_support_apis` from the
   `linux-compat` branch and put it in `<X4>/extensions/`.
2. **Install the system LuaSocket for Lua 5.1**: package `lua5.1-socket`
   (Debian/Ubuntu naming). **`lua5.4-socket` is INCOMPATIBLE** — X4's Lua is **5.1**.
   - **On Fedora (our box):** ✅ **`lua5.1-socket` IS packaged on Fedora**
     (`packages.fedoraproject.org/pkgs/lua-socket/lua5.1-socket`). Install it, then copy
     `socket/core.so` + `socket/unix.so` into the game lua path. No self-build needed.
3. **Copy the socket `.so` libraries** into a path X4's Lua searches:
   - `<X4>/game/ui/core/lualibs/` **or**
   - `<X4>/extensions/sn_mod_support_apis/ui/c_library/socket/`
   - The loader searches: `"extensions/sn_mod_support_apis/ui/c_library/?.so;?.so;ui/core/lualibs/?.so"`.
   - **Do NOT use symlinks** — X4 ≥ 7.x rejects symlinked files.
4. **Disable Protective/Protected UI Mode** (Settings → Extensions) — required for
   `require` and native lib loading.
5. Loader Lua files involved: **`linpipe.lua` / `linux_pipe.lua`** open the socket.

### How the socket is exposed (Linux)
bekopharm uses a **Unix domain socket placed in the savegame folder**, e.g.:
```
~/.config/EgoSoft/X4/save/x4_external_game.xml
```
(Named `.xml` so X4's own "delete file" capability can clean it up — a clever hack to get
around the sandbox's limited filesystem rights.) Test the live socket from a shell with:
```
nc -U ~/.config/EgoSoft/X4/save/x4_external_game.xml
```
TCP is also possible (`LuaSocket allows UDP or TCP server depending on how it is started`)
— for our bridge, **localhost TCP** may be simpler and protocol-symmetric with a Windows
fallback. **Decide TCP-localhost vs Unix-socket in build** (`04-build-plan.md`).

### Data flow on Linux (Path B)
```
Twitch ⇄ Bridge process ⇄ (TCP localhost OR Unix socket) ⇄ LuaSocket in X4 ⇄ Lua ⇄ MD
```
The bridge is the socket **server** or **client** — bekopharm's simpit has X4 host the
socket and external tools subscribe (he fans telemetry into node-red → WebSocket/MQTT).
For us, simplest is: **X4 hosts a listening socket; the Bridge connects in.** Then the
Bridge pushes Twitch events as lines and X4 reads them in a continuous loop.

## Decision summary

| Question | Provisional answer | Confirm |
|----------|-------------------|---------|
| Windows pipes or LuaSocket? | **LuaSocket (Path B)** — dev box is Linux. | Does user run X4 native-Linux or Proton? |
| Transport | **localhost TCP** (portable) — fall back to Unix socket if needed. | bench both |
| Who hosts the socket | **X4 listens, Bridge connects** | revisit if reconnection is fiddly |
| Depend on bekopharm fork, or vendor our own LuaSocket loader | TBD — depending is faster, vendoring is self-contained | `04-build-plan.md` |

## Risks / unknowns to validate early
- **Fedora LuaSocket-for-Lua-5.1 `.so`** must be built/obtained correctly (ABI must match
  X4's embedded Lua 5.1). This is the #1 setup risk — prove it with a "hello socket" spike.
- Protected UI mode off = mods can run arbitrary Lua / load native code. Fine for a
  personal mod; note it in the README for any future distribution.
- Socket reads must be **non-blocking** (`settimeout(0)`) so they never stall the game
  frame; poll each tick via a Lua timer / MD loop.
- X4 patches periodically break the Mod Support APIs — pin to a known-good combo. **Pin SN
  API ≥ 1.93** (1.91/1.92 had an 8.0 main-menu regression; 1.93 fixed it). **Do NOT use the
  "Community Edition" fork** — it's archived (2025-09-18), 7.X-only, and superseded by the
  original SirNukes/bvbohnen API for 8.x. See doc 06.
