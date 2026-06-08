# 05 — The C++ / Native-Code Route (LuaJIT FFI)

> Added after the user asked about "a C++ set of tools for modding." This documents the
> native-code path, how it works, and whether we should use it. **Short answer: the C++
> route is real and powerful, but for *our* Twitch use-case the right amount of it is the
> small amount we already get for free via LuaSocket.** Details below.

## The key fact: X4's Lua is **LuaJIT**, which has **FFI**

X4's UI scripting VM isn't plain Lua 5.1 — it's **LuaJIT** (Lua 5.1 ABI + JIT). LuaJIT
ships a **Foreign Function Interface (FFI)**:

```lua
local ffi = require("ffi")
ffi.cdef[[ int my_func(const char* s); ]]   -- declare C signatures (copy from headers)
local lib = ffi.load("mylib")                -- loads libmylib.so (Linux) / mylib.dll (Win)
lib.my_func("hello")                          -- call native code directly from the mod
```

This is the seam that makes "C++ modding" of X4 possible: you compile a **native shared
library** (`.so` / `.dll`) and call into it from the mod's Lua. **This is exactly how
LuaSocket works** (LuaSocket is a C library), and how the Mod Support APIs' Windows
named-pipe "DLL" works. So we are *already* using the native-code route — just via an
existing, battle-tested library instead of one we write.

## What "C++ tools" actually refers to (the landscape)

There are three different things people mean by "C++ X4 tools":

1. **Official "X Tools"** (Steam → Library → Tools). Egosoft's official modding toolset:
   asset import/export, cat/dat packing, shader/material tooling. It is **asset/XML
   tooling, not a C++ code SDK** — it doesn't help you write game logic in C++.

2. **`ioTools - X4 Modding Kit`** (Nexus 1420). Scripts to unpack game files + a WebApp to
   browse the docs/XML. Convenience tooling, not native code.

3. **Community C++ frameworks via LuaJIT FFI** — the real "code in C++" route:
   - **`carrascodev/x4-mods`** — `HenMod.Commons` (base classes `X4ScriptBase`,
     `X4ScriptSingleton`, Lua-integration helpers) + **`NakamaX4Client`**, which does
     **real-time multiplayer** by talking to a **Nakama** game server. Built with
     **CMake + vcpkg**, deps `nlohmann-json` + `msgpack-cxx`. Codebase is ~29% C++ / 26% C
     / 16% Lua. **This proves a C++ X4 mod can do real networking in-process.**
   - The Mod Support APIs' winpipe DLL is the same pattern, smaller.

So the friend's "C++ set of tools" is almost certainly either the official **X Tools** or
the **LuaJIT-FFI + native-library** pattern exemplified by `HenMod.Commons`.

## How a native lib integrates (the pattern)

```
 X4 mod (Lua, LuaJIT)  --ffi.load-->  libtwitch_native.so  --(sockets/TLS/threads)-->  Twitch
        │  ffi.cdef declares the C API                 │
        └── calls C functions; gets data back          └── C/C++ does the heavy lifting
```

- You expose a flat **C ABI** (`extern "C"`) from the C++ lib (FFI can't read C++ name
  mangling/classes directly).
- The lib can spawn its **own threads** so network I/O doesn't block X4's frame; the mod
  polls a `poll()`-style C function each tick for queued events.
- Cross-platform = build the `.so` for Linux (we have `gcc`) and a `.dll` for Windows.

## Does this change OUR architecture? Trade-off analysis

| Approach | What we'd build | Pros | Cons |
|----------|-----------------|------|------|
| **A. Python bridge + LuaSocket** (current plan) | Python process (Twitch) + thin Lua socket client (LuaSocket = existing native lib) | Twitch's hard parts (OAuth refresh, EventSub WS, TLS, JSON, reconnect) in Python = fast to write & iterate; no C++ to compile; hot-reload logic; LuaSocket is proven on Linux (bekopharm) | One extra process to launch alongside the game |
| **B. Custom native C++ lib via FFI** | `libtwitch_native.so` doing sockets *(or even the whole Twitch client)*, loaded by `ffi.load` | Can collapse to **zero external processes** if the lib embeds the Twitch client; tight, fast; full control | Async **TLS WebSocket + OAuth in C++** is a LOT more work than Python; per-platform builds; a blocking/crashing call can hitch or crash the **game process**; slow iteration; harder to debug |
| **C. Hybrid (recommended)** | Keep Python bridge for Twitch; native code only for transport — which LuaSocket already provides | Best of both: heavy/changing logic in Python, native seam handled by a proven lib we don't maintain | Still one external process |

### Recommendation: stay on **A/C** (Python bridge + LuaSocket), with B as a known fallback
- Our need is a **Twitch chat/event firehose**, not in-process game-state sync. The hard
  work is on the *Twitch protocol* side, which is dramatically easier in Python than in a
  hand-written C++ TLS/WebSocket client.
- We **already use native code** (LuaSocket via FFI/require) for the transport, so we get
  the C++-route benefit (real sockets in-game) **without writing or maintaining a C++ lib.**
- The `carrascodev` framework writes its own C++ because **multiplayer state sync** needs
  deep, fast, in-process game bindings (msgpack, singletons). **We don't** — a Twitch
  integration is loosely coupled and event-driven.
- **When B becomes worth it:** if we ever want *zero* external process, or if
  LuaSocket-for-Lua-5.1 on Fedora proves too painful to build, we can write a **tiny C
  shim `.so`** (just `connect/send/recv/poll`) and `ffi.load` it — a small, contained
  amount of C, far less than a full C++ framework. Keep this in the back pocket (D4).

## Action items from this
- [x] Documented the native/FFI route and the C++ frameworks.
- [ ] Add `carrascodev/x4-mods` + LuaJIT FFI docs to `references.md`.
- [ ] D4 in the build plan now has **three** options: depend-on-fork / vendor-LuaSocket /
      write-our-own-C-shim. Default stays LuaSocket; C-shim is the fallback.
- [ ] Note for later: most C++ X4 tooling is Windows-first (PowerShell/vcpkg/.dll). On our
      Linux target we lean on LuaJIT FFI's cross-platform `.so` loading.
