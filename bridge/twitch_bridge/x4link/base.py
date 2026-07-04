"""Shared behaviour for every X4 transport.

A transport's only job is to move newline-delimited JSON lines (see `protocol`)
between the bridge and X4. What differs per platform is *who opens what* — so the
only thing subclasses implement is `run()` (the connect/serve loop); everything
else (framing-safe sends, the read loop, connection state, teardown) lives here.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Awaitable, Callable

from .. import protocol

log = logging.getLogger("x4link")

OnMessage = Callable[[dict], Awaitable[None]]


class BaseX4Link:
    def __init__(self, socket_path: str, on_message: OnMessage, reconnect_delay: float = 1.0):
        self._path = socket_path
        self._on_message = on_message
        self._reconnect_delay = reconnect_delay
        self._writer: asyncio.StreamWriter | None = None
        self._connected = asyncio.Event()
        self._stop = False
        self._send_lock = asyncio.Lock()

    @property
    def connected(self) -> bool:
        return self._writer is not None and not self._writer.is_closing()

    async def send(self, msg: dict) -> bool:
        """Send one message as a single write (== one message frame for X4, which
        reads in message mode). The lock guarantees one frame per send even under
        concurrent callers. Returns False if not currently connected."""
        if not self.connected:
            log.warning("drop (not connected): %s", msg)
            return False
        async with self._send_lock:
            writer = self._writer
            if writer is None or writer.is_closing():
                log.warning("drop (not connected): %s", msg)
                return False
            writer.write(protocol.encode(msg))
            try:
                await writer.drain()
                return True
            except (ConnectionError, OSError) as e:
                log.warning("send failed: %s", e)
                return False

    async def run(self) -> None:
        """Connect/serve loop. Returns when stop() is called. Subclass implements."""
        raise NotImplementedError

    def stop(self) -> None:
        self._stop = True
        if self._writer is not None:
            self._writer.close()

    async def _read_loop(self, reader: asyncio.StreamReader) -> None:
        """Read newline-delimited JSON until EOF/stop, dispatching each message."""
        while not self._stop:
            line = await reader.readline()
            if not line:  # EOF -> the other end closed the connection
                break
            try:
                msg = protocol.decode(line)
            except ValueError as e:
                log.warning("bad line from X4: %s", e)
                continue
            await self._on_message(msg)
