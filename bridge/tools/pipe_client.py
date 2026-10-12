r"""Connect to the bridge's Windows named pipe the way X4 does (as a CLIENT).

On Windows the bridge HOSTS \\.\pipe\<name>; the game (SirNukes winpipe,
CreateFile) connects in. The Windows tools all need that client end, so it
lives here once. Windows only: needs the Proactor loop's create_pipe_connection.
"""

from __future__ import annotations

import asyncio
import os
import sys

# Allow running from the bridge/ dir without installing the package.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


async def open_pipe(path: str) -> tuple[asyncio.StreamReader, asyncio.StreamWriter]:
    """Connect to the pipe at `path`; raise OSError if nobody is hosting it."""
    loop = asyncio.get_running_loop()
    reader = asyncio.StreamReader(loop=loop)
    trans, proto = await loop.create_pipe_connection(
        lambda: asyncio.StreamReaderProtocol(reader, loop=loop), path)
    return reader, asyncio.StreamWriter(trans, proto, reader, loop)
