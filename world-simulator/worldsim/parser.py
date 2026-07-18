"""Deterministic free-text command parser -- no AI/LLM involved.

Accepts arbitrary player input, including erratic, chaotic, or wholly
unrealistic statements ("demand a refund of the Louisiana Purchase"), and
always returns a resolvable Order. Unrecognized intent falls back to the
`wildcard` order type (see worldsim/orders.py::_resolve_wildcard), which
still produces a deterministic, in-world reaction via a fixed sentiment
word list -- input is never silently dropped and never crashes the game.

Hard safety guarantee: every Order this module returns has
`actor_id == player_id`. There is no code path here that can construct an
Order for a different nation, no matter what the input text says --
"make China declare war on Russia" cannot actually command China. If the
text's apparent subject is a nation other than the player, the whole
statement is downgraded to a wildcard rhetorical gesture *by the player*
about that nation, never an order carried out *by* that nation. This
applies just as much to declarative "fact" statements about another
nation ("With a vote of 85%, Canada instituted a communist government")
as it does to commands.

The player's *own* nation is a different story: "With a vote of 85% of
the population, Canada enacts a communist government" issued while
playing as Canada is a legitimate self-directed action and does change
Canada's government -- the claimed vote share is just flavor text, never
parsed or used to set public_opinion/stability directly; the same fixed
coup/liberalization consequences apply regardless of what percentage the
player claims.
"""
from __future__ import annotations

import re

from .models import SECTOR_TYPES, World
from .orders import Order, TARGETED_ORDERS


def _find(lowered: str, phrase: str) -> int:
    """Word-boundary search so short keywords like "fund" don't false-match
    inside unrelated words like "refund". Returns the match start index, or
    -1 if not found."""
    match = re.search(r"\b" + re.escape(phrase) + r"\b", lowered)
    return match.start() if match else -1

# (order_type, keywords) -- checked in this fixed priority order, most
# specific/unambiguous verbs first, so "trade war" doesn't accidentally
# match plain "war" before "trade" is considered, etc.
VERB_RULES = (
    ("sue_for_peace", ("sue for peace", "cease fire", "ceasefire", "end the war", "make peace", "stop the war", "surrender")),
    ("declare_war", ("declare war", "invade", "attack", "wage war", "go to war", "bomb", "conquer")),
    ("impose_embargo", ("embargo", "sanction", "blockade", "boycott")),
    ("break_alliance", ("break alliance", "break our alliance", "betray", "abandon our alliance", "end alliance", "end our alliance")),
    ("propose_alliance", ("alliance", "ally with", "mutual defense", "defense pact")),
    ("trade_pact", ("trade deal", "trade pact", "trade agreement", "free trade")),
    ("improve_relations", ("improve relations", "diplomacy", "reach out", "extend friendship", "make friends", "apologize")),
    ("build_military", ("build military", "build up the military", "rearm", "mobilize", "increase defense spending", "build army")),
    (
        "modify_constitution",
        (
            "new constitution", "rewrite the constitution", "constitution",
            "abolish democracy", "impose authoritarian rule", "declare martial law",
            "coup", "one-party rule", "seize absolute power", "become a dictatorship",
            "restore democracy", "restore parliament", "restore parliamentary",
            "become a democracy", "transition to democracy", "hold free elections",
            # Generic regime-change verbs -- only actually change the
            # government if _find_government below also recognizes a
            # specific government-type word somewhere in the text;
            # otherwise this falls back to a wildcard, so adding these
            # broad verbs can't misfire into an unintended government
            # change (see parse_command's matched_type == "modify_constitution"
            # branch).
            "enacts a", "establishes a", "installs a", "institutes a",
            "declares itself a", "becomes a",
        ),
    ),
    ("invest_sector", ("invest in", "boost", "develop", "fund", "grow the", "subsidize")),
    ("invest_economy", ("invest", "stimulate", "economic stimulus", "grow the economy")),
    ("pass", ("do nothing", "wait", "hold position", "stand down")),
)

# Maps keywords about a *form of government* to a GOVERNMENT_TYPES value,
# used only to fill in modify_constitution's detail -- never to look up or
# change any nation other than the actor (that order has no target_id).
GOVERNMENT_ALIASES = {
    "communist": "authoritarian", "communism": "authoritarian",
    "fascist": "authoritarian", "fascism": "authoritarian",
    "dictatorship": "authoritarian", "dictator": "authoritarian",
    "authoritarian": "authoritarian", "one-party": "authoritarian",
    "one party": "authoritarian", "autocracy": "authoritarian",
    "martial law": "authoritarian", "junta": "authoritarian",
    "democracy": "democracy", "democratic": "democracy", "republic": "democracy",
    "parliament": "parliamentary", "parliamentary": "parliamentary",
}

