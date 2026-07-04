r"""The link to X4. Cross-platform, two mirror-image transports:

* **Linux** (native X4 via the bekopharm LuaSocket fork): X4 HOSTS a Unix-domain
  socket in the savegame folder; this bridge connects in as a CLIENT.
  → `asyncio.open_unix_connection`.

* **Windows** (native X4 via the stock SirNukes Named Pipes API): the roles are
  REVERSED — the external app HOSTS the named pipe (`\\.\pipe\twitch`) and X4
  connects in as a CLIENT (winpipe `open_pipe` = CreateFile). See docs/02 Path A.
  → asyncio's Proactor `start_serving_pipe` (stdlib; no pywin32 needed).

Both directions speak the same newline-delimited JSON (see `protocol`). Because
X4's winpipe reads in *message* mode (one `file:read()` == one of our writes), we
serialise sends behind a lock so every protocol message goes out as exactly one
pipe write == one message frame. The public surface (`connected`, `send`, `run`,
`stop`) is identical on both platforms.
"""

from __future__ import annotations

import asyncio
import logging
import sys
from typing import Awaitable, Callable

from . import protocol

log = logging.getLogger("x4link")

OnMessage = Callable[[dict], Awaitable[None]]

IS_WINDOWS = sys.platform == "win32"


class X4Link:
    def __init__(self, socket_path: str, on_message: OnMessage, reconnect_delay: float = 1.0):
        self._path = socket_path
        self._on_message = on_message
        self._reconnect_delay = reconnect_delay
        self._writer: asyncio.StreamWriter | None = None
        self._connected = asyncio.Event()
        self._stop = False
        self._send_lock = asyncio.Lock()
        self._servers: list | None = None  # Windows: the PipeServer handles

    @property
    def connected(self) -> bool:
        return self._writer is not None and not self._writer.is_closing()

    async def send(self, msg: dict) -> bool:
        """Send one message as a single pipe write (== one message frame for X4).
        Returns False if not currently connected."""
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
        """Connect/serve loop. Returns when stop() is called."""
        if IS_WINDOWS:
            await self._run_win_server()
        else:
            await self._run_unix_client()

    def stop(self) -> None:
        self._stop = True
        if self._writer is not None:
            self._writer.close()
        if self._servers:
            for s in self._servers:
                try:
                    s.close()
                except Exception:  # noqa: BLE001 - best effort teardown
                    pass

    # --- Linux: connect to the socket X4 hosts --------------------------------

    async def _run_unix_client(self) -> None:
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

    # --- Windows: host the pipe X4 connects into ------------------------------

    async def _run_win_server(self) -> None:
        loop = asyncio.get_running_loop()

        def factory() -> asyncio.StreamReaderProtocol:
            reader = asyncio.StreamReader(loop=loop)
            return asyncio.StreamReaderProtocol(reader, self._on_win_client, loop=loop)

        while not self._stop and self._servers is None:
            try:
                # start_serving_pipe keeps at least one free pipe instance alive,
                # so X4 can connect at any time (and reconnect after a game/ui reload).
                self._servers = await loop.start_serving_pipe(factory, self._path)
                log.info("hosting X4 pipe at %s (waiting for X4 to connect)", self._path)
            except OSError as e:
                log.warning("cannot host pipe %s (%s); retrying", self._path, e)
                await asyncio.sleep(self._reconnect_delay)

        try:
            while not self._stop:
                await asyncio.sleep(0.2)
        finally:
            if self._servers:
                for s in self._servers:
                    try:
                        s.close()
                    except Exception:  # noqa: BLE001
                        pass
            self._servers = None

    async def _on_win_client(self, reader: asyncio.StreamReader,
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

    # --- shared read loop -----------------------------------------------------

    async def _read_loop(self, reader: asyncio.StreamReader) -> None:
        while not self._stop:
            line = await reader.readline()
            if not line:  # EOF -> X4 closed the connection
                break
            try:
                msg = protocol.decode(line)
            except ValueError as e:
                log.warning("bad line from X4: %s", e)
                continue
            await self._on_message(msg)
