"""Order types and their resolution logic.

Orders are resolved in fixed priority buckets each turn (diplomacy -> economy
-> military) so resolution order never depends on nation iteration order.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from .models import World

ORDER_TYPES = (
    "pass",
    "build_military",
    "invest_economy",
    "improve_relations",
    "propose_alliance",
    "break_alliance",
    "trade_pact",
    "impose_embargo",
    "declare_war",
    "sue_for_peace",
)

# Lower number resolves first.
PRIORITY = {
    "improve_relations": 0,
    "propose_alliance": 0,
    "break_alliance": 0,
    "trade_pact": 0,
    "impose_embargo": 0,
    "sue_for_peace": 0,
    "invest_economy": 1,
    "build_military": 1,
    "declare_war": 2,
    "pass": 3,
}


@dataclass(frozen=True)
class Order:
    actor_id: str
    type: str
    target_id: Optional[str] = None

    def __post_init__(self):
        if self.type not in ORDER_TYPES:
            raise ValueError(f"Unknown order type: {self.type}")
        if self.type in TARGETED_ORDERS and not self.target_id:
            raise ValueError(f"Order {self.type} requires a target_id")
        if self.target_id is not None and self.target_id == self.actor_id:
            raise ValueError(f"Order {self.type} cannot target its own actor")


TARGETED_ORDERS = {
    "improve_relations",
    "propose_alliance",
    "break_alliance",
    "trade_pact",
    "impose_embargo",
    "declare_war",
    "sue_for_peace",
}

ALLIANCE_RELATION_THRESHOLD = 40
WAR_RELATION_HIT = -60
EMBARGO_RELATION_HIT = -20
BREAK_ALLIANCE_RELATION_HIT = -15


def legal_orders(world: World, actor_id: str):
    """Yield every legal Order the given nation could issue this turn."""
    actor = world.get(actor_id)
    yield Order(actor_id, "pass")
    yield Order(actor_id, "build_military")
    yield Order(actor_id, "invest_economy")
    for other in world.alive_nations():
        if other.id == actor_id:
            continue
        yield Order(actor_id, "improve_relations", other.id)
        if other.id not in actor.at_war_with:
            mutual_relation = min(actor.relation(other.id), other.relation(actor_id))
            if (
                other.id not in actor.alliances
                and mutual_relation >= ALLIANCE_RELATION_THRESHOLD
            ):
                yield Order(actor_id, "propose_alliance", other.id)
            if other.id in actor.alliances:
                yield Order(actor_id, "break_alliance", other.id)
            if other.id not in actor.trade_pacts and mutual_relation >= 0:
                yield Order(actor_id, "trade_pact", other.id)
            if other.id not in actor.embargoes_against:
                yield Order(actor_id, "impose_embargo", other.id)
            yield Order(actor_id, "declare_war", other.id)
        else:
            yield Order(actor_id, "sue_for_peace", other.id)


def _shift_relations(actor, target, delta: float) -> None:
    """Apply a mutual relation delta between two nations (clamped later by
    Nation.clamp_stats, called after every order resolves)."""
    actor.relations[target.id] = actor.relation(target.id) + delta
    target.relations[actor.id] = target.relation(actor.id) + delta


def _resolve_pass(world: World, order: Order) -> None:
    actor = world.get(order.actor_id)
    actor.stability += 1


def _resolve_build_military(world: World, order: Order) -> None:
    actor = world.get(order.actor_id)
    spend = min(15.0, actor.economy * 0.2)
    actor.economy -= spend
    actor.military += spend * 1.2


def _resolve_invest_economy(world: World, order: Order) -> None:
    actor = world.get(order.actor_id)
    actor.economy += 5 + actor.resources.get("energy", 0) * 0.02
    actor.stability += 0.5


def _resolve_improve_relations(world: World, order: Order) -> None:
    actor = world.get(order.actor_id)
    target = world.get(order.target_id)
    _shift_relations(actor, target, 8)


def _resolve_propose_alliance(world: World, order: Order) -> None:
    actor = world.get(order.actor_id)
    target = world.get(order.target_id)
    if actor.relation(target.id) >= ALLIANCE_RELATION_THRESHOLD and target.relation(actor.id) >= ALLIANCE_RELATION_THRESHOLD:
        actor.alliances.add(target.id)
        target.alliances.add(actor.id)
        world.log(f"{actor.name} and {target.name} form an alliance.")


def _resolve_break_alliance(world: World, order: Order) -> None:
    actor = world.get(order.actor_id)
    target = world.get(order.target_id)
    if target.id in actor.alliances:
        actor.alliances.discard(target.id)
        target.alliances.discard(actor.id)
        _shift_relations(actor, target, BREAK_ALLIANCE_RELATION_HIT)
        world.log(f"{actor.name} breaks its alliance with {target.name}.")


def _resolve_trade_pact(world: World, order: Order) -> None:
    actor = world.get(order.actor_id)
    target = world.get(order.target_id)
    if actor.relation(target.id) >= 0 and target.relation(actor.id) >= 0:
        actor.trade_pacts.add(target.id)
        target.trade_pacts.add(actor.id)
        world.log(f"{actor.name} and {target.name} sign a trade pact.")


def _resolve_impose_embargo(world: World, order: Order) -> None:
    actor = world.get(order.actor_id)
    target = world.get(order.target_id)
    actor.embargoes_against.add(target.id)
    actor.trade_pacts.discard(target.id)
    target.trade_pacts.discard(actor.id)
    _shift_relations(actor, target, EMBARGO_RELATION_HIT)
    world.log(f"{actor.name} imposes an embargo on {target.name}.")


def _resolve_declare_war(world: World, order: Order) -> None:
    actor = world.get(order.actor_id)
    target = world.get(order.target_id)
    if target.id in actor.at_war_with:
        return
    actor.alliances.discard(target.id)
    target.alliances.discard(actor.id)
    actor.at_war_with.add(target.id)
    target.at_war_with.add(actor.id)
    _shift_relations(actor, target, WAR_RELATION_HIT)
    world.log(f"{actor.name} declares war on {target.name}!")


def _resolve_sue_for_peace(world: World, order: Order) -> None:
    actor = world.get(order.actor_id)
    target = world.get(order.target_id)
    if target.id not in actor.at_war_with:
        return
    # Peace only sticks if the target also wants it (weaker/exhausted) or was
    # the one who proposed. We approximate willingness with a stability check:
    # a side accepts peace if it isn't clearly winning.
    actor_winning = actor.military > target.military * 1.3
    if not actor_winning:
        actor.at_war_with.discard(target.id)
        target.at_war_with.discard(actor.id)
        world.log(f"{actor.name} and {target.name} agree to peace.")
    else:
        world.log(f"{target.name} rejects {actor.name}'s peace offer.")


RESOLVERS = {
    "pass": _resolve_pass,
    "build_military": _resolve_build_military,
    "invest_economy": _resolve_invest_economy,
    "improve_relations": _resolve_improve_relations,
    "propose_alliance": _resolve_propose_alliance,
    "break_alliance": _resolve_break_alliance,
    "trade_pact": _resolve_trade_pact,
    "impose_embargo": _resolve_impose_embargo,
    "declare_war": _resolve_declare_war,
    "sue_for_peace": _resolve_sue_for_peace,
}


def resolve_orders(world: World, orders: list) -> None:
    """Resolve a batch of orders in fixed priority order (stable sort)."""
    ordered = sorted(orders, key=lambda o: PRIORITY[o.type])
    for order in ordered:
        actor = world.nations.get(order.actor_id)
        if actor is None or not actor.alive:
            continue
        if order.target_id is not None:
            target = world.nations.get(order.target_id)
            if target is None or not target.alive:
                continue
        RESOLVERS[order.type](world, order)
        actor.clamp_stats()
        if order.target_id:
            world.get(order.target_id).clamp_stats()
