#!/usr/bin/env python3
"""Unit test: Companion.on_x4_message routes each X4 -> bridge `t` to its handler (r22).

FLEET and CMDFAIL never reach the source (chat); SHIPDOWN/SHIPNEW go through the
economy when there is one and pass through when there is not; any other type goes
to the source's action handler. Every message is recorded in the status feed. Stdlib
only: the source and the X4 link are swapped for recorders.
"""
import asyncio
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from twitch_bridge import protocol  # noqa: E402
from twitch_bridge.app import Companion  # noqa: E402
from twitch_bridge.config import Config  # noqa: E402

ok = True


def check(cond, label):
    global ok
    ok = ok and bool(cond)
    print(f"{'PASS' if cond else 'FAIL'}: {label}")


class Recorder:
    """Stands in for both the source (handle_action) and the X4 link (send)."""
    name = "stdin"

    def __init__(self):
        self.got = []

    async def handle_action(self, msg):
        self.got.append(msg)

    async def send(self, msg):
        self.got.append(msg)


async def companion(economy: bool):
    cfg = Config(source="stdin", economy=economy, dashboard=False, launcher=False,
                 wallet_path=str(Path(tempfile.mkdtemp()) / "wallet.json"))
    c = Companion(cfg)
    c.source, c.link = Recorder(), Recorder()
    return c


async def main():
    c = await companion(economy=True)
    await c.on_x4_message(protocol.fleet(""))
    check(c.source.got == [], "economy on: FLEET is bookkeeping, it never reaches chat")
    await c.on_x4_message(protocol.shipdown("PSF-481"))
    check(c.source.got == [], "economy on: SHIPDOWN of a ship nobody adopted says nothing")
    await c.on_x4_message({"t": protocol.CMDFAIL, "id": "nosuch", "ref": "x"})
    check([m.get("t") for m in c.source.got] == [protocol.SAY],
          "economy on: CMDFAIL goes to the economy, whose `say` (not the raw cmdfail) "
          f"reaches the source (got {c.source.got})")
    say = {"t": protocol.SAY, "msg": "hello chat"}
    await c.on_x4_message(say)
    check(c.source.got[-1] == say, "a type with no handler (say) goes to the source")
    # fleet, shipdown, cmdfail, say: four in, plus the economy's answer to the cmdfail
    check(c.status.actions_out == 5, "every X4 message is recorded in the status feed "
          f"(actions_out={c.status.actions_out})")

    c = await companion(economy=False)
    await c.on_x4_message(protocol.fleet(""))
    await c.on_x4_message({"t": protocol.CMDFAIL, "id": "x", "ref": "x"})
    check(c.source.got == [], "economy off: FLEET and CMDFAIL are swallowed")
    down = protocol.shipdown("PSF-481")
    await c.on_x4_message(down)
    check(c.source.got == [down], "economy off: SHIPDOWN passes through to the source")


asyncio.run(main())
print("\n" + ("ALL PASS" if ok else "SOME FAILED"))
sys.exit(0 if ok else 1)
