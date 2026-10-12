"""Event source abstraction.

A Source produces Twitch events (bridge -> X4) and optionally handles actions
the game sends back (X4 -> bridge, e.g. "say this in chat" via Helix).
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator

log = logging.getLogger("source")


class Source:
    name = "base"

    async def events(self) -> AsyncIterator[dict]:
        """Yield protocol messages (dicts) to forward to X4. Override me."""
        raise NotImplementedError
        if False:  # pragma: no cover - makes this an async generator for typing
            yield {}

    async def handle_action(self, msg: dict) -> None:
        """Handle an action message from X4 (X4 -> bridge). Default: log it."""
        log.info("[X4 action] %s", msg)

    async def aclose(self) -> None:
        """Optional cleanup."""
        return None
