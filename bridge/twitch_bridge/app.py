"""Wire a Source to the X4 link and run until the source ends.

    source.events()  --(Twitch events)-->  X4
    X4 actions       --(say/...)-->        source.handle_action()
"""

from __future__ import annotations

import asyncio
import logging
import webbrowser
from pathlib import Path

from . import protocol, setup_store
from .admin import Admin
from .catalog import STARTER
from .commands import CommandEngine
from .config import Config
from .dashboard import Dashboard
from .economy import Economy
from .fleet import Fleet
from .runtime import Runtime
from .sources import make_source
from .wallet import Wallet
from .x4link import BaseX4Link, make_x4_link

log = logging.getLogger("app")


async def _poll_x4(link: BaseX4Link, status) -> None:
    """Mirror the X4 link state into the dashboard status (decoupled from X4Link)."""
    prev = None
    try:
        while True:
            now = link.connected
            if now != prev:
                status.set_x4(now)
                prev = now
            await asyncio.sleep(0.5)
    except asyncio.CancelledError:
        pass


async def _award_loop(wallet: Wallet, status) -> None:
    """Award coins to active viewers every interval, persist, refresh the dashboard."""
    try:
        while True:
            await asyncio.sleep(wallet.s.coin_interval)
            given = wallet.award()
            wallet.save()
            status.set_econ(wallet.stats())
            log.debug("awarded %d coins across %d viewers", given, len(wallet.viewers))
    except asyncio.CancelledError:
        pass


def _apply_saved_creds(config: Config) -> None:
    """Load persisted Twitch app creds (from the dashboard's Connect button) so the
    twitch source auto-connects on subsequent runs. Env vars still win if set."""
    if config.source != "twitch":
        return
    saved = setup_store.load()
    config.client_id = config.client_id or saved.get("client_id", "")
    config.client_secret = config.client_secret or saved.get("client_secret", "")
    config.channel = config.channel or saved.get("channel", "")


def _connect_from_dashboard(body: dict, source, loop) -> None:
    """Called from the dashboard thread when the user clicks Connect.
    Blank fields fall back to the saved values — so the user never has to
    re-enter the secret (Twitch shows it only once)."""
    saved = setup_store.load()
    cid = (body.get("client_id") or "").strip() or saved.get("client_id", "")
    secret = (body.get("client_secret") or "").strip() or saved.get("client_secret", "")
    chan = (body.get("channel") or "").strip() or saved.get("channel", "")
    if not (cid and secret):
        return
    setup_store.save({"client_id": cid, "client_secret": secret, "channel": chan})
    if hasattr(source, "connect"):
        asyncio.run_coroutine_threadsafe(source.connect(cid, secret, chan), loop)


def _open_browser(url: str) -> None:
    try:
        webbrowser.open(url)
    except (webbrowser.Error, OSError) as e:  # never let opening a browser kill the companion
        log.warning("could not auto-open browser (%s) — open %s manually", e, url)


