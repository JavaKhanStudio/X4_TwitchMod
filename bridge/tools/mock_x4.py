r"""Mock X4: stands in for the game so we can test the bridge end-to-end.

The transport follows the game's, per OS:
  --socket PATH  (Linux) X4, via the bekopharm LuaSocket fork, HOSTS a Unix-domain
                 socket; this script does the same and accepts the bridge.
  --pipe NAME    (Windows) the BRIDGE hosts \\.\pipe\twitch and X4 connects in as
                 a client (SirNukes winpipe, CreateFile); this script connects.
Either way it prints every message it receives from the bridge and lets you type
lines back (X4 -> bridge actions).

Usage:
    python tools/mock_x4.py --socket /tmp/x4_twitch.sock
    py tools/mock_x4.py --pipe \\.\pipe\twitch      # the default on Windows
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

from pipe_client import open_pipe
from twitch_bridge import protocol


async def _read_bridge(reader: asyncio.StreamReader) -> None:
    while True:
        line = await reader.readline()
        if not line:
            break
        try:
            msg = protocol.decode(line)
            print(f"[mock_x4 <- bridge] {json.dumps(msg)}", flush=True)
        except ValueError:
            print(f"[mock_x4 <- bridge] (raw) {line!r}", flush=True)


async def _handle_client(reader: asyncio.StreamReader, writer: asyncio.StreamWriter,
                         state: dict) -> None:
    print("\n[mock_x4] bridge connected", flush=True)
    state["writer"] = writer
    # Greet like X4 would once it's ready.
    writer.write(protocol.encode(protocol.ready()))
    await writer.drain()
    try:
        await _read_bridge(reader)
    finally:
        print("[mock_x4] bridge disconnected", flush=True)
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


async def _host_socket(path: str, state: dict) -> None:
    if os.path.exists(path):
        os.unlink(path)
    server = await asyncio.start_unix_server(
        lambda r, w: _handle_client(r, w, state), path=path)
    print(f"[mock_x4] listening on {path}", flush=True)
    async with server:
        await server.serve_forever()


async def _join_pipe(path: str, state: dict) -> None:
    reader, state["writer"] = await open_pipe(path)
    print(f"[mock_x4] connected to bridge at {path}", flush=True)
    await _read_bridge(reader)
    print("\n[mock_x4] bridge closed the pipe", flush=True)


async def main() -> None:
    p = argparse.ArgumentParser(description="Stand in for X4 on the bridge's transport.")
    via = p.add_mutually_exclusive_group()
    via.add_argument("--socket", help="host this Unix socket, as X4 does on Linux "
                     "(default /tmp/x4_twitch.sock off Windows)")
    via.add_argument("--pipe", help=r"connect to this named pipe, as X4 does on Windows "
                     r"(default \\.\pipe\twitch on Windows)")
    args = p.parse_args()
    if args.socket is None and args.pipe is None:
        if sys.platform == "win32":
            args.pipe = r"\\.\pipe\twitch"
        else:
            args.socket = "/tmp/x4_twitch.sock"

    state: dict = {"writer": None}
    link = _join_pipe(args.pipe, state) if args.pipe else _host_socket(args.socket, state)
    await asyncio.gather(link, _console(state))


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
    except OSError as e:
        print(f"[mock_x4] could not connect ({e}); is the bridge running?", file=sys.stderr)
