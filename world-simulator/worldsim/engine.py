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

# Minor events are not a flat, context-free coin flip: their magnitude is
# randomized within a range (so the "same" event never plays out
# identically twice, even in an otherwise-identical replay), and unrest-
# flavored events are only ever *eligible* when the nation's own domestic
# stats -- the product of the choices that got it there -- have already
# degraded. A stable, well-governed nation cannot randomly suffer civil
# unrest or a corruption scandal; it has to actually be struggling first.
#
# (name, resource-delta ranges, stability-delta range, opinion-delta range)
POSITIVE_EVENTS = (
    ("bumper_harvest", {"food": (5.0, 15.0)}, (1.0, 4.0), (1.0, 4.0)),
    ("oil_discovery", {"oil": (8.0, 20.0)}, (0.0, 2.0), (1.0, 4.0)),
    ("rare_metals_strike", {"metals": (6.0, 16.0)}, (0.0, 2.0), (1.0, 3.0)),
    ("tech_breakthrough", {"tech_components": (6.0, 16.0)}, (0.0, 2.0), (1.0, 4.0)),
    ("cultural_festival", {}, (1.0, 4.0), (2.0, 5.0)),
)
# A weather/supply shock that can strike any nation regardless of how well
# it's governed -- unlike civil unrest, this isn't a verdict on domestic
# management.
NEUTRAL_EVENTS = (
    ("drought", {"food": (-15.0, -5.0)}, (-4.0, -1.0), (-3.0, -1.0)),
)
# Only rolled when the nation is already domestically struggling (see
# UNREST_STABILITY_THRESHOLD / UNREST_OPINION_THRESHOLD below).
UNREST_EVENTS = (
    ("civil_unrest", {}, (-9.0, -4.0), (-11.0, -5.0)),
    ("corruption_scandal", {}, (-4.0, -1.0), (-10.0, -4.0)),
)

BASE_EVENT_CHANCE = 0.06
# A nation already in domestic trouble is more turbulent generally, not
# just eligible for worse outcomes -- more is happening, good or bad.
STRUGGLING_EVENT_CHANCE_BONUS = 0.05
UNREST_STABILITY_THRESHOLD = 40.0
UNREST_OPINION_THRESHOLD = 40.0

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
        # Background nations are real, addressable targets but never take
        # their own AI-chosen actions -- see Nation.is_background.
        if nation.is_player or nation.is_background:
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
        nation.economy += (avg_sector - 40.0) * 0.08

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

        _maybe_trigger_minor_event(world, nation, rng)

        nation.clamp_stats()
        _maybe_trigger_civil_war(world, nation, rng)


def _maybe_trigger_minor_event(world: World, nation, rng: random.Random) -> None:
    """Roll for a minor event. Whether the nation is even eligible for
    unrest-flavored outcomes -- and how likely an event is at all -- both
    depend on its current domestic stats, which are themselves a product
    of the choices (player or AI) that led here. Magnitudes are sampled
    from a range rather than fixed, so no two occurrences of "the same"
    event play out identically."""
    struggling = nation.stability < UNREST_STABILITY_THRESHOLD or nation.public_opinion < UNREST_OPINION_THRESHOLD
    chance = BASE_EVENT_CHANCE + (STRUGGLING_EVENT_CHANCE_BONUS if struggling else 0.0)
    if rng.random() >= chance:
        return

    pool = list(POSITIVE_EVENTS) + list(NEUTRAL_EVENTS)
    if struggling:
        pool += list(UNREST_EVENTS)
    name, resource_ranges, stability_range, opinion_range = rng.choice(pool)

    nation.stability += rng.uniform(*stability_range)
    nation.public_opinion += rng.uniform(*opinion_range)
    for r, (lo, hi) in resource_ranges.items():
        nation.resources[r] = nation.resources.get(r, 0.0) + rng.uniform(lo, hi)
    world.log(f"{nation.name} experiences {name.replace('_', ' ')}.")


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
        if nation.government_type == "authoritarian" or nation.is_background:
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
            # Sort by id before picking the max: nation.at_war_with is a
            # set, and Python's string hash randomization means set
            # iteration order isn't stable across process restarts even
            # with the same world.seed. An exact-military tie between two
            # enemies could otherwise pick a different conqueror on a
            # different run, breaking the "same seed, same replay"
            # determinism guarantee. Breaking ties by id keeps the choice
            # a pure function of world state.
            conqueror_id = max(
                sorted(nation.at_war_with),
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
    # Domination only requires eliminating the other nations the game
    # actually simulates as active rivals -- background reference states
    # (Nation.is_background) never act and were never part of "every other
    # nation" in spirit; counting all ~190 of them here would make
    # domination effectively unreachable.
    alive_main = [n for n in world.alive_nations() if not n.is_background]
    if len(alive_main) == 1 and alive_main[0].id == player_id:
        return "win"
    return None


# One turn represents one month. This is purely a labeling/UI concept --
# nothing in the engine's math depends on it -- but it's what lets a
# "skip ahead 3 turns" request be presented to the player as "skip ahead
# 3 months."
TURN_LENGTH_MONTHS = 1


def advance_turns(
    world: World, player_id: str, player_orders: list[Order], num_turns: int, rng: random.Random
) -> list[str]:
    """Resolve `player_orders` (the player may submit several at once, e.g.
    "invest in energy" + "embargo Russia" in the same turn) on the first
    turn, then run `num_turns - 1` further turns with no further player
    input -- an implicit pass, exactly like sitting out a turn -- so the
    player can ask to skip ahead several months at once instead of being
    stopped for input every single turn. AI nations keep acting normally
    throughout. Returns every event_log line produced across all the turns
    advanced, so the caller can show one combined digest instead of only
    the last turn's events; stops early (returning however many turns it
    actually got through) the moment game_status stops being None, since
    there's no point simulating further turns once the game has ended."""
    start_cursor = len(world.event_log)
    run_turn(world, player_orders, rng)
    for _ in range(max(0, num_turns - 1)):
        if game_status(world, player_id) is not None:
            break
        run_turn(world, [Order(player_id, "pass")], rng)
    return world.event_log[start_cursor:]
