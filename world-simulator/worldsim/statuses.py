"""Declared statuses: player-announced national achievements ("Canadian
scientists unveil matter synthesis technology") and the varied, seeded-
random world reaction to them.

Design constraints (see project README / CLAUDE.md-equivalent discussion):
this stays fully deterministic -- no AI/LLM call, same seed replays
identically -- while still avoiding the two failure modes the feature was
built to fix: (1) a fixed keyword always producing the same effect, and
(2) a given rival always reacting the same way to the same trigger. Both
are solved the same way every other reaction in this codebase is solved:
score a menu of options against *current* world state (relation, relative
strength, personality, category fit) with a seeded RNG roll layered on
top, so the outcome depends on the game's actual history up to that point,
not just which keyword was typed.
"""
from __future__ import annotations

import random

from .models import World
from .orders import ACCESSION_RELATION_THRESHOLD, _enter_war, _shift_relations, absorb_nation

# ---------------------------------------------------------------------
# Personalities: a stable-per-game, deterministic trait assigned to every
# nation at world creation (see scenarios._assign_personality). Not a
# player-visible stat -- it colors *how* a nation tends to react, the same
# way real states have different institutional temperaments, without
# making any single trigger word deterministic on its own (relation state,
# category, and RNG all still move the outcome).
PERSONALITY_TYPES = (
    "opportunistic",
    "envious",
    "cautious",
    "idealistic",
    "isolationist",
    "aggressive",
)

