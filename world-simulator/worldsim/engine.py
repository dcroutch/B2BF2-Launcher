"""Turn loop: gather orders, resolve them, apply passive effects, log events."""
from __future__ import annotations

import random
from typing import Callable, Optional

from .ai import choose_order
from .models import ELECTION_TERM_LENGTH, RESOURCE_TYPES, SECTOR_TYPES, Nation, World
from .orders import Order, absorb_nation, resolve_orders

WAR_STABILITY_DRAIN = 2.0
WAR_MILITARY_DRAIN = 1.5
COLLAPSE_STABILITY = 0.0

# A government (elected or not) needs at least this much public approval to
# survive a scheduled election.
ELECTION_WIN_OPINION_THRESHOLD = 50.0
# Parliamentary systems can be brought down between elections by a vote of
# no confidence, but only under genuinely extreme, sustained displeasure on
# both fronts -- a single bad turn shouldn't topple a government.
NO_CONFIDENCE_OPINION_THRESHOLD = 15.0
NO_CONFIDENCE_STABILITY_THRESHOLD = 25.0
# A new administration (AI nations only -- the player's game simply ends)
# takes office with a fresh, moderate approval rating rather than inheriting
# the outgoing government's unpopularity.
NEW_ADMINISTRATION_OPINION = 55.0

# (name, resource deltas, stability delta, public_opinion delta)
MINOR_EVENTS = (
    ("drought", {"food": -10}, -3, -2),
    ("bumper_harvest", {"food": 10}, 2, 2),
    ("oil_discovery", {"oil": 15}, 1, 3),
    ("rare_metals_strike", {"metals": 12}, 1, 2),
    ("tech_breakthrough", {"tech_components": 12}, 1, 3),
    ("civil_unrest", {}, -6, -8),
    ("cultural_festival", {}, 3, 4),
    ("corruption_scandal", {}, -2, -7),
)

# Global commodity market tuning.
MARKET_PRICE_ADJUST_RATE = 0.1
MARKET_PRICE_MIN, MARKET_PRICE_MAX = 0.5, 2.0
MARKET_ECONOMY_SENSITIVITY = 0.01

# Domestic fracturing: a nation governing badly enough, for long enough,
# risks part of itself breaking away into an independent rebel faction --
# a new, fully independent Nation the rest of the world (including the
# original) now has to deal with, not a scripted one-off event.
CIVIL_WAR_STABILITY_THRESHOLD = 15.0
CIVIL_WAR_OPINION_THRESHOLD = 20.0
CIVIL_WAR_CHANCE_PER_TURN = 0.12
CIVIL_WAR_SPLIT_FRACTION = 0.3
CIVIL_WAR_STABILITY_SHOCK = -10.0
CIVIL_WAR_OPINION_SHOCK = -5.0


def run_turn(world: World, player_orders: list[Order], rng: random.Random) -> None:
    """Advance the world by one turn.

    player_orders: orders already chosen by the human player this turn.
    AI nations have their orders generated here.
    """
    all_orders = list(player_orders)
    for nation in world.alive_nations():
        if nation.is_player:
            continue
        all_orders.append(choose_order(world, nation.id, rng))

    resolve_orders(world, all_orders)
    _apply_passive_effects(world, rng)
    _update_market_prices(world)
    _resolve_elections(world)
    _check_collapses(world)
    world.turn += 1


