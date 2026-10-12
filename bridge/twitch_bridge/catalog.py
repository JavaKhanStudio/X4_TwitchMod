"""Catalog — what viewers can do.

Two layers live here:

1. `STARTER` — the **current runtime** catalog: a list of `Command`s the live
   `CommandEngine` already consumes (chat-prefix / event triggers + cooldowns +
   roles). This is what actually works today.

2. `StoreEvent` + `CATALOG` — the **forward economy schema** (doc 08, esp. §5 and
   §10). One `StoreEvent` is the single source of truth that must drive BOTH the
   `!buy` purchase engine (M4.0) AND the browsable item-list view (`/catalog` +
   the shareable export). It carries display metadata so the same record renders
   as a viewer-facing list — never a second catalog to keep in sync.

   This is intentionally a *stub* so the structure is locked in and a future
   session won't invent a different shape. It is NOT wired into the engine yet:
   the coin/karma wallet (M3.5/3.6) and the `!buy` dispatcher (M4.0) come first.
   Fields will evolve, but the shape — rich record, many projections — should not.

Roles: everyone < subscriber < vip < moderator < broadcaster.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .commands import Command

# ---------------------------------------------------------------------------
# 1. Current runtime catalog (live; consumed by CommandEngine today)
# ---------------------------------------------------------------------------
STARTER = [
    # chat commands ---------------------------------------------------------
    Command(id="ping", action="ping",
            chat_prefix="!ping", min_role="everyone",
            cooldown=5.0),

    Command(id="spawn", action="spawn",
            chat_prefix="!spawn", min_role="moderator",   # gated until you trust it
            cooldown=30.0, arg_names=["ship"]),

    # Combat-rank query — read-only, free, everyone. The bridge just vets + forwards;
    # MD (Twitch_OnRank) reads the game's fight statistics and answers in chat with
    # the current rank, ships destroyed, and fight score to the next rank. Both !rank
    # and !kills share the id "rank" so they share one 10s cooldown (no alias-hopping).
    Command(id="rank", action="rank", chat_prefix="!rank", min_role="everyone", cooldown=10.0),
    Command(id="rank", action="rank", chat_prefix="!kills", min_role="everyone", cooldown=10.0),

    # Economic (trade) rank query — same pattern; MD cue Twitch_OnTradeRank reads
    # stat.trade_rank / trade_score. !traderank + !econ share one 10s cooldown.
    # (Rank-UP announcements for both ranks are auto-pushed from MD's poll loop,
    # Twitch_RankWatch — no bridge command needed for those.)
    Command(id="traderank", action="traderank", chat_prefix="!traderank", min_role="everyone", cooldown=10.0),
    Command(id="traderank", action="traderank", chat_prefix="!econ", min_role="everyone", cooldown=10.0),

    # simple testing commands: fire the faction spawns from chat on demand,
    # without needing a channel-points redeem or a raid. They reuse the existing
    # MD actions, so they hit the same cues (Twitch_OnPirateAttack /
    # Twitch_OnReinforcements). Mod-gated so viewers can't spam them; change
    # min_role to "everyone" for open testing.
    Command(id="test_enemy", action="pirate_attack",
            chat_prefix="!enemy", min_role="moderator", cooldown=5.0),
    Command(id="test_ally", action="reinforcements",
            chat_prefix="!ally", min_role="moderator", cooldown=5.0),

    # Same idea for the two station-interference effects: fire them straight from
    # chat without spending coins, so they can be tested against a real station.
    # Both act on whatever station is NEAREST the player in the player's current
    # sector, so park next to one before trying them.
    # Tracker mines — the free mod-only way to fire the same MD cue
    # (Twitch_OnMineField) that viewers reach by paying for `!buy mines`.
    Command(id="test_mines", action="mine_field",
            chat_prefix="!mines", min_role="moderator", cooldown=15.0),

    # The Doom event, free and mod-only, so it can be tried before viewers reach it.
    # Fires the same MD cue (Twitch_OnXenonArmada) `!buy armada` reaches. 60s because
    # the last one is probably still shooting. crisis=True: mod or not, this does
    # nothing until the dashboard's "accept crisis level" box is ticked — the switch
    # is the streamer's consent, and a moderator is not the streamer.
    Command(id="test_armada", action="xenon_armada", crisis=True,
            chat_prefix="!armada", min_role="moderator", cooldown=60.0),

    # The counter to it (MD cue Twitch_OnTerranTaskForce). NOT crisis-gated, on
    # purpose and asymmetrically: the switch exists to stop chat ending the save, and
    # this is the thing that stops chat ending the save. A streamer who has turned
    # crisis off can still be jumped by vanilla Xenon, and should still be rescuable.
    Command(id="test_taskforce", action="terran_taskforce",
            chat_prefix="!terran", min_role="moderator", cooldown=60.0),

    Command(id="test_disarm", action="station_disarm",
            chat_prefix="!disarm", min_role="moderator", cooldown=5.0),
    Command(id="test_loot", action="station_loot",
            chat_prefix="!loot", min_role="moderator", cooldown=5.0),

    # DIAGNOSTIC: echoes the one argument MD receives back to chat, to isolate the
    # chat->bridge->lua->MD arg-passing path from any effect logic. Usage: !argtest hello
    Command(id="argtest", action="argtest",
            chat_prefix="!argtest", min_role="everyone", arg_names=["value"]),

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

    # Boso Ta "video call" -----------------------------------------------------
    # MD cue Twitch_OnBosoCall puts Boso Ta on the cockpit monitor (live-rendered +
    # lip-synced) playing one of his real vanilla voice clips. The single arg is a
    # MOOD, not a line: MD owns the line ids and picks one from that mood, so a
    # repeated event doesn't replay the same clip.
    #
    # NOTHING HERE NEEDS A "BUSY" COOLDOWN. A call that arrives while the player is
    # in a menu or mid-conversation is HELD by MD and shown as soon as the game can,
    # rather than dropped — so the cooldowns below are purely about pacing, not about
    # trying to guess a good moment. Cooldowns still matter: they cap how many calls
    # can pile up behind one long menu visit.
    #
    # VIEWER-FACING, not just a test hook: subscriber is the floor, so subs, VIPs and
    # mods can all call Boso (ROLE_RANK is ordered everyone < subscriber < vip <
    # moderator < broadcaster, and the gate is a >= test, so naming the LOWEST allowed
    # role admits every role above it). Plain viewers cannot.
    # `!boso` with no argument walks through the moods one per call (MD keeps the
    # counter), so pressing it a few times demos every mood; `!boso angry` jumps
    # straight to one; `!boso random` draws from the full 1263-line pool. Either way
    # MD answers in chat with the mood and line id — at the moment it actually plays,
    # not when queued.
    # TWO cooldowns, because they do different jobs now that it is not mod-only:
    # the 5s global paces the channel as a whole, and the per-user minute stops one
    # sub holding the line all stream. Neither is about picking a good moment — a
    # call that lands while the player is busy is HELD by MD and shown when it can
    # be, rather than dropped — they exist to cap how many calls pile up behind one
    # long menu visit, which matters more the more people can fire it.
    Command(id="boso", action="boso_call",
            chat_prefix="!boso", min_role="subscriber",
            cooldown=5.0, user_cooldown=60.0, arg_names=["mood"]),

    Command(id="boso_raid", action="boso_call",
            on_event="raid", cooldown=30.0, fixed_args={"mood": "excited"}),
    Command(id="boso_sub", action="boso_call",
            on_event="sub", cooldown=30.0, fixed_args={"mood": "praise"}),
    Command(id="boso_cheer", action="boso_call",
            on_event="cheer", cooldown=60.0, fixed_args={"mood": "greet"}),
]

# Mood words Twitch_OnBosoCall understands. MIRRORS the $moods list in that cue —
# MD resolves the mood by string compare, so the two lists must stay identical
# (tools/test_commands.py fails if they drift). Anything else, including an empty
# arg, makes MD advance to the NEXT mood in this order rather than picking randomly.
BOSO_MOODS = ("greet", "praise", "excited", "angry", "threat", "worried", "alert")

# `!boso random` is deliberately NOT a mood. The moods above are hand-picked handfuls
# of lines chosen to fit an event; this draws from EVERY Boso Ta recording instead —
# all 1263 ids on his TextDB page 10201 that have real audio, generated into
# extensions/twitch_integration/md/twitch_boso_lines.xml by tools/gen_boso_lines.py.
# MD tests for this word before the mood lookup, so it must stay out of BOSO_MOODS
# (an unknown word there means "advance the cycle", which is not what this does).
# The pool has to live in MD: numbers don't marshal Lua->MD and MD can't convert the
# string it does get, so the bridge can only ever ask for a random line, not name one.
BOSO_RANDOM = "random"


# ---------------------------------------------------------------------------
# 2. Forward economy schema (doc 08) — single source of truth for engine + views
# ---------------------------------------------------------------------------

# Severity tier = the streamer's "experience dial" (doc 08 §5). Orthogonal to karma.
# -1 Debug is dev-only plumbing (test triggers), never part of the viewer economy.
TIERS = {-1: "Debug", 0: "Pure Interaction", 1: "Minor Distraction",
         2: "Major Distraction", 3: "Doom"}
# Reputation effect on the buyer's karma (doc 08 §3).
KARMA = ("good", "neutral", "bad", "doom")
# What the action does for the viewer: "info" answers in chat (bridge-side, e.g.
# !bal); "effect" changes the game (MD cue). Both show on the catalog page.
KINDS = ("info", "effect")
# Implementation status — the catalog doubles as the interactions roadmap, so every
# idea gets an entry the moment it exists; `status` tracks DEV progress (orthogonal
# to `enabled`, which is streamer config). tools/test_md_sync.py enforces that
# "live" matches what the MD script really implements (cue exists, TODO-free).
#   live      — works in the game now
#   wip       — being built (MD cue is a stub, or bridge wiring incomplete)
#   planned   — designed (the entry itself IS the design) but not started
#   suggested — community/viewer idea accepted into the list, not committed yet
STATUS = ("live", "wip", "planned", "suggested")

# --- arg domains: viewer-typed tokens the bridge canonicalises before X4 sees them ---
# "faction": the 14 diplomacy-capable NPC factions. This list MUST MIRROR $keys /
# $factions in the MD cue Twitch_OnFactionIncident (same ids, same spelling) — MD
# matches by string, so a key that isn't in both places silently falls back to a
# random faction. All 14 verified against vanilla libraries/factions.xml.
# `twitchally` is OUR faction (extensions/twitch_integration/libraries/factions.xml),
# not a vanilla one — it belongs here because its relations are deliberately NOT
# locked and it is not nodiplomacyselection, so it can be shoved around like any
# other faction. twitchfoe is excluded on purpose: its relation blocks ARE locked
# at -1, so an incident against it would be a no-op the viewer paid for.
FACTION_KEYS = ["argon", "antigone", "hatikvah", "teladi", "ministry", "paranid",
                "holyorder", "trinity", "alliance", "terran", "pioneers", "boron",
                "split", "freesplit", "twitchally"]
# Who the stance command can be pointed AT — everyone except the Twitch faction
# itself, since the stance is *between* twitchally and someone else.
STANCE_TARGETS = [k for k in FACTION_KEYS if k != "twitchally"]
# The three stances, weakest hostility first. These map to the game's own relation
# BANDS in MD (relation.ally/neutral/kill .mid), not to hardcoded numbers, so each
# faction's own thresholds decide what counts as allied or shoot-on-sight.
STANCE_KEYS = ["ally", "neutral", "war"]
STANCE_ALIASES = {
    "ally": "ally", "allied": "ally", "allies": "ally", "friend": "ally",
    "friendly": "ally", "peace": "ally", "love": "ally",
    "neutral": "neutral", "reset": "neutral", "calm": "neutral", "truce": "neutral",
    "ceasefire": "neutral", "nothing": "neutral",
    "war": "war", "enemy": "war", "enemies": "war", "hostile": "war", "kill": "war",
    "attack": "war", "hate": "war",
}


def resolve_stance(token: str) -> str | None:
    """A chat token -> ally | neutral | war, or None."""
    norm = "".join(c for c in (token or "").lower() if c.isalnum())
    return STANCE_ALIASES.get(norm)
# What chat actually types. Keys here are already normalised (lowercase, letters and
# digits only), so "Holy Order" / "HOP" / "hop" all land on the same entry.
FACTION_ALIASES = {
    "arg": "argon", "argonfederation": "argon", "argons": "argon",
    "ant": "antigone", "antigonerepublic": "antigone",
    "hat": "hatikvah", "hatikvahfreeleague": "hatikvah", "hfl": "hatikvah",
    "tel": "teladi", "teladicompany": "teladi", "teladis": "teladi",
    "min": "ministry", "mof": "ministry", "ministryoffinance": "ministry",
    "par": "paranid", "paranids": "paranid", "godrealm": "paranid",
    "godrealmoftheparanid": "paranid",
    "hop": "holyorder", "holyorderofthepontifex": "holyorder", "pontifex": "holyorder",
    "tri": "trinity", "trinitysanctum": "trinity",
    "ali": "alliance", "aow": "alliance", "allianceoftheword": "alliance",
    "ter": "terran", "terrans": "terran", "terranprotectorate": "terran",
    "pio": "pioneers", "segaris": "pioneers", "segarispioneers": "pioneers",
    "bor": "boron", "borons": "boron", "kingdomend": "boron",
    "zya": "split", "zyarth": "split", "zyarthpatriarchy": "split", "splits": "split",
    "twitch": "twitchally", "ally": "twitchally", "allies": "twitchally",
    "twitchallies": "twitchally", "chat": "twitchally", "us": "twitchally",
    "frf": "freesplit", "free": "freesplit", "freefamilies": "freesplit",
    "familes": "freesplit", "families": "freesplit",
}


def resolve_faction(token: str) -> str | None:
    """A chat token -> a canonical faction key MD understands, or None."""
    norm = "".join(c for c in token.lower() if c.isalnum())
    if norm in FACTION_KEYS:
        return norm
    return FACTION_ALIASES.get(norm)


@dataclass
class StoreEvent:
    """One purchasable/trigger-able thing — drives the engine AND the item-list."""

    # --- identity / runtime (drives the !buy engine; M4.0) ---
    id: str                          # internal action id = the MD cue X4 fires
    buy_key: str                     # the `!buy <key>` abbreviation (TT's "abr")
    nicknames: list[str] = field(default_factory=list)  # extra accepted keys (e.g. "sats")
    kind: str = "effect"             # info (chat answer) | effect (changes the game)

    # --- economy (doc 08 §3-4) ---
    cost: int = 0                    # fixed coin cost (0 + cost_per_unit => variable)
    cost_per_unit: int | None = None  # variable price = cost_per_unit * <unit arg>
    unit: str | None = None          # which arg scales the price, e.g. "qty"
    karma: str = "neutral"           # good | neutral | bad | doom (reputation effect)
    cooldown: float = 0.0            # per-event re-buy cooldown, seconds
    event_cap: int = 0               # max per rolling window (§3.1); 0 = uncapped
    min_role: str = "everyone"       # optional role floor on top of the coin cost

    # --- trigger (default: a `!buy <key>` purchase) ---
    on_event: str | None = None      # if set, fires on this event instead of !buy (raid/sub/…)
    reward: str | None = None        # for redeem-triggered: match this reward title
    args: list[str] = field(default_factory=list)  # named args parsed from the !buy line
    arg_domain: str | None = None    # canonicalise+validate every arg against a domain
                                     # before charging ("faction" => resolve_faction,
                                     # "sector" => sectors.resolve, which consumes the
                                     # WHOLE rest of the line since sector names are
                                     # multi-word and yields the sector's MACRO name).
                                     # Without this, a mistyped/capitalised name reaches
                                     # MD unmatched and silently becomes a random pick.
    distinct_args: bool = False      # reject a buy that repeats the same resolved value

    # --- display (drives the item-list view, doc 08 §10) ---
    label: str = ""                  # human name (defaults to buy_key)
    description: str = ""            # viewer-facing "what happens"
    category: str = "Misc"           # grouping in the list view
    tier: int = 0                    # -1 Debug / 0 Pure / 1 Minor / 2 Major / 3 Doom (§5)

    # --- lifecycle ---
    status: str = "planned"          # dev progress: live | wip | planned | suggested
    default_enabled: bool = True     # ships enabled? (Major/Doom default False)
    enabled: bool = True             # current streamer setting (runtime-overridable)
    ship_picker: bool = False        # True => "buy any ship" event: price + macro come
                                     # from the ships.py registry, not the fixed `cost`
    fleet_picker: bool = False       # True => "adopt a ship" event: the target is one of
                                     # the player's EXISTING ships (fleet.py roster) and
                                     # the price comes from that hull, not from `cost`
    price_note: str = ""             # shown in the COST column instead of `cost` when the
                                     # price is not a fixed number (per ship / per hull),
                                     # so a 0 there never reads as "free"

    @property
    def syntax(self) -> str:
        """The chat usage string shown in the item-list / help."""
        if self.on_event:
            return f"(auto on {self.on_event})"
        if self.kind == "info":      # direct chat command, not a purchase
            return " ".join([f"!{self.buy_key}"] + [f"<{a}>" for a in self.args])
        return " ".join(["!buy", self.buy_key] + [f"<{a}>" for a in self.args])

    @property
    def variable(self) -> bool:
        return self.cost_per_unit is not None

    @property
    def crisis(self) -> bool:
        """Does buying this need the streamer's "accept crisis level" consent?

        DERIVED from the tier rather than declared per event, so the two can never
        disagree: tier 3 IS the doom dial (TIERS above), and anything that earns
        that tier is by definition save-threatening. A new Doom entry is gated the
        moment it is written, with nothing to remember."""
        return self.tier >= 3

    def display(self) -> dict:
        """The item-list projection (doc 08 §10): what /catalog + the export emit.
        Display code consumes ONLY this dict, never the live object."""
        return {
            "buy_key": self.buy_key,
            "nicknames": self.nicknames,
            "kind": self.kind,
            "label": self.label or self.buy_key,
            "description": self.description,
            "category": self.category,
            "tier": self.tier,
            "tier_name": TIERS.get(self.tier, "?"),
            "karma": self.karma,
            "syntax": self.syntax,
            "cost": self.cost,
            "price_note": self.price_note,
            "cost_per_unit": self.cost_per_unit,
            "unit": self.unit,
            "cooldown": self.cooldown,
            "event_cap": self.event_cap,
            "status": self.status,
            "enabled": self.enabled,
            # Shown as its own badge on the item list: "enabled" alone would tell a
            # reader this is buyable right now, and a crisis event only is while the
            # streamer says so.
            "crisis": self.crisis,
        }


# A representative spread (NOT the full catalog — see doc 08 §5.1). Enough to pin
# the schema: fixed + variable cost, args, on_event triggers, all 4 tiers, karma,
# default-off destructive tiers. Costs are first-draft (doc 08 §5.1).
CATALOG: list[StoreEvent] = [
    # Tier -1 — Debug (dev-only plumbing; never part of the viewer economy) ---
    # `!buy test` -> id "spawn" -> the MD Twitch_OnSpawn cue (spawns 20 named
    # scouts). Priced at 1000 coins to exercise the wallet path. Remove once real
    # effects are wired.
    StoreEvent(id="spawn", buy_key="test", cost=1000, karma="neutral", tier=-1,
               category="Test", label="Test: spawn 20 ships", status="live",
               description="Spawns 20 player-owned scouts (Twitch 2..21) next to the player."),

    # Info — chat answers, implemented bridge-side in economy.py (no MD cue).
    # nicknames MUST mirror COMMAND_ALIASES there; tools/test_md_sync.py enforces it.
    StoreEvent(id="balance", buy_key="balance", nicknames=["bal", "coins", "money"],
               kind="info", tier=0, category="Info", status="live",
               label="Balance", description="Shows your coin balance and karma in chat."),
    StoreEvent(id="karma", buy_key="karma", nicknames=["whatiskarma", "rep"],
               kind="info", tier=0, category="Info", status="live",
               label="Karma", description="Explains karma and shows yours."),
    StoreEvent(id="shop", buy_key="shop",
               nicknames=["catalog", "store", "purchaselist", "instructions", "commands", "help"],
               kind="info", tier=0, category="Info", status="live",
               label="Shop", description="Lists what you can buy (this page)."),
    StoreEvent(id="sectors", buy_key="sectors", nicknames=["sector", "where", "map"],
               kind="info", tier=0, category="Info", status="live",
               label="Sectors", description="Explains how to aim a station at a sector, and "
               "looks a sector name up (e.g. !sectors grand)."),

    # Tier 0 — Pure Interaction (identity / flavour) ------------------------
    StoreEvent(id="name_ship", buy_key="nameship", cost=120, karma="neutral", tier=0,
               category="Identity", args=["name"],
               label="Name a ship", description="Rename one of the player's ships."),
    # Adoption claims an EXISTING ship out of the player's fleet, so there is no fixed
    # cost: fleet.py prices each hull from the same ships.json that prices `!buy ship`
    # (/1200 instead of /300 — a claim, not a purchase). `cost` stays 0 and unused;
    # fleet_picker is what routes it to the per-hull pricing path.
    StoreEvent(id="adopt_ship", buy_key="adopt", nicknames=["adoptship"],
               fleet_picker=True, karma="good", tier=0, cooldown=10,
               category="Identity", status="live", args=["idcode"], price_note="by hull",
               label="Adopt a ship", description="Claim one of the player's existing ships as "
               "yours — it gets renamed after you. Price scales with the hull: "
               "`!buy adopt` lists what's available with ID codes and prices, then "
               "`!buy adopt PSF-481`. ONE ship per viewer — !abandon yours before taking "
               "another. `!fleet` shows the list, `!myship` shows yours."),
    StoreEvent(id="fleet", buy_key="fleet", nicknames=["adoptable"],
               kind="info", tier=0, category="Info", status="live",
               label="Fleet", description="Lists the player's ships that are still up for "
               "adoption, with their ID codes and prices. Add a hull class to narrow it "
               "down: !fleet S (or M, L, XL) — handy when the cheapest ships crowd out "
               "the capitals."),
    StoreEvent(id="myship", buy_key="myship", nicknames=["myships"],
               kind="info", tier=0, category="Info", status="live",
               label="My ship", description="Shows which ship(s) you have adopted."),
    # `info` here means "a free top-level !command the bridge answers", which is what
    # this is — but unlike the other info entries it also reaches the game: MD reverts
    # the ship's name. Free and never refunded, so it can't be used to churn the
    # roster. Moderators can release anyone's ship; viewers only their own.
    StoreEvent(id="abandon_ship", buy_key="abandon", nicknames=["disown", "release"],
               kind="info", tier=0, category="Identity", status="live",
               label="Abandon a ship", description="Give up a ship you adopted: it goes "
               "back on the !fleet list and the game reverts its name. !abandon on its own "
               "if you hold one ship, !abandon <ID> otherwise. Free, and the coins you "
               "paid are not refunded."),
    # Charges coins, but it is a top-level !command rather than a !buy: you are not
    # picking something off a shelf, you are rebuilding a specific wreck you own.
    # Priced off the same hull value as adoption (fleet.RESURRECT_MULTIPLIER).
    StoreEvent(id="resurrect_ship", buy_key="resurrect", nicknames=["rebuild", "revive"],
               kind="info", tier=1, category="Identity", status="live",
               price_note="1.5x adopt",
               label="Resurrect a ship", description="Rebuild one of your adopted ships "
               "after it is destroyed. A replacement hull of the same type is laid down at "
               "the player's HQ and renamed back to you. Costs 1.5x what adopting that hull "
               "costs; wrecks keep indefinitely, so there is no rush."),

    # Tier 1 — Minor Distraction (survivable) -------------------------------
    # LIVE faction spawns (twitchfoe / twitchally). Buyable by ANYONE for coins —
    # the coin cost is the gate, not a role — so viewers, not just mods, drive them.
    # id must equal the MD cue's control ('pirate_attack' / 'reinforcements').
    StoreEvent(id="pirate_attack", buy_key="enemy", nicknames=["raiders", "attack"], cost=200,
               karma="bad", tier=1, cooldown=45, event_cap=5, category="Combat", status="live",
               label="Spawn Raiders", description="Summon a squad of hostile Twitch Raiders "
               "(the twitchfoe faction) that hunt the player."),

    StoreEvent(id="pirate_harass", buy_key="pirate", cost=180, karma="bad", tier=1,
               cooldown=120, event_cap=4, category="Combat",
               label="Pirate harassment", description="One S/M pirate jumps in to annoy the "
               "nearest player ship."),
    StoreEvent(id="ware_drop", buy_key="ware", cost_per_unit=2, unit="qty", karma="good", tier=1,
               args=["ware", "qty"], category="Gifts",
               label="Gift wares", description="Drop wares near the player; price scales with qty."),

    # LIVE — buy the PLAYER any warship, priced by that ship's in-game value. The
    # ship name + coin price + macro come from the ships.py registry (generated from
    # game data by tools/gen_ships.py); `!buy ship` with no name lists them. id must
    # equal the MD cue control ('gift_ship'); the bridge sends the chosen macro.
    StoreEvent(id="gift_ship", buy_key="ship", nicknames=["ships", "buyship"],
               args=["name"], ship_picker=True, price_note="by ship", karma="good", tier=1,
               cooldown=60, event_cap=5, category="Gifts", status="live",
               label="Gift a ship", description="Buy the player a ship (e.g. !buy ship nemesis, "
               "!buy ship katana). Price scales with the ship; '!buy ship' lists what's available. "
               "Spawns player-owned beside the player with a random loadout."),

    # Tier 2 — Major Distraction (a real moment; OFF by default) ------------
    StoreEvent(id="khaak_swarm", buy_key="khaak", cost=900, karma="bad", tier=2,
               cooldown=600, event_cap=2, default_enabled=False, enabled=False, category="Combat",
               label="Kha'ak swarm", description="A cluster of Kha'ak fighters jumps in and attacks."),

    # Tracker mines — LIVE. Six hostile Tracker Mines (the game's own
    # weapon_gen_mine_02_macro) materialise 700-1000m around the player, inside
    # their own 1km follow range, and home in. 10000 explosion damage each, but
    # 100 hull and an 80m trigger: shootable and dodgeable. They wipe themselves
    # after 10 minutes so repeat buys can't litter the sector permanently.
    # Tier 2, so default_enabled=False is the RECOMMENDATION — but it ships ON, for
    # the same reason faction_stance does: `enabled` has no runtime switch (the
    # dashboard toggles cooldowns and caps only), so enabled=False would mean "edit
    # this file before anyone can buy it". Set enabled=False here to pull it from the
    # store; the 240s cooldown and the cap of 3 are the live brakes.
    StoreEvent(id="mine_field", buy_key="mines", nicknames=["mine", "minefield", "trackermines"],
               cost=700, karma="bad", tier=2, cooldown=240, event_cap=3,
               default_enabled=False, category="Combat", status="live",
               label="Tracker Mines", description="Seed six hostile Tracker Mines around the "
               "player. They wake up, home in and detonate — shoot them or outrun them "
               "(they give up past 1.5km). Anything left over self-destructs in 10 minutes."),

    # Terran Task Force — LIVE, and the armada's opposite number: 22 hulls led by an
    # Asgard, staged 8-12km off the player (inside the armada's 14-20km, so the
    # cavalry lands on the near side), pointed at whatever the PLAYER is at war with.
    # Terran hulls, Twitch Allies flag — see the MD cue for why the real Terran
    # Protectorate is the wrong owner for a rescue.
    #
    # PRICED UNDER THE ARMADA (18000 vs 25000) DELIBERATELY. The counter has to be
    # affordable in the minutes after the doom lands, or it is decoration; and the
    # asymmetry means a chat that wants to save the run always can, while a chat that
    # wants to end it needs both more coins AND the streamer's consent. Tier 2, so it
    # is NOT crisis-gated — nothing here threatens the save.
    #
    # NEEDS CRADLE OF HUMANITY. Without the DLC the hull macros resolve to nothing,
    # MD reports the failure and the bridge refunds the buyer.
    StoreEvent(id="terran_taskforce", buy_key="terran",
               nicknames=["taskforce", "cavalry", "asgard", "atf", "rescue"],
               cost=18000, karma="good", tier=2, cooldown=1800, event_cap=1,
               default_enabled=False, category="Combat", status="live",
               label="Terran Task Force", description="An ATF battle group jumps in on the "
               "player's side: an Asgard, 2 Syn, 2 Osaka and 17 escorts, already hunting "
               "whatever the player is at war with. Built to beat the Xenon Armada. Survivors "
               "stay in the game. Needs the Cradle of Humanity DLC."),

    # Tier 3 — Doom (fleet/station-threatening; OFF, capped) ----------------
    StoreEvent(id="xenon_k", buy_key="xenonk", cost=6500, karma="doom", tier=3,
               cooldown=1800, event_cap=1, default_enabled=False, enabled=False, category="Doom",
               label="Xenon K", description="A Xenon K destroyer jumps into the player's sector."),

    # Xenon Armada — LIVE, and the heaviest thing in the shop: a Xenon I plus 21
    # escorts (3 K, 4 PE, 6 P, 8 fighters) stage 14-20km off the player and come in
    # as one fleet under the I. Unlike every other combat event, nothing here is
    # temporary — the survivors stay in the save.
    #
    # ANYONE CAN BUY IT — but only while the streamer has "accept crisis level"
    # ticked in the dashboard. That is what `tier=3` now means at runtime: every
    # Doom entry is gated on Runtime.crisis_enabled (see StoreEvent.crisis below),
    # which is off by default and resets every session. So `enabled=True` here is
    # honest — the event really is in the shop, browsable and priced — while the
    # decision to let 25000 coins end the save stays a live, one-click, revocable
    # call by the person flying the ship, instead of a source edit nobody makes.
    StoreEvent(id="xenon_armada", buy_key="armada",
               nicknames=["xenon", "invasion", "xenonarmada", "doom"],
               cost=25000, karma="doom", tier=3, cooldown=3600, event_cap=1,
               default_enabled=False, category="Doom", status="live",
               label="Xenon Armada", description="A Xenon I and 21 escorts jump in on the "
               "player and attack as one fleet. Nothing cleans them up afterwards — whatever "
               "survives stays in the game. CRISIS LEVEL: only buyable while the streamer "
               "has accepted crisis level in the companion."),

    # Buyable by anyone (!buy ally) AND auto-fires free on a raid (via STARTER). ---
    StoreEvent(id="reinforcements", buy_key="ally", nicknames=["allies", "reinforcements"],
               cost=120, karma="good", tier=1, cooldown=30, on_event="raid",
               category="Gifts", status="live",  # spawns a twitchally squad (MD)
               label="Spawn Allies", description="Summon a friendly Twitch Allies squad that "
               "joins your fleet (or patrols the sector). Also auto-fires on a raid."),

    # Diplomacy — LIVE. Buyable by anyone; hooks the game's faction-relation system.
    # Optional args name the two factions; omit for two random ones. The MD cue's
    # $byKey list MUST mirror these keys (extensions/twitch_integration md).
    StoreEvent(id="faction_incident", buy_key="incident", nicknames=["feud", "diplomacy"],
               args=["faction1", "faction2"], arg_domain="faction", distinct_args=True,
               cost=300, karma="neutral", tier=1,
               cooldown=45, category="Diplomacy", status="live",
               label="NPC Faction Incident",
               description="Sour relations between two NPC factions (uses the game's diplomacy "
               "system). Omit for two random, or name one or two of: " + ", ".join(FACTION_KEYS)
               + ". Short names work too (hop, zya, tel...). E.g. !buy incident argon paranid"),

    # The heavy version of the incident: instead of nudging a relation a little, it
    # SETS the Twitch faction's standing with someone to a named band. Tier 2 and
    # priced accordingly — flipping a major faction to war redraws the map the
    # player is flying through, and it is not self-reversing the way an incident is.
    # karma is neutral because the SAME event can be kind or vicious depending on the
    # stance argument, and karma is per-event, not per-argument.
    StoreEvent(id="faction_stance", buy_key="stance", nicknames=["twitchwar", "pact"],
               args=["faction", "stance"], arg_domain="faction_stance",
               cost=900, karma="neutral", tier=2, cooldown=120, event_cap=3,
               # Tier 2 RECOMMENDS shipping off (default_enabled=False, as the other
               # tier-2 entries do with enabled=False beside it). This one ships ON
               # anyway: there is no runtime switch for `enabled` — the dashboard only
               # toggles cooldowns and caps — so enabled=False would mean "edit this
               # file to use the feature at all". Set enabled=False here to pull it
               # from the store; the cooldown + event_cap are the live brakes.
               category="Diplomacy", status="live", default_enabled=False,
               label="Twitch Faction Stance",
               description="Set the Twitch Allies' standing with one NPC faction to "
               "ally, neutral or war — the game's own relation bands, so it really does "
               "make them shoot (or stop shooting). E.g. !buy stance paranid war, "
               "!buy stance teladi ally. Targets: " + ", ".join(STANCE_TARGETS) + "."),

    # Stations — LIVE. Build a COMPLETE station, in the player's sector or in any
    # other sector chat names: `!buy wharf`, `!buy defence argon prime`.
    #
    # OWNERSHIP. These are built for the TWITCH ALLIES faction by default — friendly,
    # they defend the sector and trade, but they are not free real estate on the
    # player's account. The streamer flips the default with the dashboard's
    # "Stations go to the player" switch, and a viewer can override either way for a
    # single buy by ending the line with `player` or `ally`. The two hostile entries
    # below have a FIXED owner and so declare no `owner` arg at all.
    #
    # ONE ENTRY PER STATION TYPE ON PURPOSE. A command carries exactly one string to
    # MD and MD cannot split it (no string ops at all), so of "which station" and
    # "which sector" only one can be the argument. The TYPE is therefore the command
    # itself — `id` is the MD cue's control, one cue per type — and the SECTOR is the
    # argument. arg_domain="sector" makes the bridge consume the whole rest of the
    # line ("argon prime") and send the sector's MACRO name, which is the only form
    # MD can turn back into a sector. Omit it and MD builds in player.sector.
    # Prices are steep next to ships (a gifted Nemesis is ~2000c): these are
    # permanent additions to the save, so caps and cooldowns are tight too.
    StoreEvent(id="station_defence", buy_key="defence", nicknames=["defense", "turrets", "fort"],
               args=["sector", "owner"], arg_domain="sector", cost=2500, karma="good", tier=1,
               cooldown=180, event_cap=3, category="Stations", status="live",
               label="Defence Platform", description="Build a fully armed defence "
               "platform. Goes to the Twitch Allies unless you end the line with `player`. E.g. !buy defence, !buy defence argon prime, !buy defence player."),
    StoreEvent(id="station_solar", buy_key="solar", nicknames=["powerplant", "spp", "energy"],
               args=["sector", "owner"], arg_domain="sector", cost=3000, karma="good", tier=1,
               cooldown=300, event_cap=2, category="Stations", status="live",
               label="Solar Power Plant", description="Build a working energy-cell "
               "factory, stocked and staffed. E.g. !buy solar, or !buy solar black hole sun iv." 
               " Built for the Twitch Allies; add `player` to the line to give it to the player instead."),
    StoreEvent(id="station_tradestation", buy_key="tradestation",
               nicknames=["tradehub", "tradingstation"],
               args=["sector", "owner"], arg_domain="sector", cost=4000, karma="good", tier=1,
               cooldown=300, event_cap=2, category="Stations", status="live",
               label="Trading Station", description="Build a trading station. "
               "E.g. !buy tradestation, or !buy tradestation antigone memorial." 
               " Built for the Twitch Allies; add `player` to the line to give it to the player instead."),
    StoreEvent(id="station_equipmentdock", buy_key="equipmentdock",
               nicknames=["eqdock", "equipdock"],
               args=["sector", "owner"], arg_domain="sector", cost=6000, karma="good", tier=1,
               cooldown=600, event_cap=1, category="Stations", status="live",
               label="Equipment Dock", description="Build an equipment dock for "
               "refits and repairs. E.g. !buy equipmentdock argon prime." 
               " Built for the Twitch Allies; add `player` to the line to give it to the player instead."),
    StoreEvent(id="station_wharf", buy_key="wharf",
               args=["sector", "owner"], arg_domain="sector", cost=9000, karma="good", tier=1,
               cooldown=600, event_cap=1, category="Stations", status="live",
               label="Wharf", description="Build a wharf (S/M ship construction). "
               "E.g. !buy wharf, or !buy wharf grand exchange iv." 
               " Built for the Twitch Allies; add `player` to the line to give it to the player instead."),
    StoreEvent(id="station_shipyard", buy_key="shipyard", nicknames=["yard"],
               args=["sector", "owner"], arg_domain="sector", cost=15000, karma="good", tier=1,
               cooldown=900, event_cap=1, category="Stations", status="live",
               label="Shipyard", description="Build a shipyard (L/XL ship "
               "construction) — the biggest gift in the shop. E.g. !buy shipyard." 
               " Built for the Twitch Allies; add `player` to the line to give it to the player instead."),

    # Hostile stations — permanent, so OFF by default like the other tier-2+ events.
    StoreEvent(id="station_piratebase", buy_key="piratebase",
               nicknames=["raiderden", "den", "pirates"],
               args=["sector"], arg_domain="sector", cost=5000, karma="bad", tier=2,
               cooldown=600, event_cap=1, default_enabled=False, enabled=False,
               category="Stations", status="live",
               label="Raider Den", description="Plant a hostile Twitch Raider base (the "
               "twitchfoe faction) in a sector. E.g. !buy piratebase argon prime."),
    StoreEvent(id="station_khaakhive", buy_key="khaakhive", nicknames=["hive"],
               args=["sector"], arg_domain="sector", cost=12000, karma="doom", tier=3,
               cooldown=3600, event_cap=1, default_enabled=False, enabled=False,
               category="Doom", status="live",
               label="Kha'ak Hive", description="Plant a Kha'ak hive in a sector. It stays. "
               "E.g. !buy hive, or !buy hive second contact ii flashpoint."),

    # Station interference — LIVE. These act on the station NEAREST the player in
    # the player's current sector; there is no argument, because "closest" is the
    # whole point (and MD cannot resolve a station from a chat-typed name anyway).
    # Both are tier 1: loud and disruptive, but neither destroys anything, and
    # disarm undoes itself. The disarm cooldown is deliberately LONGER than the 90s
    # the effect lasts — two overlapping disarms on one station leave two re-arm
    # timers running and the first re-arms it early (see the MD cue's KNOWN LIMIT).
    # Cooldown MUST stay above the MD re-arm delay (600s, Twitch_StationRearm): two
    # disarms on one station inside the window leave two timers and the first re-arms
    # it early. 660s gives a minute of headroom. Cost is up from the 90s version —
    # 10 minutes with a station's guns down is a real window, not a flicker.
    StoreEvent(id="station_disarm", buy_key="disarm", nicknames=["sabotage", "silence"],
               cost=600, karma="bad", tier=1, cooldown=660, event_cap=3,
               category="Sabotage", status="live",
               label="Disarm a station", description="Shut down every turret AND the defence "
               "drones on the station closest to the player for 10 minutes, then they come "
               "back online. Same window the base game gives a hacked turret panel. Works on "
               "anyone's station — including the player's."),
    StoreEvent(id="station_loot", buy_key="loot", nicknames=["hack", "plunder", "steal"],
               cost=300, karma="bad", tier=1, cooldown=90, event_cap=4,
               category="Sabotage", status="live",
               label="Hack a station", description="Hack the storage module on the station "
               "closest to the player — the same trick pirates use to plunder one. Its cargo "
               "bursts out as containers for anyone to scoop up."),

    # Suggested (community ideas accepted into the list; not committed) ------
    StoreEvent(id="vision", buy_key="vision", nicknames=["sats"], cost=300,
               karma="good", tier=1, category="Gifts", status="suggested",
               label="Vision", description="Deploy a ring of advanced satellites "
               "around the player's current sector."),
]


def catalog_view(events: list[StoreEvent] | None = None, enabled_only: bool = True) -> list[dict]:
    """The item-list projection served at `/catalog` and written by the export."""
    items = events if events is not None else CATALOG
    return [e.display() for e in items if e.enabled or not enabled_only]