# ---------------------------------------------------------------------
# The catalog of declarable statuses. Free-text triggered (see
# parser.py's STATUS_KEYWORDS derived from this table) -- no stat
# prerequisite, but the one-time payoff is modest and each status can only
# ever pay out once per nation (see declared_statuses idempotency in
# orders._resolve_declare_status), so it rewards flavorful play without
# being a repeatable stat-farm exploit.
#
# category drives which reactions the rest of the world leans toward (see
# CATEGORY_REACTION_AFFINITY below) -- a scientific/economic breakthrough
# invites petitions and imitation, a military one invites fear and arms
# races, an ideological one invites both fervent allies and outright
# condemnation.
STATUS_CATALOG = {
    "post_scarcity_economy": {
        "name": "a post-scarcity economy",
        "category": "economic",
        "keywords": ("post-scarcity", "post scarcity", "abundance economy", "eliminate scarcity", "end scarcity"),
        "economy": 10, "stability": 4, "opinion": 8, "military": 0,
    },
    "universal_basic_income": {
        "name": "universal basic income",
        "category": "economic",
        "keywords": ("universal basic income", "guaranteed income for everyone", "basic income for all"),
        "economy": 4, "stability": 5, "opinion": 9, "military": 0,
    },
    "resource_monopoly": {
        "name": "a global resource monopoly",
        "category": "economic",
        "keywords": ("resource monopoly", "corner the market", "control the world's resources", "monopolize global resources"),
        "economy": 9, "stability": 2, "opinion": 3, "military": 0,
    },
    "trade_dominance": {
        "name": "global trade dominance",
        "category": "economic",
        "keywords": ("trade dominance", "dominate world trade", "become the world's trading hub", "global trade empire"),
        "economy": 8, "stability": 3, "opinion": 4, "military": 0,
    },
    "currency_hegemony": {
        "name": "global currency hegemony",
        "category": "economic",
        "keywords": ("global reserve currency", "currency hegemony", "our currency becomes the world standard"),
        "economy": 8, "stability": 2, "opinion": 3, "military": 0,
    },
    "fusion_breakthrough": {
        "name": "commercial fusion power",
        "category": "scientific",
        "keywords": ("fusion breakthrough", "commercial fusion", "fusion power online", "cracked fusion"),
        "economy": 7, "stability": 3, "opinion": 6, "military": 1,
    },
    "ai_singularity": {
        "name": "a self-improving artificial general intelligence",
        "category": "scientific",
        "keywords": ("ai singularity", "artificial general intelligence", "self-improving ai", "the singularity"),
        "economy": 7, "stability": -2, "opinion": 3, "military": 2,
    },
    "space_program": {
        "name": "a mature independent space program",
        "category": "scientific",
        "keywords": ("space program", "moon landing", "orbital colony", "put a colony in orbit", "reach mars"),
        "economy": 4, "stability": 2, "opinion": 9, "military": 1,
    },
    "quantum_computing_breakthrough": {
        "name": "a working quantum computer",
        "category": "scientific",
        "keywords": ("quantum computing breakthrough", "working quantum computer", "quantum supremacy"),
        "economy": 5, "stability": 1, "opinion": 4, "military": 1,
    },
    "matter_synthesis": {
        "name": "matter synthesis technology",
        "category": "scientific",
        "keywords": ("matter synthesis", "synthesize matter", "molecular assembler", "replicator technology"),
        "economy": 9, "stability": 3, "opinion": 7, "military": 0,
    },
    "military_supremacy": {
        "name": "overwhelming conventional military supremacy",
        "category": "military",
        "keywords": ("military supremacy", "unmatched military", "strongest military on earth", "military dominance"),
        "economy": 0, "stability": 3, "opinion": 2, "military": 10,
    },
    "nuclear_deterrent": {
        "name": "a credible nuclear deterrent",
        "category": "military",
        "keywords": ("nuclear deterrent", "nuclear weapons program", "successful nuclear test", "go nuclear"),
        "economy": -2, "stability": 4, "opinion": -1, "military": 12,
    },
    "orbital_weapons_platform": {
        "name": "an orbital weapons platform",
        "category": "military",
        "keywords": ("orbital weapons platform", "weapons in orbit", "space-based weapons", "orbital strike capability"),
        "economy": -1, "stability": 1, "opinion": -3, "military": 11,
    },
    "elite_special_forces": {
        "name": "a world-renowned special forces corps",
        "category": "military",
        "keywords": ("elite special forces", "world class special forces", "best commandos in the world"),
        "economy": 0, "stability": 2, "opinion": 3, "military": 6,
    },
    "missile_defense_shield": {
        "name": "a comprehensive missile defense shield",
        "category": "military",
        "keywords": ("missile defense shield", "missile shield", "intercept any missile"),
        "economy": -1, "stability": 3, "opinion": 4, "military": 8,
    },
    "cultural_golden_age": {
        "name": "a cultural golden age",
        "category": "cultural",
        "keywords": ("cultural golden age", "golden age of culture", "cultural renaissance"),
        "economy": 3, "stability": 3, "opinion": 10, "military": 0,
    },
    "global_media_dominance": {
        "name": "global media and entertainment dominance",
        "category": "cultural",
        "keywords": ("global media dominance", "dominate world entertainment", "our films conquer the world"),
        "economy": 4, "stability": 1, "opinion": 6, "military": 0,
    },
    "education_revolution": {
        "name": "a world-leading education system",
        "category": "cultural",
        "keywords": ("education revolution", "best schools in the world", "world leading education"),
        "economy": 3, "stability": 4, "opinion": 8, "military": 0,
    },
    "olympic_glory": {
        "name": "unprecedented Olympic success",
        "category": "cultural",
        "keywords": ("olympic glory", "dominate the olympics", "sweep the olympics"),
        "economy": 1, "stability": 1, "opinion": 9, "military": 0,
    },
    "architectural_wonder": {
        "name": "a new architectural wonder of the world",
        "category": "cultural",
        "keywords": ("architectural wonder", "build a wonder of the world", "tallest building in the world"),
        "economy": 2, "stability": 2, "opinion": 7, "military": 0,
    },
    "democratic_beacon": {
        "name": "status as a beacon of democracy",
        "category": "ideological",
        "keywords": ("beacon of democracy", "model democracy for the world", "shining example of democracy"),
        "economy": 1, "stability": 3, "opinion": 8, "military": 0,
    },
    "revolutionary_vanguard": {
        "name": "leadership of a global revolutionary movement",
        "category": "ideological",
        "keywords": ("revolutionary vanguard", "export the revolution", "lead the world revolution"),
        "economy": -1, "stability": -2, "opinion": 7, "military": 2,
    },
    "religious_awakening": {
        "name": "a national religious awakening",
        "category": "ideological",
        "keywords": ("religious awakening", "spiritual revival", "national religious revival"),
        "economy": 0, "stability": 4, "opinion": 6, "military": 0,
    },
    "technocratic_utopia": {
        "name": "a technocratic model society",
        "category": "ideological",
        "keywords": ("technocratic utopia", "rule by technocrats", "government run by algorithms"),
        "economy": 3, "stability": -1, "opinion": 2, "military": 0,
    },
    "disease_cure": {
        "name": "a cure for a major global disease",
        "category": "environmental",
        "keywords": ("cure for cancer", "cure a global disease", "eradicate the disease", "medical breakthrough cures"),
        "economy": 3, "stability": 3, "opinion": 11, "military": 0,
    },
    "climate_solution": {
        "name": "a working large-scale climate solution",
        "category": "environmental",
        "keywords": ("climate solution", "reverse climate change", "solve global warming", "carbon capture breakthrough"),
        "economy": 2, "stability": 3, "opinion": 9, "military": 0,
    },
    "renewable_energy_transition": {
        "name": "a complete renewable energy transition",
        "category": "environmental",
        "keywords": ("renewable energy transition", "fully renewable grid", "100% renewable energy"),
        "economy": 5, "stability": 3, "opinion": 8, "military": 0,
    },
    "genetic_engineering_breakthrough": {
        "name": "a landmark genetic engineering breakthrough",
        "category": "environmental",
        "keywords": ("genetic engineering breakthrough", "gene editing breakthrough", "engineer the human genome"),
        "economy": 4, "stability": -1, "opinion": 2, "military": 0,
    },
}

