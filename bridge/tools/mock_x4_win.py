"""Mock X4 for Windows: stands in for the game so we can test the bridge locally.

On Windows the BRIDGE hosts the named pipe and X4 connects in as a CLIENT (just
like the stock SirNukes winpipe does with CreateFile on \\.\pipe\twitch). This
script is that client: it connects, prints every message it receives (the vetted
commands the bridge sends), and lets you type lines back (X4 -> bridge actions).

Usage:
    py tools/mock_x4_win.py                      # default pipe \\.\pipe\twitch
    py tools/mock_x4_win.py --pipe \\.\pipe\twitch

Type at the prompt:
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

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from twitch_bridge import protocol  # noqa: E402


async def _reader_loop(reader: asyncio.StreamReader) -> None:
    while True:
        line = await reader.readline()
        if not line:
            print("\n[mock_x4] bridge closed the pipe", flush=True)
            break
        try:
            msg = protocol.decode(line)
            print(f"[mock_x4 <- bridge] {json.dumps(msg)}", flush=True)
        except ValueError:
            print(f"[mock_x4 <- bridge] (raw) {line!r}", flush=True)


async def _console(writer: asyncio.StreamWriter) -> None:
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
    p.add_argument("--pipe", default=r"\\.\pipe\twitch")
    args = p.parse_args()

    loop = asyncio.get_running_loop()
    reader = asyncio.StreamReader(loop=loop)
    trans, proto = await loop.create_pipe_connection(
        lambda: asyncio.StreamReaderProtocol(reader, loop=loop), args.pipe)
    writer = asyncio.StreamWriter(trans, proto, reader, loop)
    print(f"[mock_x4] connected to bridge at {args.pipe}", flush=True)

    await asyncio.gather(_reader_loop(reader), _console(writer))


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
    except OSError as e:
        print(f"[mock_x4] could not connect ({e}); is the bridge running?", file=sys.stderr)
