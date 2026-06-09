# 09 — Onboarding, OAuth & the Companion App (end-user experience)

> How a *streamer* actually sets this up and uses it. Docs 00–06 are the plumbing, 08 is the
> gameplay economy; this doc is the **product UX**: where the Twitch login happens, what the
> user clicks, and why it can't all live inside the game like the RimWorld mod did.
>
> Written 2026-06-09, right after Milestone 1 (the socket bridge) was proven working live.

---

## 1. The constraint that shapes the whole experience (X4 vs RimWorld)

The inspiration, **TwitchToolkit**, put *everything* in-game — the bot token field, a "create
your bot" link, the OAuth, the chat connection — all inside the mod's settings window. It
could do that because **RimWorld mods are C# with full .NET**: the mod itself opened the
network connection and talked to Twitch directly. **One process.**

**X4 cannot do this.** X4 mods are a sandboxed XML (Mission Director) + Lua (UI) environment
with **no networking, no `io`, no `os`** (see doc 00 §2). That sandbox is the entire reason
this project exists in the shape it does. Therefore the Twitch side **must** run in a small
**companion app** (our "bridge") outside the game. **Two processes, always — not a choice.**

| | RimWorld / TwitchToolkit | X4 / this project |
|---|---|---|
| Mod language | C# (full .NET) | sandboxed XML + Lua (no net) |
| Twitch connection | inside the game | **external companion app (required)** |
| OAuth / tokens | in the mod's settings | in the companion app |
| Processes | 1 | 2 (game + companion) |

The goal of this doc: given that constraint, make the experience *feel* as close to
TwitchToolkit's one-stop setup as possible.

### 1b. The constraint is NARROWER than "no UI in game" — it's exactly two things

Earlier framing over-stated this. The socket is **bidirectional** (proven by the Milestone 1
ping/pong), so the in-game UI *can* collect credentials and a "Connect" click and **send them to
the companion**. Precisely what the sandbox forbids is only:

| Capability | In-game? | Note |
|---|---|---|
| Config screens, text-input fields, buttons | ✅ | Simple Menu API has editboxes + buttons |
| Send Client ID/secret/channel to the companion | ✅ | over the socket — proven |
| Show status / viewer count | ✅ | companion pushes it back over the socket |
| Twitch network calls + OAuth | ❌ | no networking in sandbox → companion does it |
| **Start the companion process** | ❌ | no `os.execute`; **and FFI `system()` is blocked** (see note) |
| Open the OAuth page in a browser | ❌ | no URL-open in sandbox → companion opens it |

> **Verified 2026-06-09 — in-game spawn is blocked.** We tested launching the companion from the
> mod via LuaJIT FFI (`ffi.C.system` / `ffi.load("c")`). **X4 restricts dangerous FFI calls even
> with Protected UI off:** `Access to FFI function 'system' is restricted!`. Engine functions are
> whitelisted, libc is not. (The C++/Nakama multiplayer mod escapes this by shipping its *own*
> native lib whose internal C isn't whitelisted — possible for us too, but it reintroduces a
> per-platform native build we deliberately avoided. See DEVLOG.)

So the **only** thing that can't be initiated from inside the game is **starting the companion
process** (and the companion, not the game, opening the OAuth browser). Everything else — entering
the Client ID in-game, clicking Connect, the game handing that to the subprocess — works.

**Bootstrapping order (the real catch):** X4 *hosts* the socket and the companion *connects in*,
so the companion must already be running for the game to reach it — and the game can't launch it.
But the companion can start **unconfigured** and idle, waiting for the game to send credentials.

**Cleanest auto-start (recommended): a Steam launch-option wrapper.** Set X4's Launch Options to
`companion-launcher.sh %command%` (same place we set the debug flag). Steam expands `%command%` to
X4's real launch command, so the wrapper starts the companion (single-instance guarded) and then
runs X4 — every launch, no per-session step, no native code. This makes "launch X4 from Steam" the
*only* action, which is as close to one-click as the sandbox allows.

### 1c. Recommended PRIMARY flow — in-game setup (closest to RimWorld)

1. Companion is started by the **Steam launch wrapper** (above) — or once/autostart — idle, no
   credentials needed yet.
2. Launch X4, load a game → socket auto-links (x4link reconnect already does this).
3. **In-game UI:** enter Client ID / Secret / channel, click **Connect**.
4. Game sends them to the companion over the socket (`{"t":"control","action":"connect",…}`).
5. Companion runs the OAuth browser flow (§3) → stores + auto-refreshes the token.
6. Companion pushes `{"t":"status",…}` back → in-game panel shows *Connected as … · N viewers*.

The companion's own setup screen (§4) becomes an *optional fallback* for users who'd rather
configure it there, or for headless/dedicated setups. The in-game panel is the main surface.

## 2. Division of responsibilities

