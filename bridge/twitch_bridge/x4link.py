"""The link to X4: an asyncio Unix-domain-socket client with reconnect.

Architecture (see docs/06): X4 HOSTS the socket (via the bekopharm LuaSocket
fork); this bridge connects in as a client. We read newline-delimited JSON
messages and dispatch them to a callback, and we send messages with `send()`.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Awaitable, Callable

from . import protocol

log = logging.getLogger("x4link")

OnMessage = Callable[[dict], Awaitable[None]]


class X4Link:
    def __init__(self, socket_path: str, on_message: OnMessage, reconnect_delay: float = 1.0):
        self._path = socket_path
        self._on_message = on_message
        self._reconnect_delay = reconnect_delay
        self._writer: asyncio.StreamWriter | None = None
        self._connected = asyncio.Event()
        self._stop = False

    @property
    def connected(self) -> bool:
        return self._writer is not None and not self._writer.is_closing()

    async def send(self, msg: dict) -> bool:
        """Send one message. Returns False if not currently connected."""
        if not self.connected:
            log.warning("drop (not connected): %s", msg)
            return False
        assert self._writer is not None
        self._writer.write(protocol.encode(msg))
        try:
            await self._writer.drain()
            return True
        except (ConnectionError, OSError) as e:
            log.warning("send failed: %s", e)
            return False

    async def run(self) -> None:
        """Connect-read loop with reconnect. Returns when stop() is called."""
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
                while not self._stop:
                    line = await reader.readline()
                    if not line:  # EOF -> X4 closed the socket
                        break
                    try:
                        msg = protocol.decode(line)
                    except ValueError as e:
                        log.warning("bad line from X4: %s", e)
                        continue
                    await self._on_message(msg)
            except (ConnectionError, OSError) as e:
                log.info("X4 connection error: %s", e)
            finally:
                self._connected.clear()
                self._writer = None
                writer.close()
                log.info("disconnected from X4")
                if not self._stop:
                    await asyncio.sleep(self._reconnect_delay)

    def stop(self) -> None:
        self._stop = True
        if self._writer is not None:
            self._writer.close()
