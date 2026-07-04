r"""Local X4 round-trip probe. Hosts \\.\pipe\twitch (like the bridge), waits for the
running game's mod to reconnect, sends a batch of raw commands, and prints X4's
replies (the 'say' lines the mod writes back). Lets us test the live Lua->MD path
without Twitch/chat.

Run the companion must be STOPPED first (it owns the pipe). Usage:
    py bridge/tools/x4_probe.py
"""
from __future__ import annotations
import asyncio, json, os, sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from twitch_bridge import protocol  # noqa: E402

PIPE = r"\\.\pipe\twitch"

# Each test: (label, cmd dict). The mod replies with a 'say' we capture.
TESTS = [
    ("argtest string", {"t": "cmd", "id": "argtest", "by": "probe", "args": {"value": "hello"}}),
    ("incident argon+paranid", {"t": "cmd", "id": "faction_incident", "by": "probe",
                                "args": {"faction1": "argon", "faction2": "paranid"}}),
    ("incident teladi only", {"t": "cmd", "id": "faction_incident", "by": "probe",
                              "args": {"faction1": "teladi"}}),
    ("incident none", {"t": "cmd", "id": "faction_incident", "by": "probe", "args": {}}),
]


async def main() -> int:
    loop = asyncio.get_running_loop()
    replies: list[str] = []
    connected = loop.create_future()
    writer_box: dict = {}

    async def on_client(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        writer_box["w"] = writer
        if not connected.done():
            connected.set_result(True)
        while True:
            line = await reader.readline()
            if not line:
                break
            try:
                msg = protocol.decode(line)
                if msg.get("t") == protocol.SAY:
                    replies.append(msg.get("msg", ""))
                    print(f"    <- say: {msg.get('msg')!r}", flush=True)
                else:
                    print(f"    <- {json.dumps(msg)}", flush=True)
            except ValueError:
                print(f"    <- (raw) {line!r}", flush=True)

    def factory():
        r = asyncio.StreamReader(loop=loop)
        return asyncio.StreamReaderProtocol(r, on_client, loop=loop)

    servers = await loop.start_serving_pipe(factory, PIPE)
    print(f"hosting {PIPE}; waiting for X4 to reconnect (up to 40s)...", flush=True)
    try:
        await asyncio.wait_for(connected, timeout=40)
    except asyncio.TimeoutError:
        print("X4 never connected — is the game running with the mod loaded?", flush=True)
        for s in servers:
            s.close()
        return 1
    print("X4 connected. Running tests...\n", flush=True)
    await asyncio.sleep(0.5)

    for label, cmd in TESTS:
        print(f"[{label}]  -> {json.dumps(cmd)}", flush=True)
        w = writer_box.get("w")
        if w is None or w.is_closing():
            print("    (pipe not connected; waiting for reconnect...)", flush=True)
            await asyncio.sleep(3.0)
            w = writer_box.get("w")
            if w is None:
                continue
        try:
            w.write(protocol.encode(cmd))
            await w.drain()
        except (ConnectionError, OSError) as e:
            print(f"    (send failed: {e}; X4 may have re-cycled the pipe)", flush=True)
        await asyncio.sleep(2.5)  # let MD process + write its say back

    print("\ndone.", flush=True)
    for s in servers:
        s.close()
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
