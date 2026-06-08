"""Starter command catalog — EDIT THIS to define what viewers can do.

This is a *starting point*, deliberately conservative (the one freeform spawn is
mod-gated). Each Command's `action` is the id the X4 side dispatches on; add a
matching cue in extensions/twitch_integration/md/Twitch_Integration.xml.

Roles: everyone < subscriber < vip < moderator < broadcaster.
"""

from .commands import Command

STARTER = [
    # chat commands ---------------------------------------------------------
    Command(id="ping", action="ping",
            chat_prefix="!ping", min_role="everyone",
            cooldown=5.0),

    Command(id="spawn", action="spawn",
            chat_prefix="!spawn", min_role="moderator",   # gated until you trust it
            cooldown=30.0, arg_names=["ship"]),

    # channel-points redemption (match the reward's exact title) -------------
    Command(id="pirate_attack", action="pirate_attack",
            on_event="redeem", reward="Pirate Attack",
            cooldown=60.0),

    # event reactions -------------------------------------------------------
    Command(id="reinforcements", action="reinforcements",
            on_event="raid", cooldown=10.0),     # args carry {viewers}

    Command(id="sub_reward", action="sub_reward",
            on_event="sub"),                     # args carry {tier, months}

    Command(id="cheer_boost", action="cheer_boost",
            on_event="cheer", cooldown=5.0),     # args carry {bits}
]
