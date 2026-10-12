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
from collections.abc import AsyncIterator, Callable

from .. import protocol
from .base import Source

log = logging.getLogger("source.stdin")

# command -> (usage, what it does, args -> event). The help is built from this, so
# a command cannot exist without being listed, or be listed without existing.
COMMANDS: dict[str, tuple[str, str, Callable[[list[str]], dict]]] = {
    "chat": ("<user> <message...>", "a chat message (no badges)",
             lambda a: protocol.chat(a[0], " ".join(a[1:]))),
    "chatas": ("<role> <user> <msg...>",
               "chat with a badge (role: subscriber|vip|moderator|broadcaster)",
               lambda a: protocol.chat(a[1], " ".join(a[2:]), badges=[a[0]])),
    "redeem": ("<user> <reward...>", "channel-points redemption",
               lambda a: protocol.redeem(a[0], " ".join(a[1:]))),
    "sub": ("<user> [tier] [months]", "subscription",
            lambda a: protocol.sub(a[0], a[1] if len(a) > 1 else "1000",
                                   int(a[2]) if len(a) > 2 else 1)),
    "cheer": ("<user> <bits>", "bits", lambda a: protocol.cheer(a[0], int(a[1]))),
    "raid": ("<user> <viewers>", "raid", lambda a: protocol.raid(a[0], int(a[1]))),
    "follow": ("<user>", "follow", lambda a: protocol.follow(a[0])),
    "ready": ("", "emit the 'ready' handshake", lambda a: protocol.ready()),
}
# Handled outside the table: raw JSON in _parse, help in _parse, quit in events().
_OTHERS = [("{...}", "raw protocol JSON, passed through"),
           ("help", "this help"),
           ("quit", "stop the bridge")]

HELP = ("fake-twitch commands (-> run through the command engine, like real events):\n"
        + "".join(f"  {left:<32}{what}\n" for left, what in
                  [(f"{c} {usage}".strip(), what) for c, (usage, what, _) in COMMANDS.items()]
                  + _OTHERS))


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

    cmd, *args = line.split()
    cmd = cmd.lower()
    if cmd == "help":
        print(HELP, end="")
        return None
    if cmd not in COMMANDS:
        log.warning("unknown command %r; type 'help'", cmd)
        return None
    try:
        return COMMANDS[cmd][2](args)
    except (IndexError, ValueError):
        log.warning("usage error; type 'help'")
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