SECTOR_ALIASES = {
    "agriculture": "agriculture", "farm": "agriculture", "farming": "agriculture",
    "industry": "industry", "manufacturing": "industry", "factories": "industry",
    "energy": "energy_sector", "power": "energy_sector", "energy sector": "energy_sector",
    "technology": "technology", "tech": "technology", "innovation": "technology",
    "services": "services", "finance": "services", "banking": "services",
}

NATION_ALIASES = {
    "usa": ("usa", "united states", "america", "u.s.", "us"),
    "uk": ("uk", "united kingdom", "britain", "england", "u.k."),
    "south_korea": ("south korea", "korea"),
    "saudi_arabia": ("saudi arabia", "saudis", "saudi"),
    "south_africa": ("south africa",),
}


def _nation_lookup(world: World) -> dict:
    """alias (lowercase) -> nation_id, for every alive nation."""
    lookup = {}
    for nation in world.alive_nations():
        lookup[nation.name.lower()] = nation.id
        lookup[nation.id.replace("_", " ")] = nation.id
        for alias in NATION_ALIASES.get(nation.id, ()):
            lookup[alias] = nation.id
    return lookup


def _find_sector(lowered: str) -> str:
    for alias, sector in SECTOR_ALIASES.items():
        if _find(lowered, alias) != -1:
            return sector
    return None


def _find_government(lowered: str) -> str:
    for alias, government_type in GOVERNMENT_ALIASES.items():
        if _find(lowered, alias) != -1:
            return government_type
    return None


def parse_command(world: World, player_id: str, text: str) -> Order:
    """Turn free-text player input into a resolvable Order for player_id.

    Always returns Order(actor_id=player_id, ...) -- see module docstring.
    """
    lowered = text.lower()
    nation_lookup = _nation_lookup(world)

    earliest_id, earliest_pos = None, None
    target_id, target_pos = None, None
    for alias, nid in nation_lookup.items():
        idx = _find(lowered, alias)
        if idx == -1:
            continue
        if earliest_pos is None or idx < earliest_pos:
            earliest_id, earliest_pos = nid, idx
        if nid != player_id and (target_pos is None or idx < target_pos):
            target_id, target_pos = nid, idx

    matched_type, verb_pos = None, None
    for order_type, keywords in VERB_RULES:
        for kw in keywords:
            idx = _find(lowered, kw)
            if idx != -1:
                matched_type, verb_pos = order_type, idx
                break
        if matched_type:
            break

    # Guard rail: the text's apparent subject is a nation other than the
    # player, mentioned before any recognized verb (e.g. "China declares
    # war on Russia", "Have Germany invade Poland"). The player cannot
    # issue orders for another nation, so this can never become a real
    # declare_war/embargo/etc. -- it's downgraded to the player making a
    # (rhetorical, wildcard) statement about that nation instead.
    if earliest_id is not None and earliest_id != player_id and (verb_pos is None or earliest_pos < verb_pos):
        wildcard_target = target_id if target_id != earliest_id else earliest_id
        return Order(player_id, "wildcard", target_id=wildcard_target, detail=text)

    if matched_type == "invest_sector":
        sector = _find_sector(lowered)
        if sector is None:
            matched_type = "invest_economy"

    if matched_type == "modify_constitution":
        government_type = _find_government(lowered)
        if government_type is None:
            # Recognized "constitution"/"coup"-flavored language but
            # couldn't tell which form of government was intended --
            # resolve as a wildcard rather than guessing.
            return Order(player_id, "wildcard", target_id=target_id, detail=text)
        return Order(player_id, "modify_constitution", detail=government_type)

    if matched_type is None:
        # No recognized verb at all: highly unusual/chaotic/unrealistic
        # input (or just nonsense) still resolves, via the wildcard path.
        return Order(player_id, "wildcard", target_id=target_id, detail=text)

    if matched_type == "invest_sector":
        return Order(player_id, "invest_sector", detail=_find_sector(lowered))

    if matched_type in TARGETED_ORDERS:
        if target_id is None:
            # Recognized a hostile/friendly verb but no valid target nation
            # was named -- still resolve as a wildcard gesture rather than
            # silently discarding the turn.
            return Order(player_id, "wildcard", target_id=None, detail=text)
        return Order(player_id, matched_type, target_id)

    return Order(player_id, matched_type)
