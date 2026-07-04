"""Linux transport: X4 HOSTS a Unix-domain socket (via the bekopharm LuaSocket
fork, in the savegame folder); the bridge connects in as a CLIENT. See docs/02
Path B and docs/06.
"""

from __future__ import annotations

import asyncio

from . import base
from .base import BaseX4Link
from .. import protocol

log = base.log


class UnixSocketX4Link(BaseX4Link):
    async def run(self) -> None:
        while not self._stop:
            try:
                reader, writer = await asyncio.open_unix_connection(self._path)
            except (FileNotFoundError, ConnectionRefusedError, OSError) as e:
                log.info("waiting for X4 socket %s (%s)", self._path, e.__class__.__name__)
                await asyncio.sleep(self._reconnect_delay)
                continue

            self._writer = writer
            self._connected.set()
            log.info("connected to X4 at %s", self._path)
            await self.send({"t": protocol.HELLO, "role": "bridge"})

            try:
                await self._read_loop(reader)
            except (ConnectionError, OSError) as e:
                log.info("X4 connection error: %s", e)
            finally:
                self._connected.clear()
                self._writer = None
                writer.close()
                log.info("disconnected from X4")
                if not self._stop:
                    await asyncio.sleep(self._reconnect_delay)
