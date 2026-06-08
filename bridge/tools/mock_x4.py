"""Mock X4: stands in for the game so we can test the bridge end-to-end.

X4 (via the bekopharm LuaSocket fork) HOSTS a Unix-domain socket; this script
does the same. It accepts the bridge as a client, prints every message it
receives (Twitch events), and lets you type lines back (X4 -> bridge actions).

Usage:
    python tools/mock_x4.py --socket /tmp/x4_twitch.sock
Then in another terminal:
    python -m twitch_bridge --socket /tmp/x4_twitch.sock

Type at the mock_x4 prompt:
    say <message...>     -> sends {"t":"say","msg":"..."} to the bridge
    {...}                -> raw protocol JSON
    quit                 -> stop
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys

# Allow running from the bridge/ dir without installing the package.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from twitch_bridge import protocol  # noqa: E402


async def _handle_client(reader: asyncio.StreamReader, writer: asyncio.StreamWriter,
                         state: dict) -> None:
    peer = "bridge"
    print(f"\n[mock_x4] {peer} connected", flush=True)
    state["writer"] = writer
    # Greet like X4 would once it's ready.
    writer.write(protocol.encode(protocol.ready()))
    await writer.drain()
    try:
        while True:
            line = await reader.readline()
            if not line:
                break
            try:
                msg = protocol.decode(line)
                print(f"[mock_x4 <- bridge] {json.dumps(msg)}", flush=True)
            except ValueError:
                print(f"[mock_x4 <- bridge] (raw) {line!r}", flush=True)
    finally:
        print(f"[mock_x4] {peer} disconnected", flush=True)
        state["writer"] = None
        writer.close()


async def _console(state: dict) -> None:
    loop = asyncio.get_running_loop()
    print("[mock_x4] type 'say <msg>' or raw JSON to send to the bridge; 'quit' to exit",
          flush=True)
    while True:
        line = await loop.run_in_executor(None, sys.stdin.readline)
        if line == "" or line.strip().lower() == "quit":
            break
        text = line.strip()
        if not text:
            continue
        writer = state.get("writer")
        if writer is None:
            print("[mock_x4] no bridge connected yet", flush=True)
            continue
        if text.startswith("{"):
            try:
                msg = json.loads(text)
            except json.JSONDecodeError:
                print("[mock_x4] bad JSON", flush=True)
                continue
        elif text.startswith("say "):
            msg = {"t": protocol.SAY, "msg": text[4:]}
        else:
            print("[mock_x4] use 'say <msg>' or raw JSON", flush=True)
            continue
        writer.write(protocol.encode(msg))
        await writer.drain()


async def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--socket", default="/tmp/x4_twitch.sock")
    args = p.parse_args()

    if os.path.exists(args.socket):
        os.unlink(args.socket)

    state: dict = {"writer": None}
    server = await asyncio.start_unix_server(
        lambda r, w: _handle_client(r, w, state), path=args.socket)
    print(f"[mock_x4] listening on {args.socket}", flush=True)

    async with server:
        await asyncio.gather(server.serve_forever(), _console(state))


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
