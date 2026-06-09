"""Real Twitch source — EventSub WebSocket (read) + Helix (send), via twitchAPI.

Reads chat / channel-points / subs / cheers / raids / follows from Twitch and
yields them as protocol messages for X4. Handles X4 -> Twitch `say` actions via
Helix. Auth + token refresh are handled by UserAuthenticationStorageHelper.

Requires:  pip install "twitchAPI>=4"   (see requirements.txt)
Config:    TWITCH_CLIENT_ID, TWITCH_CLIENT_SECRET, TWITCH_CHANNEL, TWITCH_TOKEN_FILE
Docs:      ../../docs/03-twitch-api.md

Field names on `data.event` follow Twitch's EventSub payload spec; accessed
defensively so a minor library/version difference logs rather than crashes.
[VERIFY] event attribute names on the first live run.
"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import AsyncIterator

from .. import protocol
from ..config import Config
from .base import Source

log = logging.getLogger("source.twitch")

try:
    from twitchAPI.twitch import Twitch
    from twitchAPI.oauth import UserAuthenticationStorageHelper
    from twitchAPI.eventsub.websocket import EventSubWebsocket
    from twitchAPI.type import AuthScope
    _IMPORT_ERROR: Exception | None = None
except Exception as e:  # pragma: no cover - exercised only without the dep
    Twitch = UserAuthenticationStorageHelper = EventSubWebsocket = AuthScope = None  # type: ignore
    _IMPORT_ERROR = e


# Scopes we request. Each maps to one subscription; if you don't grant a scope,
# that subscription is skipped (see _safe_listen) but the rest still work.
def _scopes() -> list:
    return [
        AuthScope.USER_READ_CHAT,              # read chat (channel.chat.message)
        AuthScope.USER_WRITE_CHAT,             # send chat (Helix)
        AuthScope.USER_BOT,                    # act as a chat bot
        AuthScope.CHANNEL_READ_REDEMPTIONS,    # channel points
        AuthScope.CHANNEL_READ_SUBSCRIPTIONS,  # subs
        AuthScope.BITS_READ,                   # cheers
        AuthScope.MODERATOR_READ_FOLLOWERS,    # follows
    ]


def _badges(event) -> list[str]:
    out = []
    for b in getattr(event, "badges", None) or []:
        sid = getattr(b, "set_id", None)
        if sid:
            out.append(sid)
    return out


class TwitchSource(Source):
    name = "twitch"

    def __init__(self, config: Config):
        if _IMPORT_ERROR is not None:
            raise RuntimeError(
                "twitchAPI not installed. `pip install -r requirements.txt` "
                "(uncomment twitchAPI). Or use --source stdin."
            ) from _IMPORT_ERROR
        # No creds required up front: the companion starts IDLE and the user
        # connects from the dashboard (the OAuth button). Env creds auto-connect.
        self.config = config
        self._queue: asyncio.Queue[dict] = asyncio.Queue()
        self._loop: asyncio.AbstractEventLoop | None = None
        self._twitch = None
        self._eventsub = None
        self._broadcaster_id: str | None = None
        self._bot_id: str | None = None
        # connection state for the dashboard
        self.connected = False
        self.connecting = False
        self.login: str | None = None
        self.error: str | None = None
        self._status_cb = None

    def set_status_cb(self, cb) -> None:
        """Register a callback invoked (no args) whenever the connection state changes."""
        self._status_cb = cb

    def _notify(self) -> None:
        if self._status_cb:
            try:
                self._status_cb()
            except Exception:  # noqa: BLE001 - status must never break the source
                pass

    def state(self) -> dict:
        # client_id is semi-public (prefill convenience); the SECRET is never exposed.
        return {"connected": self.connected, "connecting": self.connecting,
                "login": self.login, "channel": self.config.channel,
                "client_id": self.config.client_id, "error": self.error}

    async def connect(self, client_id: str, client_secret: str, channel: str = "") -> bool:
        """Authenticate + subscribe (the OAuth flow). Returns success. Safe to call
        from the dashboard via run_coroutine_threadsafe on the bridge loop."""
        if self.connecting:
            return False
        self.config.client_id = client_id.strip()
        self.config.client_secret = client_secret.strip()
        self.config.channel = (channel or "").strip()
        if not self.config.client_id or not self.config.client_secret:
            self.error = "Client ID and Secret are required."
            self._notify()
            return False
        self.connecting = True
        self.error = None
        self._notify()
        try:
            await self._teardown()
            await self._setup()  # bind() opens the browser on first run
            self.connected = True
            await self._queue.put(protocol.ready())
            return True
        except Exception as e:  # noqa: BLE001 - surface to the UI, don't crash
            self.error = str(e)
            self.connected = False
            log.warning("connect failed: %s", e)
            return False
        finally:
            self.connecting = False
            self._notify()

    async def disconnect(self) -> None:
        await self._teardown()
        self.connected = False
        self.login = None
        self._notify()

    def _emit(self, msg: dict) -> None:
        """Enqueue from an EventSub callback. Thread-safe: callbacks may run on a
        different loop/thread than our consumer, so hop back via the main loop."""
        loop = self._loop
        if loop is None:
            self._queue.put_nowait(msg)
        else:
            loop.call_soon_threadsafe(self._queue.put_nowait, msg)

    # ---- lifecycle ---------------------------------------------------------

    async def _setup(self) -> None:
        cfg = self.config
        self._loop = asyncio.get_running_loop()
        self._twitch = await Twitch(cfg.client_id, cfg.client_secret)

        storage = Path(cfg.token_file)
        storage.parent.mkdir(parents=True, exist_ok=True)
        helper = UserAuthenticationStorageHelper(self._twitch, _scopes(), storage_path=storage)
        await helper.bind()  # first run opens a browser; then refreshes from disk

        # NOTE: Twitch.get_users() is an ASYNC GENERATOR in twitchAPI 4.x — iterate
        # it, never `await` it (that raises "'async_generator' object can't be awaited").
        me = await self._first_user()
        if me is None:
            raise RuntimeError("could not fetch the authenticated Twitch user")
        self._bot_id = me.id  # the authenticated account reads/sends chat
        if cfg.channel:
            chan = await self._first_user(logins=[cfg.channel])
            if chan is None:
                raise RuntimeError(f"Twitch channel not found: {cfg.channel!r}")
            self._broadcaster_id = chan.id
        else:
            self._broadcaster_id = self._bot_id  # default: our own channel
        self.login = me.login
        self._notify()
        log.info("authenticated as %s; broadcaster=%s", me.login, self._broadcaster_id)

        self._eventsub = EventSubWebsocket(self._twitch)
        self._eventsub.start()  # non-blocking; subscribe within ~10s

        b, bot = self._broadcaster_id, self._bot_id
        await self._safe_listen("chat",
            self._eventsub.listen_channel_chat_message(b, bot, self._on_chat))
        await self._safe_listen("redeem",
            self._eventsub.listen_channel_points_custom_reward_redemption_add(b, self._on_redeem))
        await self._safe_listen("subscribe",
            self._eventsub.listen_channel_subscribe(b, self._on_sub))
        await self._safe_listen("cheer",
            self._eventsub.listen_channel_cheer(b, self._on_cheer))
        await self._safe_listen("follow",
            self._eventsub.listen_channel_follow_v2(b, b, self._on_follow))
        # channel.raid takes no scope; subscribe on incoming raids to our channel.
        await self._safe_listen("raid",
            self._eventsub.listen_channel_raid(self._on_raid, to_broadcaster_user_id=b))

    async def _first_user(self, **kw):
        """First user from Twitch.get_users() (an async generator in twitchAPI 4.x)."""
        async for u in self._twitch.get_users(**kw):
            return u
        return None

    async def _safe_listen(self, label: str, coro) -> None:
        """Await one listen_* call; log+skip on failure (e.g. missing scope)."""
        try:
            await coro
            log.info("subscribed: %s", label)
        except Exception as e:  # noqa: BLE001 - one bad sub shouldn't kill the rest
            log.warning("subscribe %s failed: %s", label, e)

    # ---- EventSub callbacks -> queue --------------------------------------

    async def _on_chat(self, data) -> None:
        ev = data.event
        self._emit(protocol.chat(
            getattr(ev, "chatter_user_name", "?"),
            getattr(getattr(ev, "message", None), "text", ""),
            _badges(ev)))

    async def _on_redeem(self, data) -> None:
        ev = data.event
        reward = getattr(ev, "reward", None)
        self._emit(protocol.redeem(
            getattr(ev, "user_name", "?"),
            getattr(reward, "title", "?")))

    async def _on_sub(self, data) -> None:
        ev = data.event
        self._emit(protocol.sub(
            getattr(ev, "user_name", "?"),
            str(getattr(ev, "tier", "1000"))))

    async def _on_cheer(self, data) -> None:
        ev = data.event
        self._emit(protocol.cheer(
            getattr(ev, "user_name", None) or "anonymous",
            int(getattr(ev, "bits", 0))))

    async def _on_raid(self, data) -> None:
        ev = data.event
        self._emit(protocol.raid(
            getattr(ev, "from_broadcaster_user_name", "?"),
            int(getattr(ev, "viewers", 0))))

    async def _on_follow(self, data) -> None:
        ev = data.event
        self._emit(protocol.follow(getattr(ev, "user_name", "?")))

    # ---- Source interface --------------------------------------------------

    async def events(self) -> AsyncIterator[dict]:
        self._loop = asyncio.get_running_loop()
        # Env creds (or persisted ones loaded into config) auto-connect; otherwise
        # we idle until the dashboard's Connect button calls connect().
        if self.config.client_id and self.config.client_secret:
            await self.connect(self.config.client_id, self.config.client_secret, self.config.channel)
        while True:
            yield await self._queue.get()

    async def handle_action(self, msg: dict) -> None:
        if msg.get("t") != protocol.SAY:
            log.info("[twitch] ignoring action: %s", msg)
            return
        if self._twitch is None:
            log.warning("[twitch] not ready; dropping say")
            return
        try:
            await self._twitch.send_chat_message(
                broadcaster_id=self._broadcaster_id,
                sender_id=self._bot_id,
                message=str(msg.get("msg", "")))
        except Exception as e:  # noqa: BLE001
            log.warning("[twitch] send_chat_message failed: %s", e)

    async def _teardown(self) -> None:
        if self._eventsub is not None:
            try:
                await self._eventsub.stop()
            except Exception:  # noqa: BLE001
                pass
            self._eventsub = None
        if self._twitch is not None:
            try:
                await self._twitch.close()
            except Exception:  # noqa: BLE001
                pass
            self._twitch = None

    async def aclose(self) -> None:
        await self._teardown()
