"""Windows transport check for X4Link: the bridge HOSTS the pipe, a mock X4
connects as CLIENT. Verifies both directions + connected-state transitions.

Run:  py bridge/tools/test_x4link_win.py
"""

from __future__ import annotations

import asyncio
import sys

from pipe_client import open_pipe
from twitch_bridge import protocol
from twitch_bridge.x4link import X4Link

PIPE = r"\\.\pipe\twitch_selftest"


async def main() -> int:
    received: list[dict] = []

    async def on_message(msg: dict) -> None:
        received.append(msg)

    link = X4Link(PIPE, on_message=on_message)
    run_task = asyncio.create_task(link.run())

    # Give the server a moment to start hosting the pipe.
    await asyncio.sleep(0.3)
    assert not link.connected, "should not be connected before a client attaches"

    reader, writer = await open_pipe(PIPE)

    # The bridge greets with HELLO on connect; wait for connected + that line.
    hello = await asyncio.wait_for(reader.readline(), timeout=2.0)
    assert protocol.decode(hello)["t"] == protocol.HELLO, hello
    await asyncio.sleep(0.05)
    assert link.connected, "should be connected once X4 attaches"

    # X4 -> bridge: a say action.
    writer.write(protocol.encode(protocol.say("hello from X4")))
    await writer.drain()

    # bridge -> X4: a vetted command (sent as one message frame).
    ok = await link.send(protocol.command("spawn", by="tester"))
    assert ok, "send should succeed while connected"
    cmd_line = await asyncio.wait_for(reader.readline(), timeout=2.0)
    cmd = protocol.decode(cmd_line)
    assert cmd["t"] == protocol.COMMAND and cmd["id"] == "spawn", cmd

    # Two rapid sends must arrive as two separate frames (message-mode safety).
    await link.send(protocol.command("ping", by="a"))
    await link.send(protocol.command("pirate_attack", by="b"))
    l1 = protocol.decode(await asyncio.wait_for(reader.readline(), timeout=2.0))
    l2 = protocol.decode(await asyncio.wait_for(reader.readline(), timeout=2.0))
    assert [l1["id"], l2["id"]] == ["ping", "pirate_attack"], (l1, l2)

    await asyncio.sleep(0.1)
    assert any(m["t"] == protocol.SAY for m in received), received

    # Client disconnects -> bridge should notice.
    writer.close()
    await asyncio.sleep(0.3)
    assert not link.connected, "should disconnect when X4 leaves"

    # A reconnect should work (server keeps hosting).
    reader2, writer2 = await open_pipe(PIPE)
    hello2 = await asyncio.wait_for(reader2.readline(), timeout=2.0)
    assert protocol.decode(hello2)["t"] == protocol.HELLO
    writer2.close()

    link.stop()
    await asyncio.sleep(0.1)
    run_task.cancel()
    try:
        await run_task
    except asyncio.CancelledError:
        pass

    print("OK: Windows X4Link transport works (both directions, framing, reconnect)")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
