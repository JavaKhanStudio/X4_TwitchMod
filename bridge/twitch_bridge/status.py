"""Shared live state for the companion dashboard.

The asyncio app writes to this from the event loop; the dashboard HTTP server
(a daemon thread) reads `snapshot()`. A plain lock keeps the two sides honest.
Deliberately dependency-free.
"""

from __future__ import annotations

import collections
import threading
import time
from typing import Any


def describe(msg: dict) -> str:
    """A short human label for an event/action, for the activity feed."""
    t = msg.get("t", "?")
    user = msg.get("user") or msg.get("by") or ""
    if t == "chat":
        return f"{user}: {msg.get('msg', '')}".strip()
    if t == "cmd":
        return f"{user} → {msg.get('id', '?')}".strip(" →")
    if t == "redeem":
        return f"{user} redeemed “{msg.get('reward', '?')}”"
    if t == "sub":
        return f"{user} subscribed (tier {msg.get('tier', '?')})"
    if t == "cheer":
        return f"{user} cheered {msg.get('bits', '?')} bits"
    if t == "raid":
        return f"{user} raided with {msg.get('viewers', '?')} viewers"
    if t == "follow":
        return f"{user} followed"
    if t == "say":
        return f"say: {msg.get('msg', '')}"
    return t


class Status:
    """Thread-safe snapshot of what the companion is doing right now."""

    def __init__(self, *, source: str = "", channel: str = "", socket_path: str = "") -> None:
        self._lock = threading.Lock()
        self._started = time.time()
        self.source = source
        self.channel = channel
        self.socket_path = socket_path
        self.x4_connected = False
        self.source_running = False
        self.events_in = 0          # Twitch -> game
        self.commands_fired = 0     # vetted commands sent to X4
        self.actions_out = 0        # game -> Twitch (e.g. say)
        self.last_error: str | None = None
        self.econ: dict = {}        # wallet stats (viewers, coins) — doc 08
        self.twitch: dict = {}      # twitch connection state (connected/login/error)
        self.flags: dict = {}       # live testing switches (e.g. cooldowns_enabled)
        self._recent: collections.deque[dict] = collections.deque(maxlen=50)

    # -- writers (called from the asyncio loop) ------------------------------
    def _push(self, direction: str, text: str) -> None:
        self._recent.appendleft({"ts": time.time(), "dir": direction, "text": text})

    def set_x4(self, connected: bool) -> None:
        with self._lock:
            if connected != self.x4_connected:
                self.x4_connected = connected
                self._push("sys", "X4 linked" if connected else "X4 disconnected")

    def set_source_running(self, running: bool) -> None:
        with self._lock:
            self.source_running = running
            self._push("sys", f"source “{self.source}” {'started' if running else 'stopped'}")

    def record_event(self, msg: dict) -> None:
        with self._lock:
            self.events_in += 1
            self._push("in", describe(msg))

    def record_command(self, action: dict) -> None:
        with self._lock:
            self.commands_fired += 1
            self._push("cmd", describe(action))

    def record_action(self, msg: dict) -> None:
        with self._lock:
            self.actions_out += 1
            self._push("out", describe(msg))

    def error(self, text: str) -> None:
        with self._lock:
            self.last_error = text
            self._push("err", text)

    def note(self, text: str) -> None:
        """Push a plain system line to the activity feed (e.g. admin actions)."""
        with self._lock:
            self._push("sys", text)

    def set_econ(self, stats: dict) -> None:
        with self._lock:
            self.econ = dict(stats)

    def set_flags(self, flags: dict) -> None:
        with self._lock:
            self.flags = dict(flags)

    def set_twitch(self, state: dict) -> None:
        with self._lock:
            was = self.twitch.get("connected")
            self.twitch = dict(state)
            if state.get("connected") and not was:
                self._push("sys", f"Twitch connected as {state.get('login') or '?'}")
            elif state.get("error"):
                self._push("err", f"Twitch: {state['error']}")

    # -- reader (called from the dashboard thread) ---------------------------
    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            return {
                "source": self.source,
                "channel": self.channel,
                "socket_path": self.socket_path,
                "x4_connected": self.x4_connected,
                "source_running": self.source_running,
                "events_in": self.events_in,
                "commands_fired": self.commands_fired,
                "actions_out": self.actions_out,
                "last_error": self.last_error,
                "econ": self.econ,
                "twitch": self.twitch,
                "flags": self.flags,
                "uptime_s": int(time.time() - self._started),
                "recent": list(self._recent),
            }