class Companion:
    """One running companion: the source, the X4 link, the economy and the dashboard,
    and the handlers that connect them. main() builds one and runs it."""

    def __init__(self, config: Config) -> None:
        from .status import Status

        _apply_saved_creds(config)
        self.config = config
        self.source = source = make_source(config)
        self.runtime = Runtime()   # live testing switches, toggled from the dashboard
        self.engine = CommandEngine(STARTER, runtime=self.runtime)
        self.status = status = Status(source=source.name, channel=config.channel,
                                      socket_path=config.socket_path)
        # If this is the twitch source, mirror its connection state into the dashboard.
        if hasattr(source, "set_status_cb"):
            source.set_status_cb(lambda: status.set_twitch(source.state()))
            status.set_twitch(source.state())

        # Restart plumbing: the dashboard's Restart button sets stop_event (from its
        # daemon thread, via the loop) so run() unblocks and runs its normal
        # shutdown — freeing the port + X4 pipe — before __main__ re-execs.
        self.loop = asyncio.get_running_loop()
        self.stop_event = asyncio.Event()
        self.restart = False

        self.wallet = self.econ = self.fleet = None
        if config.economy:
            self.wallet = Wallet(config.wallet_path)
            # Adoptions live beside the wallet: same directory, same lifetime. The roster
            # itself is NOT persisted — X4 republishes it on every load.
            self.fleet = Fleet(Path(config.wallet_path).with_name("adoptions.json"))
            self.econ = Economy(self.wallet, runtime=self.runtime, fleet=self.fleet)
            status.set_econ(self.wallet.stats())
        self.admin = Admin(self.runtime, status, wallet=self.wallet, fleet=self.fleet)
        self.admin.publish_flags()

        # X4 -> bridge: one handler per message type `t`. A type with no entry goes to
        # the source's action handler (a `say` reaches chat that way). A new `t` is one
        # constant in protocol.py plus one entry here.
        self.x4_handlers = {protocol.FLEET: self._on_fleet,
                            protocol.CMDFAIL: self._on_cmdfail}
        if self.econ is not None:   # without the economy nobody owns ships: pass through
            self.x4_handlers[protocol.SHIPDOWN] = self._on_ship_change
            self.x4_handlers[protocol.SHIPNEW] = self._on_ship_change

        self.link = make_x4_link(config.socket_path, on_message=self.on_x4_message,
                                 reconnect_delay=config.reconnect_delay)
        self.dash = None

    # -- dashboard callbacks (called from the dashboard's daemon thread) ---------

    def request_restart(self) -> None:
        self.restart = True
        self.loop.call_soon_threadsafe(self.stop_event.set)

    def on_connect(self, body: dict) -> None:
        _connect_from_dashboard(body, self.source, self.loop)

    def on_disconnect(self) -> None:
        if hasattr(self.source, "disconnect"):
            asyncio.run_coroutine_threadsafe(self.source.disconnect(), self.loop)

    def on_admin(self, body: dict) -> dict:
        """Dashboard actions (admin.py). Runs on the event loop so wallet + runtime
        changes never race the loop's own reads."""
        try:
            return asyncio.run_coroutine_threadsafe(self.admin.run(body), self.loop).result(timeout=5)
        except Exception as e:  # noqa: BLE001 — never let the dashboard thread crash
            log.exception("dashboard action %r failed", body.get("action"))
            return {"ok": False, "error": str(e)}

    # -- X4 -> bridge ---------------------------------------------------------------

    async def on_x4_message(self, msg: dict) -> None:
        # Every X4 -> bridge message flows through the status feed first.
        self.status.record_action(msg)
        handler = self.x4_handlers.get(msg.get("t"))
        if handler is not None:
            await handler(msg)
        else:
            await self.source.handle_action(msg)

    async def _on_fleet(self, msg: dict) -> None:
        """The player's ship roster. Bookkeeping only — it never reaches chat."""
        fleet = self.fleet
        if fleet is None:
            return
        n = fleet.update(msg)
        lost = fleet.prune_missing()
        self.status.note(f"fleet: {n} ships"
                         + (f" ({fleet.total} owned)" if fleet.truncated else "")
                         + (f"; {len(lost)} adopted ship(s) went missing" if lost else ""))
        # Re-arm X4's death watch for every adopted ship still in the fleet.
        # MD's group is rebuilt from scratch by a savegame load, and a save
        # from another timeline may hold a completely different one, so the
        # registry has to keep asserting what it believes. add_to_group is
        # idempotent, and there are only ever a handful of adopted ships, so
        # re-sending each roster is cheaper than tracking MD's state here.
        for code in list(fleet.adoptions):
            if code in fleet.ships:
                await self.dispatch(protocol.command("watch_ship", "bridge", {"idcode": code}))

    async def _on_ship_change(self, msg: dict) -> None:
        """An adopted ship died, or a replacement for one was built. Both change who
        owns what, so they go through the economy. dispatch() (not handle_action)
        because handle_ship_new answers with a `cmd` as well as a `say` — the
        rename of the new hull rides the ordinary adopt_ship path."""
        handler = (self.econ.handle_ship_down if msg["t"] == protocol.SHIPDOWN
                   else self.econ.handle_ship_new)
        for out in handler(msg):
            await self.dispatch(out)

    async def _on_cmdfail(self, msg: dict) -> None:
        """A command X4 couldn't carry out (no room for a station, no target, ...):
        refund the buyer instead of leaving them charged for nothing. The economy
        turns it into the chat message, so nothing else is said about it here."""
        if self.econ is None:
            return
        for out in self.econ.handle_x4_failure(msg):
            self.status.record_action(out)
            await self.source.handle_action(out)

    # -- bridge -> chat / X4 ----------------------------------------------------------

    async def dispatch(self, out: dict) -> None:
        """Route one output: a `say` goes to chat, anything else (cmd) goes to X4."""
        if out.get("t") == protocol.SAY:
            await self.source.handle_action(out)
            self.status.record_action(out)
        else:
            await self.link.send(out)
            self.status.record_command(out)

    async def consume(self) -> None:
        self.status.set_source_running(True)
        try:
            async for event in self.source.events():
                # Control messages (ready/hello) pass straight through.
                if event.get("t") in (protocol.READY, protocol.HELLO):
                    await self.link.send(event)
                    continue
                self.status.record_event(event)
                # Economy handles !buy / !balance / !gift / admin (chat only); the
                # command engine handles STARTER prefixes + event reactions. Disjoint.
                if self.econ is not None and event.get("t") == protocol.CHAT:
                    for out in self.econ.handle_chat(event):
                        await self.dispatch(out)
                for action in self.engine.process(event):
                    await self.dispatch(action)
            if self.wallet is not None:
                self.wallet.save()
        finally:
            self.status.set_source_running(False)

    # -- lifetime ----------------------------------------------------------------------

    def start_dashboard(self) -> None:
        config = self.config
        self.dash = Dashboard(self.status, port=config.dashboard_port,
                              on_connect=self.on_connect, on_disconnect=self.on_disconnect,
                              on_admin=self.on_admin, on_restart=self.request_restart).start()
        log.info("companion dashboard → %s  (open this in your browser)", self.dash.url)
        if config.open_browser:
            _open_browser(self.dash.url)

    async def run(self) -> bool:
        """Run until the source ends (headless) or stop_event fires (dashboard).
        True -> the Restart button was pressed; __main__ re-execs a fresh process
        now that the port + X4 pipe are released."""
        config = self.config
        if config.dashboard:
            self.start_dashboard()
        # Self-install the menu launcher (app menu / Start Menu) so a shared mod just
        # needs to be run once.
        if config.launcher:
            from .launcher import ensure_launcher
            made = ensure_launcher()
            if made:
                log.info("menu launcher: %s", made)

        link_task = asyncio.create_task(self.link.run(), name="x4link")
        tasks = [asyncio.create_task(self.consume(), name="consume"),
                 asyncio.create_task(_poll_x4(self.link, self.status), name="x4poll")]
        if self.wallet is not None:
            tasks.append(asyncio.create_task(_award_loop(self.wallet, self.status), name="award"))
        log.info("bridge up: source=%s socket=%s economy=%s", self.source.name,
                 config.socket_path, "on" if self.econ else "off")
        try:
            if config.dashboard:
                # A manually-started companion must NOT die when its source ends — the
                # user is watching the dashboard. Stay alive (X4 link keeps retrying)
                # until interrupted (Ctrl-C) or the Restart button fires stop_event.
                await self.stop_event.wait()
            else:
                # Headless / tests: exit when the source is exhausted.
                await tasks[0]
        finally:
            await self.shutdown(link_task, tasks)
        return self.restart

    async def shutdown(self, link_task, tasks) -> None:
        log.info("shutting down")
        self.link.stop()
        for t in tasks:
            t.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        if self.wallet is not None:
            self.wallet.save()
        await self.source.aclose()
        if self.dash is not None:
            self.dash.stop()
        # let the link task observe stop and unwind
        try:
            await asyncio.wait_for(link_task, timeout=2.0)
        except asyncio.TimeoutError:
            link_task.cancel()


async def main(config: Config) -> bool:
    return await Companion(config).run()
