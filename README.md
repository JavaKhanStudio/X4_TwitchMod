# X4 Twitch Integration Mod

A from-scratch **Twitch integration mod for X4: Foundations** — a two-way bridge so Twitch
chat, channel points, subs, bits and raids drive in-game events, and in-game events post
back to chat.

## Status
🔬 **Research / reference-bank phase.** No code yet. The architecture and the (non-obvious)
way to get networking out of X4's sandbox are documented in [`docs/`](docs/).

## How it works (the short version)
X4 mods can't open sockets directly. We bridge out of the game:

```
Twitch  ⇄  Bridge process (Python/Node)  ⇄  socket  ⇄  LuaSocket in X4  ⇄  MD scripts
         EventSub + Helix + OAuth          localhost      (Lua UI layer)     (game logic)
```

On **Linux** (this project's target) the socket is a **Unix domain socket opened inside X4**
via a side-loaded **LuaSocket** library — the MIT-licensed, X4-8.x-maintained **bekopharm
`linux-compat` fork** of the Mod Support APIs — not Windows named pipes. Our MD scripts use
its documented **Named Pipes API**; the Python bridge connects in as a client.

## Reference bank — read in order
| Doc | What's in it |
|-----|--------------|
| [`docs/00-overview-and-architecture.md`](docs/00-overview-and-architecture.md) | Goal, the sandbox constraint, full architecture, wire protocol. |
| [`docs/01-x4-modding-basics.md`](docs/01-x4-modding-basics.md) | Extension layout, content.xml, MD cues, Lua UI loading. |
| [`docs/02-network-bridge-linux.md`](docs/02-network-bridge-linux.md) | Named Pipes vs LuaSocket; the Linux socket mechanism. |
| [`docs/03-twitch-api.md`](docs/03-twitch-api.md) | EventSub, OAuth scopes, sending chat (2026-current). |
| [`docs/04-build-plan.md`](docs/04-build-plan.md) | Staged milestones + open decisions. |
| [`docs/05-native-cpp-and-ffi-option.md`](docs/05-native-cpp-and-ffi-option.md) | The C++/native (LuaJIT FFI) route — and why we don't need it. |
| [`docs/06-ecosystem-survey.md`](docs/06-ecosystem-survey.md) | **Verified survey of the modding ecosystem + the resolved architecture. Start here for the "what exists" picture.** |
| [`docs/references.md`](docs/references.md) | Every source URL. |

## Next step
Milestone 0–1 in the build plan: confirm native-Linux vs Proton, then a **"hello socket"
spike** proving bidirectional X4 ⇄ external-process messaging before any Twitch code.
