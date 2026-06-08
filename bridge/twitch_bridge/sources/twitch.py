"""Real Twitch source — STUB.

This is where the live integration goes (Milestone 3). The plan, per
docs/03-twitch-api.md, current for 2026:

  * Auth: OAuth user token + refresh; validate hourly. Scopes:
      user:read:chat   (read chat via EventSub)
      user:write:chat  (send chat via Helix)
      plus channel:bot / user:bot as needed.
  * Read: EventSub WebSocket. Subscribe to:
      channel.chat.message
      channel.channel_points_custom_reward_redemption.add
      channel.subscribe / channel.subscription.gift
      channel.cheer, channel.raid, channel.follow
    Normalize each notification into a protocol message (protocol.chat(), ...)
    and yield it.
  * Act: handle_action() -> call Helix (POST /helix/chat/messages, etc).

Recommended lib: `twitchAPI` (PyTwitchAPI) — has EventSub WS + Helix + OAuth.
Intentionally not implemented yet so the bridge runs with stdlib only.
"""

from __future__ import annotations

import logging
from typing import AsyncIterator

from ..config import Config
from .base import Source

log = logging.getLogger("source.twitch")


class TwitchSource(Source):
    name = "twitch"

    def __init__(self, config: Config):
        self.config = config

    async def events(self) -> AsyncIterator[dict]:
        raise NotImplementedError(
            "TwitchSource is a stub. Implement EventSub here (Milestone 3), "
            "or run with --source stdin for now. See docs/03-twitch-api.md."
        )
        if False:  # pragma: no cover
            yield {}

    async def handle_action(self, msg: dict) -> None:
        # TODO: map {"t":"say",...} -> Helix POST /helix/chat/messages
        log.info("[twitch action stub] %s", msg)