def _apply_passive_effects(world: World, rng: random.Random) -> None:
    alive = world.alive_nations()
    alive_ids = {n.id for n in alive}
    embargoers_by_target: dict = {}
    for nation in alive:
        for target_id in nation.embargoes_against:
            embargoers_by_target.setdefault(target_id, 0)
            embargoers_by_target[target_id] += 1

    for nation in alive:
        # War exhaustion.
        if nation.at_war_with:
            nation.stability -= WAR_STABILITY_DRAIN * len(nation.at_war_with)
            nation.military -= WAR_MILITARY_DRAIN * len(nation.at_war_with)
            nation.economy -= 1.0 * len(nation.at_war_with)
            nation.public_opinion -= 1.5 * len(nation.at_war_with)

        # Embargoes against this nation drain its economy.
        embargo_count = embargoers_by_target.get(nation.id, 0)
        nation.economy -= 1.5 * embargo_count
        nation.public_opinion -= 1.0 * embargo_count

        # Trade pacts give a small mutual boost.
        nation.economy += 0.5 * len(nation.trade_pacts & alive_ids)

        # Global commodity markets: a surplus of a scarce (high-price)
        # commodity is a windfall (net exporter); a deficit of a scarce
        # commodity is a squeeze (net importer) -- ties each nation's
        # economy to the same shared markets everyone else trades in.
        for r in RESOURCE_TYPES:
            surplus = nation.resources.get(r, 0.0) - 50.0
            price_pressure = world.market_prices.get(r, 1.0) - 1.0
            nation.economy += surplus * price_pressure * MARKET_ECONOMY_SENSITIVITY

        # Domestic sectors are a second, slower lever on economy: a nation
        # whose sectors are collectively above/below their baseline (40)
        # sees a small ongoing boost/drag, on top of economic_potential.
        avg_sector = sum(nation.sectors.get(s, 40.0) for s in SECTOR_TYPES) / len(SECTOR_TYPES)
        nation.economy += (avg_sector - 40.0) * 0.03

        # Economy drifts toward this nation's long-run potential (raised
        # permanently by sustained invest_economy orders). Without this,
        # trade/investment only ever push economy upward and every nation
        # eventually converges on the same global cap; the drift keeps
        # nations differentiated by how much they've actually built up.
        nation.economy += (nation.economic_potential - nation.economy) * 0.05

        # Public opinion drifts toward a target set by prosperity relative
        # to this nation's own potential (booming feels good, a bust feels
        # bad) and by overall stability.
        target_opinion = 50 + (nation.stability - 50) * 0.3 + (nation.economy - nation.economic_potential) * 0.3
        nation.public_opinion += (target_opinion - nation.public_opinion) * 0.05

        # Stability drifts toward a target based on prosperity *and* public
        # sentiment -- a nation can be objectively prosperous but still
        # destabilize if its own public has turned against it.
        target_stability = 40 + nation.economy * 0.3 + (nation.public_opinion - 50) * 0.15
        nation.stability += (target_stability - nation.stability) * 0.05

        # Relations slowly heal toward neutral over time (grudges fade)
        # unless the two nations are still actively at war.
        for other_id in list(nation.relations.keys()):
            if other_id in nation.at_war_with:
                continue
            nation.relations[other_id] += (0 - nation.relations[other_id]) * 0.02

        # Resources regenerate slowly if not embargoed.
        for r in nation.resources:
            nation.resources[r] += 1.0

        # A small seeded chance of a minor event.
        if rng.random() < 0.08:
            name, resource_deltas, stability_delta, opinion_delta = rng.choice(MINOR_EVENTS)
            nation.stability += stability_delta
            nation.public_opinion += opinion_delta
            for r, d in resource_deltas.items():
                nation.resources[r] = nation.resources.get(r, 0) + d
            world.log(f"{nation.name} experiences {name.replace('_', ' ')}.")

        nation.clamp_stats()
        _maybe_trigger_civil_war(world, nation, rng)


def _maybe_trigger_civil_war(world: World, nation, rng: random.Random) -> None:
    """A nation governing badly enough (very low stability *and* very low
    public opinion, at once) risks part of itself breaking away into an
    independent rebel faction -- domestic fracturing as a real, emergent
    consequence, not a scripted event. The rebels are a normal Nation from
    here on: they fight the parent, can sue for peace, ally with others,
    grow their own economy, or eventually even accede back."""
    if nation.stability >= CIVIL_WAR_STABILITY_THRESHOLD or nation.public_opinion >= CIVIL_WAR_OPINION_THRESHOLD:
        return
    if rng.random() >= CIVIL_WAR_CHANCE_PER_TURN:
        return

    rebels = Nation(
        id=f"{nation.id}_rebels_t{world.turn}",
        name=f"{nation.name} Rebel Faction",
        stability=40.0,
        military=nation.military * CIVIL_WAR_SPLIT_FRACTION,
        economy=nation.economy * CIVIL_WAR_SPLIT_FRACTION,
        public_opinion=50.0,
        government_type="authoritarian",
        election_due_turn=world.turn + ELECTION_TERM_LENGTH,
    )
    for r in nation.resources:
        rebels.resources[r] = nation.resources[r] * CIVIL_WAR_SPLIT_FRACTION
        nation.resources[r] *= 1 - CIVIL_WAR_SPLIT_FRACTION
    nation.military *= 1 - CIVIL_WAR_SPLIT_FRACTION
    nation.economy *= 1 - CIVIL_WAR_SPLIT_FRACTION
    nation.stability += CIVIL_WAR_STABILITY_SHOCK
    nation.public_opinion += CIVIL_WAR_OPINION_SHOCK

    rebels.at_war_with.add(nation.id)
    nation.at_war_with.add(rebels.id)
    rebels.clamp_stats()
    nation.clamp_stats()
    world.spawn_nation(rebels)
    world.log(f"{nation.name} fractures under the strain: a rebel faction breaks away and declares independence!")


