"""Turn loop: gather orders, resolve them, apply passive effects, log events."""
from __future__ import annotations

import random
from typing import Callable, Optional

from .ai import choose_order
from .models import World
from .orders import Order, resolve_orders

WAR_STABILITY_DRAIN = 2.0
WAR_MILITARY_DRAIN = 1.5
COLLAPSE_STABILITY = 0.0

MINOR_EVENTS = (
    ("drought", {"food": -10}, -3),
    ("bumper_harvest", {"food": 10}, 2),
    ("resource_discovery", {"rare_earths": 15}, 1),
    ("civil_unrest", {}, -6),
    ("cultural_festival", {}, 3),
)


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

        # Embargoes against this nation drain its economy.
        nation.economy -= 1.5 * embargoers_by_target.get(nation.id, 0)

        # Trade pacts give a small mutual boost.
        nation.economy += 0.5 * len(nation.trade_pacts & alive_ids)

        # Stability drifts toward a target based on prosperity.
        target_stability = 40 + nation.economy * 0.3
        nation.stability += (target_stability - nation.stability) * 0.05

        # Resources regenerate slowly if not embargoed.
        for r in nation.resources:
            nation.resources[r] += 1.0

        # A small seeded chance of a minor event.
        if rng.random() < 0.08:
            name, resource_deltas, stability_delta = rng.choice(MINOR_EVENTS)
            nation.stability += stability_delta
            for r, d in resource_deltas.items():
                nation.resources[r] = nation.resources.get(r, 0) + d
            world.log(f"{nation.name} experiences {name.replace('_', ' ')}.")

        nation.clamp_stats()


def _check_collapses(world: World) -> None:
    for nation in world.alive_nations():
        if nation.stability <= COLLAPSE_STABILITY:
            nation.alive = False
            for other in world.nations.values():
                other.alliances.discard(nation.id)
                other.trade_pacts.discard(nation.id)
                other.at_war_with.discard(nation.id)
                other.embargoes_against.discard(nation.id)
            world.log(f"{nation.name} collapses into instability and exits the world stage.")


def game_status(world: World, player_id: str, max_turns: int = 100) -> Optional[str]:
    """Return 'win', 'loss', or None if the game should continue."""
    player = world.nations[player_id]
    if not player.alive:
        return "loss"
    alive = world.alive_nations()
    if world.turn >= max_turns:
        strongest = max(alive, key=lambda n: n.economy + n.military)
        return "win" if strongest.id == player_id else "loss"
    if len(alive) == 1 and alive[0].id == player_id:
        return "win"
    return None
