"""Live, dashboard-toggleable switches shared by the engines.

Not persisted — these are session-only testing aids the streamer flips from the
companion UI. Both the command engine (commands.py) and the purchase engine
(economy.py) hold the SAME Runtime instance, so a checkbox in the dashboard
changes their behaviour with no restart.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class Runtime:
    # When False, every cooldown (store re-buy cooldowns AND command-engine
    # global/per-user cooldowns) is bypassed — for testing without waiting.
    cooldowns_enabled: bool = True
    # When False, the per-rolling-window purchase caps are bypassed: both the
    # per-event cap ("maxed this window") and the per-karma-type cap ("too many
    # 'bad' events right now, try later") — for testing without hitting limits.
    caps_enabled: bool = True
    # Who owns a station chat builds when the buy line doesn't say. False (the
    # default) => the Twitch Allies faction: friendly, defends the sector, trades,
    # but not free real estate on the player's account. True => the player owns
    # everything chat builds. A viewer can always override this for one purchase by
    # ending the line with `player` or `ally`.
    stations_to_player: bool = False
    # "Accept crisis level" — the streamer's consent to tier-3 (Doom) events, the
    # ones that can cost the player their fleet, their station or the save. OFF by
    # default: a crisis event is in the shop and priced, but nobody can buy it (and
    # no moderator can fire its test command) until the streamer ticks the box.
    #
    # WHY A SWITCH AND NOT `enabled=False` IN THE CATALOG: `enabled` is authoring
    # state — changing it means editing catalog.py and restarting the companion, so
    # in practice a doom event shipped off stays off forever. This is the same
    # decision made live, mid-stream, by the person who actually carries the
    # consequences, and it can be taken back just as fast. Session-only on purpose:
    # consent to blow up the save should not silently survive into next stream.
    crisis_enabled: bool = False