# ---------------------------------------------------------------------
# Reaction archetypes and how likely each one is, by category and by the
# reacting nation's personality. Values are relative weights, not
# probabilities -- they're combined multiplicatively with a relation-based
# factor and per-turn RNG jitter (see react_to_declared_statuses), so no
# single table entry ever fully determines the outcome on its own.
REACTION_TYPES = (
    "petition_to_join",
    "attack_for_access",
    "pressure_for_access",
    "propose_alliance",
    "propose_trade_pact",
    "imitate_race",
    "condemn",
    "ignore",
)

CATEGORY_REACTION_AFFINITY = {
    "economic": {"petition_to_join": 3.0, "pressure_for_access": 2.5, "propose_trade_pact": 3.0, "imitate_race": 1.5, "attack_for_access": 1.0, "propose_alliance": 1.5, "condemn": 0.5, "ignore": 2.0},
    "scientific": {"petition_to_join": 2.5, "pressure_for_access": 2.5, "propose_trade_pact": 2.0, "imitate_race": 3.0, "attack_for_access": 1.5, "propose_alliance": 1.5, "condemn": 0.5, "ignore": 2.0},
    "military": {"petition_to_join": 1.0, "pressure_for_access": 1.0, "propose_trade_pact": 0.5, "imitate_race": 3.0, "attack_for_access": 2.0, "propose_alliance": 2.5, "condemn": 2.0, "ignore": 2.0},
    "cultural": {"petition_to_join": 2.0, "pressure_for_access": 0.5, "propose_trade_pact": 2.0, "imitate_race": 1.0, "attack_for_access": 0.3, "propose_alliance": 2.0, "condemn": 0.5, "ignore": 3.0},
    "ideological": {"petition_to_join": 1.5, "pressure_for_access": 0.5, "propose_trade_pact": 1.0, "imitate_race": 1.0, "attack_for_access": 1.0, "propose_alliance": 2.5, "condemn": 3.0, "ignore": 2.0},
    "environmental": {"petition_to_join": 2.0, "pressure_for_access": 1.5, "propose_trade_pact": 2.5, "imitate_race": 2.0, "attack_for_access": 0.5, "propose_alliance": 2.0, "condemn": 0.5, "ignore": 2.5},
}

PERSONALITY_REACTION_AFFINITY = {
    "opportunistic": {"petition_to_join": 2.5, "pressure_for_access": 1.5, "propose_trade_pact": 2.0, "propose_alliance": 2.0, "imitate_race": 1.0, "attack_for_access": 1.0, "condemn": 0.5, "ignore": 0.8},
    "envious": {"attack_for_access": 2.5, "pressure_for_access": 2.0, "condemn": 2.0, "petition_to_join": 0.5, "imitate_race": 1.5, "propose_trade_pact": 0.7, "propose_alliance": 0.7, "ignore": 1.0},
    "cautious": {"ignore": 2.5, "propose_trade_pact": 1.5, "pressure_for_access": 1.2, "petition_to_join": 0.8, "imitate_race": 1.0, "attack_for_access": 0.3, "propose_alliance": 1.0, "condemn": 0.8},
    "idealistic": {"petition_to_join": 2.5, "propose_alliance": 2.5, "condemn": 1.5, "propose_trade_pact": 1.5, "imitate_race": 1.0, "attack_for_access": 0.5, "pressure_for_access": 0.7, "ignore": 0.8},
    "isolationist": {"ignore": 3.5, "propose_trade_pact": 0.7, "pressure_for_access": 0.5, "petition_to_join": 0.5, "imitate_race": 0.8, "attack_for_access": 0.4, "propose_alliance": 0.4, "condemn": 0.6},
    "aggressive": {"attack_for_access": 2.5, "imitate_race": 2.0, "condemn": 1.5, "pressure_for_access": 1.2, "petition_to_join": 0.4, "propose_trade_pact": 0.6, "propose_alliance": 0.8, "ignore": 0.8},
}

