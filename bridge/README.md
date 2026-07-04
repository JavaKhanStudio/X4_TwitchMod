# Twitch Bridge

The external process that owns all Twitch complexity (EventSub WebSocket, Helix,
OAuth) and speaks a tiny newline-JSON line protocol to X4 over a **Unix domain
socket**. X4 hosts the socket (via the bekopharm LuaSocket fork); this bridge
connects in as a client. See `../docs/` for the full architecture.

## Status
Skeleton. Runs today on the **Python standard library only**. The real Twitch
source is stubbed (`twitch_bridge/sources/twitch.py`); the `stdin` fake source
lets you drive the whole pipeline by hand.

## Layout
```
twitch_bridge/
  protocol.py     wire format (newline-JSON) + message constructors
  config.py       env-driven config (socket path, source, Twitch creds)
  x4link/         transport to X4 (one interface, two impls, factory-selected)
    base.py       shared: framing-safe send, read loop, connection state
    unixsocket.py Linux: connect as CLIENT to the socket X4 hosts
    winpipe.py    Windows: HOST \\.\pipe\twitch; X4 connects as CLIENT
  app.py          wires source <-> x4link
  __main__.py     `python -m twitch_bridge`
  sources/
    base.py       Source interface
    stdin.py      fake Twitch via console/pipe (default)
    twitch.py     real EventSub source (STUB, Milestone 3)
tools/
  mock_x4.py      stands in for the game; hosts the socket for testing
```

## Try it without X4 (two terminals)
```bash
# terminal 1 — pretend to be X4 (host the socket)
cd bridge && python tools/mock_x4.py --socket /tmp/x4_twitch.sock

# terminal 2 — run the bridge against it
cd bridge && python -m twitch_bridge --socket /tmp/x4_twitch.sock
# then type:  chat alice !spawn fighter
#             raid bigstreamer 250
# watch them arrive as JSON in terminal 1.
# In terminal 1 type:  say Welcome to the stream!
# watch the bridge log it as an X4 action in terminal 2.
```

A non-interactive smoke test of the same loop lives at `tools/smoke_test.sh`.

## Real Twitch
`sources/twitch.py` is implemented (EventSub + Helix via twitchAPI). To go live:
```bash
pip install -r requirements.txt
export TWITCH_CLIENT_ID=... TWITCH_CLIENT_SECRET=... TWITCH_CHANNEL=yourchannel
python -m twitch_bridge --source twitch --socket ~/.config/EgoSoft/X4/save/x4_twitch.xml
```
First run opens a browser for OAuth; tokens are stored under
`~/.config/x4-twitch-bridge/` and auto-refreshed thereafter. Create the app at
https://dev.twitch.tv/console (OAuth redirect `http://localhost:17563`).

## Commands
The command engine (`commands.py`) turns Twitch events into vetted `cmd` messages,
applying permissions + cooldowns. Edit **`catalog.py`** to change what viewers can do
(chat prefixes like `!spawn`, channel-point rewards, raid/sub/cheer reactions). Each
`action` needs a matching cue in the X4 mod's MD script.

## Tests
```bash
python tools/test_commands.py   # command engine: perms, cooldowns, args (stdlib)
bash tools/smoke_test.sh        # end-to-end plumbing through the engine (stdlib)
python tools/test_twitch_api.py # twitchAPI names/signatures (needs twitchAPI)
python tools/test_lua_decode.py # X4 Lua JSON decode + cmd dispatch (needs lupa)
```
