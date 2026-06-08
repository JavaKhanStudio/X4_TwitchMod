# X4 Twitch Integration Mod — Overview & Architecture

> Reference bank for building a Twitch-integration mod for **X4: Foundations** (Egosoft).
> Audience: the developer (Claude) building this mod from scratch. Everything here is
> distilled from research — items marked **[VERIFY]** still need hands-on confirmation.

## 1. The goal

Add a **Twitch integration** to X4: Foundations. Concretely, that means a two-way bridge:

- **Twitch → Game**: chat messages, commands, channel-point redemptions, subs, bits,
  raids, follows → trigger in-game events (spawn ships, launch missions, alter the
  economy, buff/nerf the player, vote on decisions, etc.).
- **Game → Twitch**: in-game events (player died, station built, war declared) → post
  messages back to chat via the Twitch API.

## 2. The single hardest constraint (read this first)

**X4 mods cannot make network calls.** The moddable surface of X4 is:

- **Mission Director (MD)** scripts — XML, event/cue driven game logic.
- **AI scripts** — XML, ship/NPC behaviour.
- **UI** — **Lua** (a sandboxed **LuaJIT** / Lua 5.1-ABI env with **FFI**), the *only*
  place arbitrary code runs. FFI = can `ffi.load` native `.so`/`.dll`. See doc 05.
- **Libraries / assets** — XML game data (wares, gamestarts, ships…).

None of these can open a socket *by default*. The Lua environment is stripped of `io`,
`os`, and networking. So a Twitch integration **must** bridge out of the game to a normal
process that can talk to Twitch. There are two established ways to do that:

### Path A — Named Pipes (Windows-only)
The community standard: **SirNukes / bvbohnen "Mod Support APIs"** ships a Named Pipes
API. A C DLL + Lua plugin let X4 act as a *client* on a Windows named pipe; an external
Python (or .exe) **pipe server** hosts the pipe and does the real networking.
→ **Windows only.** Uses `pywin32`. Does not work on native Linux X4. See `02-network-bridge-linux.md`.

### Path B — LuaSocket inside X4 (Linux-friendly) ✅ our path
**bekopharm** patched the Mod Support APIs to **side-load `LuaSocket`** (the standard Lua
networking library, as a `.so`) into X4's Lua environment and **open a real TCP/UDP/Unix
socket directly from inside the game**. No DLL, no pywin32. X4 itself becomes a socket
endpoint that an external app connects to. This is the route for a **native-Linux** build.
See `02-network-bridge-linux.md` for the concrete mechanism.

> **Decision (provisional):** target **native-Linux X4 + LuaSocket (Path B)**, because the
> dev machine is Fedora Linux. If the user actually runs X4 through Proton/Wine, Path A
> (Windows named pipes under Wine) may be simpler — **confirm which before committing.**

## 3. High-level architecture

```
 ┌────────────────────────────┐         socket          ┌────────────────────────────┐
 │  X4: Foundations (game)     │  (TCP/Unix, localhost)   │  Twitch Bridge (our app)    │
 │                             │ <══════════════════════> │  standalone process         │
 │  ┌──────────────────────┐   │   line-delimited JSON    │  (Python or Node.js)        │
 │  │ MD scripts (XML)     │   │                          │                             │
 │  │  - react to events   │   │                          │  ┌───────────────────────┐  │
 │  │  - spawn ships, etc. │   │                          │  │ Twitch EventSub (WS)  │  │
 │  └─────────▲────────────┘   │                          │  │  channel.chat.message │  │
 │            │ lua events     │                          │  │  channel points, subs │  │
 │  ┌─────────┴────────────┐   │                          │  │  raids, bits…         │  │
 │  │ Lua UI layer          │  │                          │  └───────────────────────┘  │
 │  │  - LuaSocket I/O      │   │                          │  ┌───────────────────────┐  │
 │  │  - read/write socket  │  │                          │  │ Twitch Helix REST     │  │
 │  └──────────────────────┘   │                          │  │  send chat, etc.      │  │
 └────────────────────────────┘                          │  └───────────────────────┘  │
                                                          │  + OAuth token mgmt          │
                                                          └────────────────────────────┘
```

### Why an external bridge process at all?
Even with LuaSocket inside X4, you do **not** want to implement the Twitch WebSocket
protocol, OAuth refresh, TLS, and JSON-heavy EventSub handling inside X4's Lua sandbox
(no TLS, fragile, hard to debug, blocks the game thread). The bridge process owns all
Twitch complexity and speaks a **tiny, dumb line protocol** to X4. X4 stays simple.

## 4. The three components we will build

| # | Component | Tech | Responsibility |
|---|-----------|------|----------------|
| 1 | **Twitch Bridge** | Python or Node | Twitch EventSub + Helix + OAuth; expose a localhost socket; translate Twitch events ⇄ line protocol. |
| 2 | **X4 extension (`extensions/twitch_integration`)** | XML (MD) + Lua | Connect to the bridge socket; parse events; drive game logic (spawns, missions, modifiers); send game events back. |
| 3 | **Mod Support APIs dependency** | existing mod | LuaSocket-enabled fork (bekopharm) OR a trimmed self-contained socket loader. Decide: depend vs. vendor. See `04-build-plan.md`. |

## 5. The wire protocol (our design — keep it dumb)

Newline-delimited JSON, one event per line, both directions. Example:

```
# Bridge → X4
{"t":"chat","user":"viewer42","msg":"!spawn fighter","badges":["sub"]}
{"t":"redeem","user":"viewer42","reward":"Spawn Pirate","amount":1}
{"t":"sub","user":"viewer42","tier":"1000","months":3}
{"t":"raid","user":"bigstreamer","viewers":250}

# X4 → Bridge
{"t":"say","msg":"viewer42 spawned a fighter for the player!"}
{"t":"ready"}            # handshake on connect
```

Keep parsing trivial on the X4 side — JSON parsing in Lua is doable but a `|`-delimited
format is even cheaper if we hit performance/robustness issues. Revisit in build.

## 6. Reading order for the rest of the bank

1. `01-x4-modding-basics.md` — extension layout, content.xml, MD cues, Lua UI loading.
2. `02-network-bridge-linux.md` — how the socket bridge works (Path A vs B, Linux details).
3. `03-twitch-api.md` — EventSub, OAuth scopes, sending chat (2026-current).
4. `04-build-plan.md` — concrete milestones & open decisions.
5. `05-native-cpp-and-ffi-option.md` — the C++/native-code route via LuaJIT FFI; why we
   don't need to write a C++ lib (LuaSocket already gives us the native seam).
6. `references.md` — every source URL, the link bank.
