r"""Windows transport: the bridge HOSTS the named pipe (`\\.\pipe\twitch`) and X4
connects in as a CLIENT (the stock SirNukes winpipe `open_pipe` == CreateFile).
This is the mirror image of the Linux setup. See docs/02 Path A.

Uses asyncio's Proactor `start_serving_pipe` (stdlib — no pywin32). The server
keeps a free pipe instance available at all times, so X4 can connect whenever its
MD read loop fires, and re-connect after a game/ui reload.
"""

from __future__ import annotations

import asyncio

from . import base
from .base import BaseX4Link
from .. import protocol

log = base.log


class WinPipeX4Link(BaseX4Link):
    def __init__(self, socket_path: str, on_message: base.OnMessage,
                 reconnect_delay: float = 1.0):
        super().__init__(socket_path, on_message, reconnect_delay)
        self._servers: list | None = None

    async def run(self) -> None:
        loop = asyncio.get_running_loop()

        def factory() -> asyncio.StreamReaderProtocol:
            reader = asyncio.StreamReader(loop=loop)
            return asyncio.StreamReaderProtocol(reader, self._on_client, loop=loop)

        while not self._stop and self._servers is None:
            try:
                self._servers = await loop.start_serving_pipe(factory, self._path)
                log.info("hosting X4 pipe at %s (waiting for X4 to connect)", self._path)
            except OSError as e:
                log.warning("cannot host pipe %s (%s); retrying", self._path, e)
                await asyncio.sleep(self._reconnect_delay)

        try:
            while not self._stop:
                await asyncio.sleep(0.2)
        finally:
            self._close_servers()

    async def _on_client(self, reader: asyncio.StreamReader,
                         writer: asyncio.StreamWriter) -> None:
        """Called by start_serving_pipe each time X4 connects (incl. after a reload)."""
        self._writer = writer
        self._connected.set()
        log.info("X4 connected to pipe %s", self._path)
        await self.send({"t": protocol.HELLO, "role": "bridge"})
        try:
            await self._read_loop(reader)
        except (ConnectionError, OSError) as e:
            log.info("X4 pipe error: %s", e)
        finally:
            self._connected.clear()
            if self._writer is writer:
                self._writer = None
            try:
                writer.close()
            except Exception:  # noqa: BLE001
                pass
            log.info("X4 disconnected from pipe")

    def stop(self) -> None:
        super().stop()
        self._close_servers()

    def _close_servers(self) -> None:
        if self._servers:
            for s in self._servers:
                try:
                    s.close()
                except Exception:  # noqa: BLE001
                    pass
        self._servers = None
