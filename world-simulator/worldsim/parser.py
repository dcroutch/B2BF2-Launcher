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
from .scenarios import BACKGROUND_NATION_ALIASES


def _find(lowered: str, phrase: str) -> int:
    """Word-boundary search so short keywords like "fund" don't false-match
    inside unrelated words like "refund". Returns the match start index, or
    -1 if not found."""
    match = re.search(r"\b" + re.escape(phrase) + r"\b", lowered)
    return match.start() if match else -1


_IRREGULAR_INFLECTIONS = {
    "go": ("go", "goes", "went", "going"),
    "become": ("become", "becomes", "became", "becoming"),
    "hold": ("hold", "holds", "held", "holding"),
}


def _inflections(word: str) -> set[str]:
    """All the inflected forms of `word` a player might plausibly type
    ("embargo" -> "embargoes"/"embargoed"/"embargoing", etc.), so a keyword
    list built around bare infinitives ("embargo", "invade") still matches
    ordinary conjugated phrasing ("China embargoes Russia") instead of
    silently falling through to a vague wildcard just because the player
    used a normal tense."""
    if word in _IRREGULAR_INFLECTIONS:
        return set(_IRREGULAR_INFLECTIONS[word])
    variants = {word, word + "s", word + "es"}
    if word.endswith("e"):
        variants.add(word + "d")
        variants.add(word[:-1] + "ing")
    else:
        variants.add(word + "ed")
        variants.add(word + "ing")
    if word.endswith("y") and len(word) > 1 and word[-2] not in "aeiou":
        variants.add(word[:-1] + "ies")
        variants.add(word[:-1] + "ied")
    return variants


def _find_verb(lowered: str, phrase: str) -> int:
    """Like _find, but tolerant of the phrase's leading verb being
    conjugated -- "embargo Russia" still recognizes "embargoes Russia" /
    "embargoed Russia" / "embargoing Russia", since the keyword lists are
    written as bare infinitives but players naturally type normal tenses."""
    head, _, rest = phrase.partition(" ")
    rest = f" {rest}" if rest else ""
    best = -1
    for variant in _inflections(head):
        idx = _find(lowered, variant + rest)
        if idx != -1 and (best == -1 or idx < best):
            best = idx
    return best


def _find_non_possessive(lowered: str, phrase: str) -> int:
    """Like _find, but returns the earliest occurrence of `phrase` that
    isn't a possessive mention ("Germany's collapse"). A plain first-match
    _find would stop at that possessive occurrence and never see a later,
    legitimate one -- e.g. "Following France's defeat, France surrenders"
    has France named twice; only the second is the sentence's real
    subject, and a nation mentioned only possessively must never count as
    one purely because an earlier, unrelated possessive of the same name
    happened to come first in the text."""
    pattern = re.compile(r"\b" + re.escape(phrase) + r"\b")
    for match in pattern.finditer(lowered):
        idx = match.start()
        after = lowered[match.end():match.end() + 2]
        if after in ("'s", "’s"):
            continue
        return idx
    return -1