# Rolled independently per (status, reactor) pair each turn until resolved
# -- so reactions trickle in unpredictably over subsequent turns rather
# than every rival responding in lockstep the instant the status is
# declared.
REACTION_ROLL_CHANCE = 0.12
# Once pressuring for access, a small chance each turn the pressured
# nation concedes a token technology/economy transfer -- representing
# forced access, not a punitive trade war (see impose_embargo for that).
ACCESS_CONCESSION_CHANCE = 0.06

# A rival voting to dissolve into the nation that just declared a status
# needs the same very-high mutual trust the rest of the game requires for
# any voluntary union (see propose_accession/invite_accession) -- a plain
# alliance (relation ~45) is nowhere near enough on its own, or every
# NATO-bloc status declaration would instantly steamroll several allies.
PETITION_RELATION_THRESHOLD = ACCESSION_RELATION_THRESHOLD
ATTACK_RELATION_THRESHOLD = -20.0

REACTION_MESSAGES = {
    "petition_to_join": (
        "Drawn by {n}'s achievement, {r} petitions to join {n} outright.",
        "{r}'s population votes to dissolve into {n}, hoping to share in {s}.",
    ),
    "attack_for_access": (
        "{r} declares war on {n}, determined to seize {s} by force.",
        "Unwilling to be left behind, {r} attacks {n} to claim {s} for itself.",
    ),
    "pressure_for_access": (
        "{r} pressures {n} for access to {s}, short of a full trade embargo.",
        "{r} demands {n} share {s}, applying diplomatic pressure without cutting off trade.",
    ),
    "propose_alliance": (
        "{r} seeks closer ties with {n}, hoping alliance brings access to {s}.",
        "{r} proposes an alliance with {n} in {s}'s wake.",
    ),
    "propose_trade_pact": (
        "{r} opens trade talks with {n}, eager for a share of {s}.",
        "{r} proposes a trade pact with {n}, hoping to benefit from {s}.",
    ),
    "imitate_race": (
        "{r} launches its own crash program, racing to match {n}'s {s}.",
        "Determined not to fall behind, {r} pours resources into matching {s}.",
    ),
    "condemn": (
        "{r} publicly condemns {n} over {s}.",
        "{r}'s government denounces {n}'s {s} as a threat to the world order.",
    ),
    "ignore": (),
}

IMITATE_SECTOR_BY_CATEGORY = {
    "scientific": "technology",
    "military": "industry",
    "economic": "services",
    "environmental": "energy_sector",
    "cultural": "services",
    "ideological": None,
}


def apply_declared_status(world: World, nation, status_id: str) -> None:
    """One-time effect of a nation successfully declaring a status.
    Idempotent per nation/status -- repeating the same announcement is
    flavor only after the first time (see orders._resolve_declare_status
    for the legality/idempotency check itself)."""
    status = STATUS_CATALOG[status_id]
    nation.economy += status["economy"]
    nation.stability += status["stability"]
    nation.public_opinion += status["opinion"]
    nation.military += status["military"]
    nation.clamp_stats()
    nation.declared_statuses.add(status_id)


def _weighted_choice(rng: random.Random, weights: dict) -> str:
    keys = list(weights.keys())
    total = sum(weights.values())
    roll = rng.random() * total
    upto = 0.0
    for k in keys:
        upto += weights[k]
        if roll <= upto:
            return k
    return keys[-1]