```
   ┌───────────────────────────┐         ┌────────────────────────────────────┐
   │  X4 (in-game UI)           │  unix   │  Companion app ("the bridge")       │
   │  THE EXPERIENCE SURFACE    │ socket  │  ALL TWITCH + ECONOMY               │
   │  • Enable Twitch toggle    │ <═════> │  • OAuth login + token storage      │
   │  • connection status panel │         │  • EventSub (chat/redeem/sub/…)     │
   │  • which events are enabled│         │  • Helix (send chat back)           │
   │  • the store / tiers (d08) │         │  • wallet / karma economy (d08)     │
   └───────────────────────────┘         └────────────────────────────────────┘
        what the streamer clicks               what holds the Twitch secrets
```

- **In-game UI owns the *experience*** — toggles, status, event catalog, store. The streamer
  drives the game from here (the "Enable Twitch" button the user asked for; see doc 08 M4.3).
- **Companion owns the *plumbing*** — every Twitch secret, token, and network call lives here,
  never in the mod or a savegame (security boundary; matches D6/D7).

## 3. Where OAuth happens (and why you never saw it in the game)

**In the companion app.** The game physically cannot do OAuth (no network). The flow, which is
already implemented in `bridge/twitch_bridge/sources/twitch.py` (twitchAPI
`UserAuthenticationStorageHelper`):

1. **One-time, per streamer:** create a Twitch application at
   <https://dev.twitch.tv/console> → copy **Client ID** + **Client Secret**, set the OAuth
   redirect to `http://localhost:17563`.
2. Enter those into the companion **once**.
3. Click **Connect** → the companion opens the system browser → streamer authorizes the
   scopes → the token is captured on the `localhost:17563` redirect → stored at
   `~/.config/x4-twitch-bridge/tokens.json` and **auto-refreshed** from then on.
4. Tokens **never** touch the X4 extension or a savegame.

After step 3, the streamer never logs in again unless they revoke access.

## 4. The target onboarding experience (TwitchToolkit-like, adapted)

The `python -m twitch_bridge …` command used during development is a **dev harness, not the
product**. The shipped experience should be:

**First run — a tiny setup screen** (the companion's only real UI), modeled on TwitchToolkit's
settings window:
- A **"Create your Twitch app →"** link that opens dev.twitch.tv with copy-paste instructions
  (and the exact redirect URL to paste).
- Fields: **Client ID**, **Client Secret**, **Channel name**.
- A **[ Connect to Twitch ]** button → runs the browser OAuth flow (§3).
- A live **status line**: `Connected as <user> · N viewers · X4: linked / waiting`.

**Steady state — zero friction:**
- The companion runs in the background and **auto-connects to X4 whenever a game loads** — the
  bridge already has socket reconnect/poll logic (`x4link.py`), so it just waits for
  `…/save/twitch.xml` to appear and links up. No re-typing, no console.
- In X4, the **Enable Twitch** toggle + status panel reflect the live connection (fed over the
  socket) and let the streamer go live / pause without alt-tabbing.

## 5. How the companion runs without a console (product, not dev)

The end user must **never** type a terminal command. Options (decide during packaging,
Milestone 6):
- **(a) One-click launcher / packaged binary** — PyInstaller one-file with a minimal tray or
  window. Double-click to start; it sits in the background.
- **(b) Optional autostart on login** — opt-in checkbox in the setup screen.
- **(c) Auto-link to X4** — already supported: the companion polls for the socket and connects
  when a game loads, reconnects if X4 restarts.

**Recommended companion UI:** a **small local web page served by the bridge on localhost**
(e.g. `http://localhost:17564`). Rationale: cross-platform with zero GUI toolkit deps, opens
links trivially, and the OAuth redirect already uses a localhost HTTP listener — so the setup
page and the auth flow share the same mechanism. A native tray app is the alternative if we
want it to feel more "installed."

## 6. The status feedback loop (so the in-game panel is truthful)

New protocol messages (extends doc 00 §5 / doc 08 §7):
```jsonc
// companion -> X4 : drive the in-game status panel
{"t":"status","connected":true,"channel":"yourname","viewers":42}
// X4 -> companion : the in-game toggle controls the live connection
{"t":"control","action":"enable"}     // or "disable" / "pause"
```
This makes the **Enable Twitch** toggle real (it tells the companion to connect/pause) and lets
the in-game panel show *Connected as … · N viewers* instead of guessing.

## 7. Open product decisions (resolve during Milestones 4–6)

| # | Decision | Leaning |
|---|----------|---------|
| U1 | Companion UI tech | **local web page served by the bridge** (shares the OAuth localhost listener) vs native tray vs Tk |
| U2 | Packaging | PyInstaller one-file binary vs system-Python + launcher script |
| U3 | Autostart | opt-in only |
| U4 | First-run app creation | guided link + paste (can't fully automate Twitch app creation) |
| U5 | Multi-PC | default same-PC; companion *can* be remote (outbound-only) but the X4 socket is local — revisit if needed (the VPS note in memory) |

## 8. One-line summary for the README

> X4's mod sandbox can't reach the internet, so Twitch lives in a tiny **companion app** you
> run alongside the game. Set it up once (create a Twitch app, click Connect, authorize in your
> browser); after that it auto-links to X4 every time you play, and you control everything from
> the in-game **Enable Twitch** panel.