# (order_type, keywords) -- checked in this fixed priority order, most
# specific/unambiguous verbs first, so "trade war" doesn't accidentally
# match plain "war" before "trade" is considered, etc.
VERB_RULES = (
    ("annex", ("annex", "absorb", "annexation")),
    ("propose_accession", ("vote to join", "accede to", "join the union", "unite with", "merge into", "petition to join")),
    ("sue_for_peace", ("sue for peace", "cease fire", "ceasefire", "end the war", "make peace", "stop the war", "surrender", "surrenders", "surrendered")),
    ("declare_war", ("declare war", "invade", "attack", "wage war", "go to war", "bomb", "conquer")),
    ("impose_embargo", ("embargo", "sanction", "blockade", "boycott", "surround", "encircle", "cut ties", "stop buying", "stop trading", "cut off trade")),
    ("break_alliance", ("break alliance", "break our alliance", "betray", "abandon our alliance", "end alliance", "end our alliance")),
    ("propose_alliance", ("alliance", "ally with", "mutual defense", "defense pact", "team up with", "join forces with")),
    ("trade_pact", ("trade deal", "trade pact", "trade agreement", "free trade", "trade with")),
    ("invite_accession", ("invite", "to join us", "join our union", "join our nation", "come join us", "into our union", "part of our nation", "part of our union")),
    ("improve_relations", ("improve relations", "diplomacy", "reach out", "extend friendship", "make friends", "be friends with", "apologize")),
    ("build_military", ("build military", "build up the military", "rearm", "mobilize", "increase defense spending", "build army", "on the military", "on the army", "military spending", "fund the military", "boost the military", "boost the army", "beef up the military", "beef up the army")),
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
            "enact a", "establish a", "install a", "institute a",
            "declare itself a", "become a",
        ),
    ),
    ("invest_sector", ("invest in", "boost", "develop", "fund", "grow the", "subsidize", "improve", "upgrade", "modernize")),
    ("invest_economy", ("invest", "stimulate", "economic stimulus", "grow the economy")),
    ("pass", ("pass", "do nothing", "not do anything", "nothing this month", "nothing this turn", "wait", "hold position", "stand down", "sit tight", "stand by")),
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
    **BACKGROUND_NATION_ALIASES,
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
        # A possessive mention ("Germany's collapse") is a modifier, not
        # the sentence's subject or its intended target -- counting it as
        # either silently mangles a legitimate order (e.g. "Following
        # Germany's collapse, we annex Poland" both tripping the
        # impersonation guard on "Germany" *and* picking Germany, not
        # Poland, as the annex target). Skip past it to find this alias's
        # earliest non-possessive occurrence, if any, since a name used
        # possessively once elsewhere in the text doesn't mean every
        # occurrence of it is -- see "Following France's defeat, France
        # surrenders", where the second "France" is the real subject.
        idx = _find_non_possessive(lowered, alias)
        if idx == -1:
            continue
        if earliest_pos is None or idx < earliest_pos:
            earliest_id, earliest_pos = nid, idx
        if nid != player_id and (target_pos is None or idx < target_pos):
            target_id, target_pos = nid, idx

    matched_type, verb_pos = None, None
    for order_type, keywords in VERB_RULES:
        # Take the earliest-occurring keyword in the text, not just
        # whichever one happens to be listed first -- otherwise a keyword
        # list order like ("embargo", "blockade", "surround") can match on
        # "blockade" later in the sentence even when "surround" appears
        # right next to the actual target earlier, wrongly placing the
        # verb after the nation mention and tripping the actor-lock guard.
        best_idx = None
        for kw in keywords:
            idx = _find_verb(lowered, kw)
            if idx != -1 and (best_idx is None or idx < best_idx):
                best_idx = idx
        if best_idx is not None:
            matched_type, verb_pos = order_type, best_idx
            break

    # Guard rail: the text's apparent subject is a nation other than the
    # player, mentioned before any recognized verb (e.g. "China declares
    # war on Russia", "Have Germany invade Poland"). The player cannot
    # issue orders for another nation, so this can never become a real
    # declare_war/embargo/etc. -- it's downgraded to the player making a
    # (rhetorical, wildcard) statement about that nation instead.
    if earliest_id is not None and earliest_id != player_id and (verb_pos is None or earliest_pos < verb_pos):
        # earliest_id is already guaranteed to be the same nation target_id
        # holds here: target_id tracks the earliest non-player mention, and
        # earliest_id (non-player, per the condition above) is by
        # definition the earliest mention overall -- so it's always also
        # the earliest non-player one.
        return Order(player_id, "wildcard", target_id=earliest_id, detail=text)

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


# How multiple distinct instructions in one submission are separated --
# newlines, semicolons, or the connector "and then" -- deliberately not a
# bare "and", since that's also ordinary English inside a single action
# ("surround Russia and institute a blockade" is one action, not two).
_MULTI_INSTRUCTION_SPLIT = re.compile(r"[\n;]+|\band then\b", re.IGNORECASE)

# A player queuing up a whole paragraph of "instructions" in one submission
# is a mistake, not intent -- cap how many distinct orders one call to
# parse_commands can produce for the same turn.
MAX_ORDERS_PER_SUBMISSION = 6


def parse_commands(world: World, player_id: str, text: str) -> list[Order]:
    """Split free text into one or more separate instructions for the same
    turn (e.g. "invest in energy; embargo Russia") and parse each with
    parse_command. A single-instruction submission still goes through this
    same path and returns a one-element list -- there's no separate
    special case for it."""
    parts = [p.strip() for p in _MULTI_INSTRUCTION_SPLIT.split(text) if p.strip()]
    if not parts:
        return [Order(player_id, "pass")]
    return [parse_command(world, player_id, p) for p in parts[:MAX_ORDERS_PER_SUBMISSION]]
