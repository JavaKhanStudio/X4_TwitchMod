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
  x4link.py       Unix-socket client to X4, with reconnect
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

## Real Twitch (later)
Set env and switch source:
```bash
export TWITCH_CHANNEL=... TWITCH_CLIENT_ID=... TWITCH_CLIENT_SECRET=...
pip install -r requirements.txt   # uncomment twitchAPI first
python -m twitch_bridge --source twitch --socket ~/.config/EgoSoft/X4/save/x4_twitch.xml
```
Implement `sources/twitch.py` first (see docs/03-twitch-api.md).
