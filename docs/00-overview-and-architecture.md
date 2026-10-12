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

> **Decision (RESOLVED):** target **native-Linux X4 + LuaSocket (Path B)** via the
> **bekopharm `linux-compat` fork** (MIT, maintained to X4 8.x). X4 hosts a **Unix domain
> socket** in the savegame folder; our Python bridge connects in; our MD code uses the
> documented **Named Pipes API**. Full rationale + verified ecosystem survey in
> `06-ecosystem-survey.md`. (X4 is at **8.x**; SN API pin **≥1.93**; Protected UI **off**.)

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

Newline-delimited JSON, one message per line, both directions. `bridge/twitch_bridge/protocol.py`
is the authority — every message has a constructor there, and nothing should build one by
hand (the tests build their fixtures with the same constructors, so a format change breaks
loudly instead of silently).

```
# Bridge → X4 : Twitch events
{"t":"chat","user":"viewer42","msg":"!spawn fighter","badges":["sub"]}
{"t":"redeem","user":"viewer42","reward":"Spawn Pirate","amount":1}
{"t":"sub","user":"viewer42","tier":"1000","months":3}
{"t":"raid","user":"bigstreamer","viewers":250}

# Bridge → X4 : a VETTED command (post permissions/cooldowns/coins)
{"t":"cmd","id":"adopt_ship","by":"viewer42","args":{...},"argv":["PSF-481","viewer42's Nemesis"],"tier":0}

# X4 → Bridge
{"t":"say","msg":"viewer42 spawned a fighter for the player!"}
{"t":"cmdfail","id":"adopt_ship","ref":"PSF-481","reason":"that ship is no longer in the fleet"}
{"t":"fleet","total":42,"sent":42,"data":"PSF-481|ship_par_m_frigate_01_a_macro|M|87|100|Cluster_14_Sector001_macro;…"}
{"t":"shipdown","idcode":"PSF-481","macro":"…","killer":"Xenon"}
{"t":"shipnew","old":"PSF-481","idcode":"NEW-014"}
{"t":"ready"}            # handshake on connect
```

### Three rules the protocol learned the hard way

**1. `argv` is the payload; `args` is for humans.** The ui lua decodes `args` into a Lua
hash table, and `pairs()` order is undefined — `{"ware","qty"}` came back as
`"50;energycells"`. `argv` is the same values as an ordered ARRAY, and arrays keep their
order through the decoder. `args` survives for logs and name-based lookups.

**2. Only TOKENS cross the pipe, never display text.** MD builds its JSON by string
concatenation, so one ship called `foo"bar` would corrupt a whole line. Ship names,
sector names and ship types are therefore never transmitted: the game sends an id code,
a macro and a sector macro, and the bridge resolves them to names from `ships.json` /
`sectors.json`. Faction display names are the one exception — they are game text, not
player-editable.

**3. X4 acknowledges FAILURE only.** There is no per-command success ack (it would double
the traffic for nothing), so the bridge holds a charge as refundable until `cmdfail`
arrives or it ages out. `cmdfail` therefore carries **`ref`** — the specific thing that
failed. Without it the bridge can only guess "the oldest outstanding charge for this
action", which is wrong for anything acknowledged only on failure: successes never leave
the pending list, so the first failure rolls back an EARLIER request that worked.

Keep parsing trivial on the X4 side: MD cannot split a string at all (its `string` type
has one property, the format operator), so anything MD has to take apart is either
delimited for the BRIDGE to parse, or split into separate event slots before it arrives.

## 6. Reading order for the rest of the bank

1. `01-x4-modding-basics.md` — extension layout, content.xml, MD cues, Lua UI loading.
2. `02-network-bridge-linux.md` — how the socket bridge works (Path A vs B, Linux details).
3. `03-twitch-api.md` — EventSub, OAuth scopes, sending chat (2026-current).
4. `04-build-plan.md` — concrete milestones & open decisions.
5. `05-native-cpp-and-ffi-option.md` — the C++/native-code route via LuaJIT FFI; why we
   don't need to write a C++ lib (LuaSocket already gives us the native seam).
6. `06-ecosystem-survey.md` — **verified, decision-oriented survey** of the whole modding
   tooling/library ecosystem; the resolved architecture and why. **Read this.**
7. `07-live-bringup-checklist.md` — the hands-on checklist for first light once X4 is installed.
8. `08-viewer-economy-and-events.md` — the **gameplay-design layer**: viewer wallet & coin
   distribution, the karma governor, the `!buy` store, the 4 severity tiers + X4 event
   catalog, and voting/democracy mode. Ported from TwitchToolkit, adapted to X4. (Docs 00–07
   are *how Twitch reaches X4*; doc 08 is *what viewers can do once it does*.)
9. `09-onboarding-oauth-and-companion-ux.md` — the **end-user experience**: where the Twitch
   OAuth login happens, the companion-app setup screen, the in-game "Enable Twitch" toggle, and
   why (unlike the RimWorld mod) the Twitch side can't live inside the game. **Read this for the
   product/UX intent.**
10. `references.md` — every source URL, the link bank.

> **Why a companion app at all (vs the RimWorld mod that inspired this)?** TwitchToolkit was C#
> with full .NET, so it did Twitch *inside* RimWorld. X4's mod sandbox (§2) has **no network**,
> so the Twitch connection + OAuth must live in a small external companion process. The in-game
> UI stays the control surface; the companion holds the secrets. Full UX in doc 09.

> **STATUS (2026-06-09): Milestone 1 — the socket bridge — is proven working live on X4 8.00
> native Linux** (bidirectional round-trip; see doc 07 Track C). The hardest unknown is retired;
> remaining work is features (economy doc 08, onboarding doc 09), not plumbing risk.
