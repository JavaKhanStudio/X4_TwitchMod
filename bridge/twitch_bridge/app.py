"""Wire a Source to the X4 link and run until the source ends.

    source.events()  --(Twitch events)-->  X4
    X4 actions       --(say/...)-->        source.handle_action()
"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path

from . import protocol, setup_store
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
    runtime = Runtime()   # live testing switches, toggled from the dashboard
    engine = CommandEngine(STARTER, runtime=runtime)
    status = Status(source=source.name, channel=config.channel, socket_path=config.socket_path)
    def publish_flags() -> None:
        """Push the WHOLE live-switch set to the dashboard. Status.set_flags replaces
        the dict rather than merging, so a partial push silently unsyncs the other
        checkboxes."""
        status.set_flags({"cooldowns_enabled": runtime.cooldowns_enabled,
                          "caps_enabled": runtime.caps_enabled,
                          "stations_to_player": runtime.stations_to_player,
                          "crisis_enabled": runtime.crisis_enabled})

    publish_flags()

    # If this is the twitch source, mirror its connection state into the dashboard.
    if hasattr(source, "set_status_cb"):
        source.set_status_cb(lambda: status.set_twitch(source.state()))
        status.set_twitch(source.state())

    loop = asyncio.get_running_loop()

    # Restart plumbing: the dashboard's Restart button sets stop_event (from its
    # daemon thread, via the loop) so the main loop below unblocks and runs its
    # normal shutdown — freeing the port + X4 pipe — before __main__ re-execs.
    stop_event = asyncio.Event()
    restart_state = {"restart": False}

    def request_restart() -> None:
        restart_state["restart"] = True
        loop.call_soon_threadsafe(stop_event.set)

    def on_connect(body: dict) -> None:
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

    def on_disconnect() -> None:
        if hasattr(source, "disconnect"):
            asyncio.run_coroutine_threadsafe(source.disconnect(), loop)

    wallet = econ = fleet = None
    if config.economy:
        wallet = Wallet(config.wallet_path)
        # Adoptions live beside the wallet: same directory, same lifetime. The roster
        # itself is NOT persisted — X4 republishes it on every load.
        fleet = Fleet(Path(config.wallet_path).with_name("adoptions.json"))
        econ = Economy(wallet, runtime=runtime, fleet=fleet)
        status.set_econ(wallet.stats())

    def on_admin(body: dict) -> dict:
        """Dashboard actions (give coins / block viewers / testing toggles). Runs on
        the event loop so wallet + runtime changes never race the loop's own reads.
        Called from the dashboard's daemon thread."""

        async def run() -> dict:
            action = (body.get("action") or "").strip()
            target = (body.get("user") or "").strip().lstrip("@").lower()
            # runtime testing toggles work with or without the economy
            if action == "stationowner":
                runtime.stations_to_player = bool(body.get("value"))
                publish_flags()
                status.note("stations now go to "
                            + ("the PLAYER" if runtime.stations_to_player else "the Twitch Allies"))
                return {"ok": True, "stations_to_player": runtime.stations_to_player}
            if action == "crisis":
                runtime.crisis_enabled = bool(body.get("value"))
                publish_flags()
                status.note("CRISIS LEVEL ACCEPTED — tier-3 events can be bought"
                            if runtime.crisis_enabled else "crisis events are off again")
                return {"ok": True, "crisis_enabled": runtime.crisis_enabled}
            if action in ("cooldowns", "caps"):
                field = "cooldowns_enabled" if action == "cooldowns" else "caps_enabled"
                setattr(runtime, field, bool(body.get("value")))
                publish_flags()
                label = "cooldowns" if action == "cooldowns" else "purchase limits"
                status.note(f"testing: {label} {'ON' if getattr(runtime, field) else 'OFF'}")
                return {"ok": True, field: getattr(runtime, field)}
            if wallet is None:
                return {"ok": False, "error": "economy is off"}
            if action == "list":
                # The moderation table. Each viewer carries their adopted ship, so a
                # mod looking at "who is this person" sees what they hold in the game
                # without cross-referencing a second panel.
                rows = wallet.viewer_list()
                if fleet is not None:
                    for r in rows:
                        r["ships"] = [fleet.card(c) for c in fleet.ships_of(r["username"])]
                return {"ok": True, "viewers": rows}
            if action == "adoptions":
                # Who holds what right now, plus the full lifecycle log. Read-only:
                # the dashboard shows it, nothing acts on it.
                if fleet is None:
                    return {"ok": False, "error": "the fleet is not tracked"}
                current = [dict(fleet.card(code), user=who)
                           for code, who in fleet.adoptions.items()]
                current.sort(key=lambda r: (r["user"], r["idcode"]))
                return {"ok": True, "adoptions": current,
                        "history": list(reversed(fleet.history))}
            if action == "giveall":
                amount = int(body.get("amount") or 0)
                for v in list(wallet.viewers.values()):
                    wallet.give_coins(v.username, amount)
                wallet.save()
                status.set_econ(wallet.stats())
                status.note(f"admin: gave {amount} coins to all {len(wallet.viewers)} viewers")
                return {"ok": True, "count": len(wallet.viewers), "amount": amount}
            if not target:
                return {"ok": False, "error": "a viewer name is required"}
            if action == "give":
                amount = int(body.get("amount") or 0)
                coins = wallet.give_coins(target, amount)
                wallet.save()
                status.set_econ(wallet.stats())
                status.note(f"admin: gave {amount} coins to {target} (now {coins})")
                return {"ok": True, "user": target, "coins": coins}
            if action in ("ban", "unban"):
                v = wallet.set_banned(target, action == "ban")
                wallet.save()
                status.note(f"admin: {'blocked' if v.banned else 'unblocked'} {target}")
                return {"ok": True, "user": target, "banned": v.banned}
            return {"ok": False, "error": f"unknown action '{action}'"}

        try:
            return asyncio.run_coroutine_threadsafe(run(), loop).result(timeout=5)
        except (ValueError, TypeError):
            return {"ok": False, "error": "invalid amount"}
        except Exception as e:  # noqa: BLE001 — never let the dashboard thread crash
            return {"ok": False, "error": str(e)}

    # X4 -> bridge actions also flow through the status feed before the source handles them.
    async def on_x4_message(msg: dict) -> None:
        status.record_action(msg)
        # A command X4 couldn't carry out (no room for a station, no target, ...):
        # refund the buyer instead of leaving them charged for nothing. The economy
        # turns it into the chat message, so nothing else is said about it here.
        # The player's ship roster. Bookkeeping only — it never reaches chat, so it
        # stops here instead of falling through to the source's action handler.
        if msg.get("t") == protocol.FLEET:
            if fleet is not None:
                n = fleet.update(msg)
                lost = fleet.prune_missing()
                status.note(f"fleet: {n} ships"
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
                        await dispatch(protocol.command("watch_ship", "bridge",
                                                        {"idcode": code}))
            return
        # An adopted ship died, or a replacement for one was built. Both change who
        # owns what, so they go through the economy. dispatch() (not handle_action)
        # because handle_ship_new answers with a `cmd` as well as a `say` — the
        # rename of the new hull rides the ordinary adopt_ship path.
        if msg.get("t") in (protocol.SHIPDOWN, protocol.SHIPNEW) and econ is not None:
            handler = (econ.handle_ship_down if msg["t"] == protocol.SHIPDOWN
                       else econ.handle_ship_new)
            for out in handler(msg):
                await dispatch(out)
            return
        if msg.get("t") == protocol.CMDFAIL:
            if econ is not None:
                for out in econ.handle_x4_failure(msg):
                    status.record_action(out)
                    await source.handle_action(out)
            return
        await source.handle_action(msg)

    link = make_x4_link(config.socket_path, on_message=on_x4_message,
                        reconnect_delay=config.reconnect_delay)

    dash = None
    if config.dashboard:
        dash = Dashboard(status, port=config.dashboard_port,
                         on_connect=on_connect, on_disconnect=on_disconnect,
                         on_admin=on_admin, on_restart=request_restart).start()
        log.info("companion dashboard → %s  (open this in your browser)", dash.url)
        if config.open_browser:
            try:
                import webbrowser
                webbrowser.open(dash.url)
            except Exception as e:  # never let opening a browser kill the companion
                log.warning("could not auto-open browser (%s) — open %s manually", e, dash.url)

    # Self-install the menu launcher (app menu / Start Menu) so a shared mod just
    # needs to be run once.
    if config.launcher:
        from .launcher import ensure_launcher
        made = ensure_launcher()
        if made:
            log.info("menu launcher: %s", made)

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
            # until interrupted (Ctrl-C) or the Restart button fires stop_event.
            await stop_event.wait()
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

    # True -> the Restart button was pressed; __main__ re-execs a fresh process
    # now that the port + X4 pipe are released.
    return restart_state["restart"]
