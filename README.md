# X4 Twitch Integration Mod

A from-scratch **Twitch integration mod for X4: Foundations** — a two-way bridge so Twitch
chat, channel points, subs, bits and raids drive in-game events, and in-game events post
back to chat. Inspired by RimWorld's *TwitchToolkit*, adapted to X4.

## Status
**Milestone 1 proven live on X4 8.00 (native Linux):** the hardest, least-documented part —
a bidirectional socket between native-Linux X4 and an external process — works end to end
(see [`docs/07`](docs/07-live-bringup-checklist.md) Track C). The viewer-facing layer is built
and tested headless:

- **`bridge/`** — the Python companion: Twitch↔X4 bridge + a coin **wallet**, **karma**
  governor, `!buy` **store**, a localhost **dashboard** (status + searchable catalog), and a
  one-click **Twitch OAuth** setup panel. ~10 test modules + a Playwright UI check, all green.
- **`extensions/twitch_integration/`** — the X4 mod (MD + Lua), loading and round-tripping the
  socket in-game.

**Remaining (needs the live game / your Twitch app):** the real OAuth flow, MD cues + actual
X4 effects per catalog event, and the in-game Enable-Twitch panel. Day-by-day log:
[`docs/DEVLOG.md`](docs/DEVLOG.md).

## How it works (the short version)
X4 mods can't open sockets or reach the network. So Twitch lives in a small **companion app**
that bridges into the game:

```
Twitch  ⇄  Companion (Python): OAuth + EventSub + Helix + economy + dashboard
                                    │  localhost Unix socket
                                    ▼
                 LuaSocket inside X4  ⇄  MD scripts (game logic)
```

On **Linux** (this project's target) the socket is a **Unix domain socket opened inside X4**
via a side-loaded **LuaSocket** library — the MIT-licensed, X4-8.x-maintained **bekopharm
`linux-compat` fork** of the Mod Support APIs. Our MD scripts use its documented **Named Pipes
API**; the companion connects in as a client. (In-game process spawning is blocked by X4's FFI
sandbox, so the companion is started separately — see [`docs/09`](docs/09-onboarding-oauth-and-companion-ux.md).)

## Quick start (the companion)
```bash
cd bridge
pip install -r requirements.txt
./run-companion.sh            # opens the dashboard at http://127.0.0.1:17564/
./install-launcher.sh         # (optional) adds an app-menu launcher button
```
The dashboard's **① Connect to Twitch** panel walks you through creating a Twitch app and
authorizing (one time). Your credentials are stored locally (gitignored, chmod 600) — never in
the repo. See [`SECURITY.md`](SECURITY.md).

## Reference bank — read in order
| Doc | What's in it |
|-----|--------------|
| [`docs/00`](docs/00-overview-and-architecture.md) | Goal, the sandbox constraint, full architecture, wire protocol. |
| [`docs/01`](docs/01-x4-modding-basics.md) | Extension layout, content.xml, MD cues, Lua UI loading. |
| [`docs/02`](docs/02-network-bridge-linux.md) | Named Pipes vs LuaSocket; the Linux socket mechanism. |
| [`docs/03`](docs/03-twitch-api.md) | EventSub, OAuth scopes, sending chat. |
| [`docs/04`](docs/04-build-plan.md) | Staged milestones + resolved decisions. |
| [`docs/05`](docs/05-native-cpp-and-ffi-option.md) | The C++/native (LuaJIT FFI) route — and why we don't use it. |
| [`docs/06`](docs/06-ecosystem-survey.md) | **Verified survey of the modding ecosystem + the resolved architecture.** |
| [`docs/07`](docs/07-live-bringup-checklist.md) | Install + first-run steps; the live bring-up log + bug ledger. |
| [`docs/08`](docs/08-viewer-economy-and-events.md) | **Viewer economy & events** — wallet, karma, the store, 4 severity tiers, the item-list. |
| [`docs/09`](docs/09-onboarding-oauth-and-companion-ux.md) | **Onboarding/OAuth/companion UX** — why Twitch can't live fully in-game. |
| [`docs/DEVLOG.md`](docs/DEVLOG.md) | Chronological engineering log. |
| [`docs/references.md`](docs/references.md) | Every source URL. |

## Next step
Live OAuth test from the companion, then wire the first real X4 effect (a catalog event →
an actual in-game spawn) in a loaded game.