def react_to_declared_statuses(world: World, rng: random.Random) -> None:
    """Once per turn: every alive, non-background nation gets an
    independent, seeded chance to react to every currently active status
    any other nation holds. The specific reaction is a weighted draw over
    category affinity x personality affinity x current relation state --
    not a fixed lookup -- so the same status declared in two different
    games (or reacted to by two different rivals in the same game)
    plausibly plays out differently."""
    holders = [n for n in world.alive_nations() if n.declared_statuses]
    if not holders:
        return

    for holder in holders:
        for status_id in list(holder.declared_statuses):
            status = STATUS_CATALOG[status_id]
            for reactor in world.alive_nations():
                if reactor.id == holder.id or reactor.is_background:
                    continue
                key = f"{status_id}:{reactor.id}"
                if key in holder.status_reactions_done:
                    continue
                if rng.random() >= REACTION_ROLL_CHANCE:
                    continue

                relation = reactor.relation(holder.id)
                weights = dict(CATEGORY_REACTION_AFFINITY[status["category"]])
                personality_weights = PERSONALITY_REACTION_AFFINITY.get(reactor.personality, {})
                for k in weights:
                    weights[k] *= personality_weights.get(k, 1.0)

                # Relation state gates the extremes: a rival that's never
                # been warm to us doesn't suddenly vote to dissolve into
                # our country just because we're rich, and a rival that's
                # never been hostile doesn't suddenly invade over it.
                if relation < PETITION_RELATION_THRESHOLD:
                    weights["petition_to_join"] = 0.0
                if relation > ATTACK_RELATION_THRESHOLD:
                    weights["attack_for_access"] *= 0.15
                # A reactor already stronger than the holder has nothing to
                # gain from joining or attacking for access.
                if reactor.economy >= holder.economy and reactor.military >= holder.military:
                    weights["petition_to_join"] = 0.0
                    weights["attack_for_access"] *= 0.2

                # RNG jitter so identical inputs still don't always resolve
                # to the same archetype.
                for k in weights:
                    weights[k] *= rng.uniform(0.6, 1.4)

                reaction = _weighted_choice(rng, weights)
                holder.status_reactions_done.add(key)
                _apply_reaction(world, holder, reactor, status_id, status, reaction, rng)

    # Ongoing pressure campaigns: a small chance per turn the pressured
    # nation grants a token concession, ending that pressure.
    for reactor in world.alive_nations():
        if not reactor.access_pressure_against:
            continue
        for holder_id in list(reactor.access_pressure_against):
            holder = world.nations.get(holder_id)
            if holder is None or not holder.alive:
                reactor.access_pressure_against.discard(holder_id)
                continue
            if rng.random() >= ACCESS_CONCESSION_CHANCE:
                continue
            transfer = min(6.0, holder.economy * 0.05)
            holder.economy -= transfer
            reactor.economy += transfer
            holder.clamp_stats()
            reactor.clamp_stats()
            reactor.access_pressure_against.discard(holder_id)
            world.log(f"{holder.name} grants {reactor.name} limited access under sustained pressure.")


def _apply_reaction(world: World, holder, reactor, status_id: str, status: dict, reaction: str, rng: random.Random) -> None:
    sname = status["name"]
    if reaction == "ignore":
        return

    templates = REACTION_MESSAGES[reaction]
    message = rng.choice(templates).format(n=holder.name, r=reactor.name, s=sname)

    if reaction == "petition_to_join":
        world.log(message)
        absorb_nation(world, holder, reactor, peaceful=True)
        return

    if reaction == "attack_for_access":
        _shift_relations(reactor, holder, -30.0)
        _enter_war(world, reactor, holder)
        world.log(message)
        return

    if reaction == "pressure_for_access":
        reactor.access_pressure_against.add(holder.id)
        _shift_relations(reactor, holder, -8.0)
        world.log(message)
        return

    if reaction == "propose_alliance":
        reactor.alliances.add(holder.id)
        holder.alliances.add(reactor.id)
        _shift_relations(reactor, holder, 10.0)
        world.log(message)
        return

    if reaction == "propose_trade_pact":
        reactor.trade_pacts.add(holder.id)
        holder.trade_pacts.add(reactor.id)
        _shift_relations(reactor, holder, 5.0)
        world.log(message)
        return

    if reaction == "imitate_race":
        sector = IMITATE_SECTOR_BY_CATEGORY.get(status["category"])
        if sector:
            reactor.sectors[sector] = reactor.sectors.get(sector, 40.0) + 6.0
        else:
            reactor.military += 3.0
        reactor.clamp_stats()
        world.log(message)
        return

    if reaction == "condemn":
        _shift_relations(reactor, holder, -12.0)
        world.log(message)
        return
