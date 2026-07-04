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
