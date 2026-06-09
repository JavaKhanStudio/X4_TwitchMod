"""Wire a Source to the X4 link and run until the source ends.

    source.events()  --(Twitch events)-->  X4
    X4 actions       --(say/...)-->        source.handle_action()
"""

from __future__ import annotations

import asyncio
import logging

from . import protocol, setup_store
from .catalog import STARTER
from .commands import CommandEngine
from .config import Config
from .dashboard import Dashboard
from .economy import Economy
from .sources import make_source
from .wallet import Wallet
from .x4link import X4Link

log = logging.getLogger("app")


async def _poll_x4(link: X4Link, status) -> None:
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


async def main(config: Config) -> None:
    from .status import Status

    # Load persisted Twitch app creds (from the dashboard's Connect button) so the
    # twitch source auto-connects on subsequent runs. Env vars still win if set.
    if config.source == "twitch":
        saved = setup_store.load()
        config.client_id = config.client_id or saved.get("client_id", "")
        config.client_secret = config.client_secret or saved.get("client_secret", "")
        config.channel = config.channel or saved.get("channel", "")

    source = make_source(config)
    engine = CommandEngine(STARTER)
    status = Status(source=source.name, channel=config.channel, socket_path=config.socket_path)

    # If this is the twitch source, mirror its connection state into the dashboard.
    if hasattr(source, "set_status_cb"):
        source.set_status_cb(lambda: status.set_twitch(source.state()))
        status.set_twitch(source.state())

    loop = asyncio.get_running_loop()

    def on_connect(body: dict) -> None:
        """Called from the dashboard thread when the user clicks Connect."""
        cid = (body.get("client_id") or "").strip()
        secret = (body.get("client_secret") or "").strip()
        chan = (body.get("channel") or "").strip()
        if not (cid and secret):
            return
        setup_store.save({"client_id": cid, "client_secret": secret, "channel": chan})
        if hasattr(source, "connect"):
            asyncio.run_coroutine_threadsafe(source.connect(cid, secret, chan), loop)

    def on_disconnect() -> None:
        if hasattr(source, "disconnect"):
            asyncio.run_coroutine_threadsafe(source.disconnect(), loop)

    wallet = econ = None
    if config.economy:
        wallet = Wallet(config.wallet_path)
        econ = Economy(wallet)
        status.set_econ(wallet.stats())

    # X4 -> bridge actions also flow through the status feed before the source handles them.
    async def on_x4_message(msg: dict) -> None:
        status.record_action(msg)
        await source.handle_action(msg)

    link = X4Link(config.socket_path, on_message=on_x4_message,
                  reconnect_delay=config.reconnect_delay)

    dash = None
    if config.dashboard:
        dash = Dashboard(status, port=config.dashboard_port,
                         on_connect=on_connect, on_disconnect=on_disconnect).start()
        log.info("companion dashboard → %s  (open this in your browser)", dash.url)
        if config.open_browser:
            try:
                import webbrowser
                webbrowser.open(dash.url)
            except Exception as e:  # never let opening a browser kill the companion
                log.warning("could not auto-open browser (%s) — open %s manually", e, dash.url)

    # Self-install the app-menu launcher so a shared mod just needs to be run once.
    if config.launcher:
        from .launcher import ensure_launcher
        made = ensure_launcher()
        if made:
            log.info("app-menu launcher: %s", made)

    link_task = asyncio.create_task(link.run(), name="x4link")
    poll_task = asyncio.create_task(_poll_x4(link, status), name="x4poll")
    award_task = (asyncio.create_task(_award_loop(wallet, status), name="award")
                  if wallet is not None else None)
    log.info("bridge up: source=%s socket=%s economy=%s", source.name, config.socket_path,
             "on" if econ else "off")

    async def dispatch(out: dict) -> None:
        """Route one output: a `say` goes to chat, anything else (cmd) goes to X4."""
        if out.get("t") == protocol.SAY:
            await source.handle_action(out)
            status.record_action(out)
        else:
            await link.send(out)
            status.record_command(out)

    async def consume() -> None:
        status.set_source_running(True)
        try:
            async for event in source.events():
                # Control messages (ready/hello) pass straight through.
                if event.get("t") in (protocol.READY, protocol.HELLO):
                    await link.send(event)
                    continue
                status.record_event(event)
                # Economy handles !buy / !balance / !gift / admin (chat only); the
                # command engine handles STARTER prefixes + event reactions. Disjoint.
                if econ is not None and event.get("t") == protocol.CHAT:
                    for out in econ.handle_chat(event):
                        await dispatch(out)
                for action in engine.process(event):
                    await dispatch(action)
            if econ is not None and wallet is not None:
                wallet.save()
        finally:
            status.set_source_running(False)

    consume_task = asyncio.create_task(consume(), name="consume")
    try:
        if config.dashboard:
            # A manually-started companion must NOT die when its source ends — the
            # user is watching the dashboard. Stay alive (X4 link keeps retrying)
            # until interrupted (Ctrl-C). The dashboard reflects the source state.
            await asyncio.Event().wait()
        else:
            # Headless / tests: exit when the source is exhausted.
            await consume_task
    finally:
        log.info("shutting down")
        link.stop()
        tasks = [consume_task, poll_task] + ([award_task] if award_task else [])
        for t in tasks:
            t.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        if wallet is not None:
            wallet.save()
        await source.aclose()
        if dash is not None:
            dash.stop()
        # let the link task observe stop and unwind
        try:
            await asyncio.wait_for(link_task, timeout=2.0)
        except asyncio.TimeoutError:
            link_task.cancel()
