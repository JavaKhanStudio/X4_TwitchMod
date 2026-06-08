"""Wire a Source to the X4 link and run until the source ends.

    source.events()  --(Twitch events)-->  X4
    X4 actions       --(say/...)-->        source.handle_action()
"""

from __future__ import annotations

import asyncio
import logging

from . import protocol
from .catalog import STARTER
from .commands import CommandEngine
from .config import Config
from .sources import make_source
from .x4link import X4Link

log = logging.getLogger("app")


async def main(config: Config) -> None:
    source = make_source(config)
    engine = CommandEngine(STARTER)
    link = X4Link(config.socket_path, on_message=source.handle_action,
                  reconnect_delay=config.reconnect_delay)

    link_task = asyncio.create_task(link.run(), name="x4link")
    log.info("bridge up: source=%s socket=%s", source.name, config.socket_path)

    try:
        async for event in source.events():
            # Control messages (ready/hello) pass straight through; everything
            # else goes through the command engine (permissions + cooldowns).
            if event.get("t") in (protocol.READY, protocol.HELLO):
                await link.send(event)
                continue
            for action in engine.process(event):
                sent = await link.send(action)
                log.debug("cmd -> X4 (sent=%s): %s", sent, action)
    finally:
        log.info("source ended; shutting down")
        link.stop()
        await source.aclose()
        # let the link task observe stop and unwind
        try:
            await asyncio.wait_for(link_task, timeout=2.0)
        except asyncio.TimeoutError:
            link_task.cancel()
