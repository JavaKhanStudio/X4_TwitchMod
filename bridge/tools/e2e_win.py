"""End-to-end smoke on Windows: launch the REAL companion as a subprocess
(stdin source, no dashboard), connect a mock X4 client to the hosted pipe, drive
a '!ping' chat event through the engine, and confirm the vetted command arrives
at X4 — then round-trip a 'say' back. Exercises the full pipeline on the pipe
transport the way the game will.

Run:  py bridge/tools/e2e_win.py
"""

from __future__ import annotations

import asyncio
import os
import sys

from pipe_client import open_pipe
from twitch_bridge import protocol

PIPE = r"\\.\pipe\twitch_e2e"
BRIDGE_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


async def main() -> int:
    env = dict(os.environ, X4_TWITCH_SOCKET=PIPE, PYTHONUNBUFFERED="1")
    proc = await asyncio.create_subprocess_exec(
        sys.executable, "-m", "twitch_bridge",
        "--source", "stdin", "--no-dashboard", "--no-launcher", "--no-economy",
        cwd=BRIDGE_ROOT, env=env,
        stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT)

    # Wait for the bridge to start hosting the pipe, then connect as X4 would.
    reader = writer = None
    for _ in range(50):
        await asyncio.sleep(0.1)
        try:
            reader, writer = await open_pipe(PIPE)
            break
        except OSError:
            pass
    assert writer is not None, "bridge never started hosting the pipe"
    print("[e2e] connected to bridge pipe")

    hello = protocol.decode(await asyncio.wait_for(reader.readline(), timeout=3.0))
    assert hello["t"] == protocol.HELLO, hello
    print("[e2e] got HELLO from bridge")

    # Drive a chat event: everyone can '!ping' -> engine emits cmd id=ping to X4.
    proc.stdin.write(b"chat tester !ping\n")
    await proc.stdin.drain()

    cmd = protocol.decode(await asyncio.wait_for(reader.readline(), timeout=5.0))
    assert cmd["t"] == protocol.COMMAND and cmd["id"] == "ping", cmd
    print(f"[e2e] X4 received vetted command: {cmd}")

    # X4 -> bridge: a 'say' (the ping handler would trigger this in-game). Confirm
    # the bridge accepts it without error by sending it and then quitting cleanly.
    writer.write(protocol.encode(protocol.say("pong from X4")))
    await writer.drain()
    await asyncio.sleep(0.2)

    proc.stdin.write(b"quit\n")
    await proc.stdin.drain()
    try:
        out = await asyncio.wait_for(proc.stdout.read(), timeout=5.0)
    except asyncio.TimeoutError:
        out = b""
    proc.terminate()
    try:
        await asyncio.wait_for(proc.wait(), timeout=3.0)
    except asyncio.TimeoutError:
        proc.kill()

    text = out.decode("utf-8", "replace")
    assert "would post to chat" in text, f"bridge did not handle the say action:\n{text}"
    print("[e2e] bridge handled the X4->chat 'say' action")
    print("\nOK: full companion pipeline works on Windows (Twitch->engine->X4 and X4->chat)")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