def _update_market_prices(world: World) -> None:
    """Update each commodity's global relative price from total supply
    across every living nation -- scarcity drives price up, abundance
    drives it down, shared by the whole world, not per-nation."""
    alive = world.alive_nations()
    if not alive:
        return
    baseline_total = 50.0 * len(alive)
    for r in RESOURCE_TYPES:
        total_stock = sum(n.resources.get(r, 0.0) for n in alive)
        target_price = baseline_total / total_stock if total_stock > 0 else MARKET_PRICE_MAX
        target_price = max(MARKET_PRICE_MIN, min(MARKET_PRICE_MAX, target_price))
        current = world.market_prices.get(r, 1.0)
        world.market_prices[r] = current + (target_price - current) * MARKET_PRICE_ADJUST_RATE


def _resolve_elections(world: World) -> None:
    """Governments answer to their own domestic politics, independent of
    anything the player types about *other* nations (see parser.py's
    actor-lock guarantee -- nothing here can be triggered or skipped by
    input text; it runs purely off public_opinion/stability state)."""
    for nation in world.alive_nations():
        if nation.government_type == "authoritarian":
            continue  # no real elections to hold or lose
        if world.turn >= nation.election_due_turn:
            _hold_election(world, nation)
        elif (
            nation.government_type == "parliamentary"
            and nation.public_opinion < NO_CONFIDENCE_OPINION_THRESHOLD
            and nation.stability < NO_CONFIDENCE_STABILITY_THRESHOLD
        ):
            world.log(f"{nation.name}'s parliament passes a vote of no confidence, collapsing the government.")
            _oust_leader(world, nation)


def _hold_election(world: World, nation) -> None:
    if nation.public_opinion >= ELECTION_WIN_OPINION_THRESHOLD:
        nation.election_due_turn = world.turn + ELECTION_TERM_LENGTH
        nation.public_opinion = min(100.0, nation.public_opinion + 3.0)
        world.log(f"{nation.name} holds elections; the incumbent government is re-elected.")
    else:
        world.log(f"{nation.name} holds elections; the incumbent government is voted out of office.")
        _oust_leader(world, nation)


def _oust_leader(world: World, nation) -> None:
    if nation.is_player:
        # The player's leadership loses power outright -- this is checked
        # by game_status() as a distinct end state from a stability collapse.
        nation.in_power = False
    else:
        nation.public_opinion = NEW_ADMINISTRATION_OPINION
        nation.election_due_turn = world.turn + ELECTION_TERM_LENGTH
        world.log(f"A new administration takes power in {nation.name}.")


def _check_collapses(world: World) -> None:
    for nation in world.alive_nations():
        if nation.stability > COLLAPSE_STABILITY:
            continue

        if nation.at_war_with:
            # A nation that collapses while still at war doesn't just
            # vanish -- the strongest enemy still fighting it annexes the
            # wreckage. This is what makes sustained war a real, reachable
            # path to conquest rather than just attrition that fades away
            # once a nation happens to fall apart.
            conqueror_id = max(
                nation.at_war_with,
                key=lambda nid: world.nations[nid].military if nid in world.nations else -1.0,
            )
            conqueror = world.nations.get(conqueror_id)
            if conqueror is not None and conqueror.alive:
                absorb_nation(world, conqueror, nation, peaceful=False)
                world.log(f"{conqueror.name} annexes the collapsed {nation.name} amid war.")
                continue

        nation.alive = False
        world.purge_nation_references(nation.id)
        world.log(f"{nation.name} collapses into instability and exits the world stage.")


def game_status(world: World, player_id: str) -> Optional[str]:
    """Return 'win', 'loss', or None if the game should continue.

    There is no turn cap: the game runs indefinitely until the player
    loses (collapse, ousted from power/annexed), wins by eliminating
    every other nation, or the player voluntarily ends the session (see
    cli.py -- that's a UI-level choice, not a world-state outcome, so it
    isn't reported here as win/loss)."""
    player = world.nations[player_id]
    if not player.alive:
        return "loss"
    if not player.in_power:
        return "loss"
    alive = world.alive_nations()
    if len(alive) == 1 and alive[0].id == player_id:
        return "win"
    return None
