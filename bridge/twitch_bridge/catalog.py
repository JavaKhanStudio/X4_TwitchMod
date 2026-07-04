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
]


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
            "cost_per_unit": self.cost_per_unit,
            "unit": self.unit,
            "cooldown": self.cooldown,
            "event_cap": self.event_cap,
            "status": self.status,
            "enabled": self.enabled,
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

    # Tier 0 — Pure Interaction (identity / flavour) ------------------------
    StoreEvent(id="name_ship", buy_key="nameship", cost=120, karma="neutral", tier=0,
               category="Identity", args=["name"],
               label="Name a ship", description="Rename one of the player's ships."),
    StoreEvent(id="adopt_ship", buy_key="adoptship", cost=200, karma="good", tier=0,
               category="Identity",
               label="Adopt a ship", description="A player ship is tagged as yours; chat is "
               "pinged when it scores a kill or dies."),

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
               args=["name"], ship_picker=True, karma="good", tier=1,
               cooldown=60, event_cap=5, category="Gifts", status="live",
               label="Gift a ship", description="Buy the player a ship (e.g. !buy ship nemesis, "
               "!buy ship katana). Price scales with the ship; '!buy ship' lists what's available. "
               "Spawns player-owned beside the player with a random loadout."),

    # Tier 2 — Major Distraction (a real moment; OFF by default) ------------
    StoreEvent(id="khaak_swarm", buy_key="khaak", cost=900, karma="bad", tier=2,
               cooldown=600, event_cap=2, default_enabled=False, enabled=False, category="Combat",
               label="Kha'ak swarm", description="A cluster of Kha'ak fighters jumps in and attacks."),

    # Tier 3 — Doom (fleet/station-threatening; OFF, capped) ----------------
    StoreEvent(id="xenon_k", buy_key="xenonk", cost=6500, karma="doom", tier=3,
               cooldown=1800, event_cap=1, default_enabled=False, enabled=False, category="Doom",
               label="Xenon K", description="A Xenon K destroyer jumps into the player's sector."),

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
               args=["faction1", "faction2"], cost=300, karma="neutral", tier=1,
               cooldown=45, category="Diplomacy", status="live",
               label="NPC Faction Incident",
               description="Sour relations between two NPC factions (uses the game's diplomacy "
               "system). Omit for two random, or name one or two of: argon, antigone, hatikvah, "
               "teladi, ministry, paranid, holyorder, trinity, alliance, terran, pioneers, boron, "
               "split, freesplit. E.g. !buy incident argon paranid"),

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
