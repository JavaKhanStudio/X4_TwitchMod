"""Fake Twitch source: read commands from the console (or a piped stdin).

Lets us develop and test the whole bridge + X4 plumbing WITHOUT live Twitch.
Type `help` for the command list. Lines starting with `{` are treated as raw
protocol JSON and passed straight through.
"""

from __future__ import annotations

import asyncio
import json
import logging
import sys
from typing import AsyncIterator

from .. import protocol
from .base import Source

log = logging.getLogger("source.stdin")

HELP = """\
fake-twitch commands (-> run through the command engine, like real events):
  chat <user> <message...>        a chat message (no badges)
  chatas <role> <user> <msg...>   chat with a badge (role: subscriber|vip|moderator|broadcaster)
  redeem <user> <reward...>       channel-points redemption
  sub <user> [tier] [months]      subscription
  cheer <user> <bits>             bits
  raid <user> <viewers>           raid
  follow <user>                   follow
  ready                           emit the 'ready' handshake
  {...}                           raw protocol JSON, passed through
  help                            this help
  quit                            stop the bridge
"""


def _parse(line: str) -> dict | None:
    line = line.strip()
    if not line:
        return None
    if line.startswith("{"):
        try:
            return json.loads(line)
        except json.JSONDecodeError as e:
            log.warning("bad JSON: %s", e)
            return None

    parts = line.split()
    cmd, args = parts[0].lower(), parts[1:]
    try:
        if cmd == "help":
            print(HELP, end="")
            return None
        if cmd == "chat":
            return protocol.chat(args[0], " ".join(args[1:]))
        if cmd == "chatas":  # chatas <role> <user> <msg...>
            return protocol.chat(args[1], " ".join(args[2:]), badges=[args[0]])
        if cmd == "redeem":
            return protocol.redeem(args[0], " ".join(args[1:]))
        if cmd == "sub":
            return protocol.sub(args[0], args[1] if len(args) > 1 else "1000",
                                int(args[2]) if len(args) > 2 else 1)
        if cmd == "cheer":
            return protocol.cheer(args[0], int(args[1]))
        if cmd == "raid":
            return protocol.raid(args[0], int(args[1]))
        if cmd == "follow":
            return protocol.follow(args[0])
        if cmd == "ready":
            return protocol.ready()
    except (IndexError, ValueError):
        log.warning("usage error; type 'help'")
        return None
    log.warning("unknown command %r; type 'help'", cmd)
    return None


class StdinSource(Source):
    name = "stdin"

    async def events(self) -> AsyncIterator[dict]:
        loop = asyncio.get_running_loop()
        print(HELP, end="", file=sys.stderr)
        while True:
            # Read a line off stdin without blocking the event loop.
            line = await loop.run_in_executor(None, sys.stdin.readline)
            if line == "":  # EOF
                log.info("stdin EOF; source ending")
                return
            if line.strip().lower() == "quit":
                return
            msg = _parse(line)
            if msg is not None:
                yield msg

    async def handle_action(self, msg: dict) -> None:
        if msg.get("t") == protocol.SAY:
            print(f"[X4 -> would post to chat] {msg.get('msg')!r}", file=sys.stderr)
        else:
            print(f"[X4 -> action] {msg}", file=sys.stderr)
