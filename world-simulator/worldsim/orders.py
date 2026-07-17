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

# How many turns a ceasefire (from a successful sue_for_peace) blocks a fresh
# declare_war between the same two nations -- without this, two nations
# whose relations are still deeply negative just re-declare war the very
# next turn, producing a war/peace flicker instead of a real ceasefire.
TRUCE_DURATION = 5


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
            if world.turn >= actor.truce_until.get(other.id, -1):
                yield Order(actor_id, "declare_war", other.id)
        else:
            yield Order(actor_id, "sue_for_peace", other.id)


ALLY_SOLIDARITY_RELATION_HIT = -20
ALLY_BACKING_RELATION_HIT = -15
EMBARGO_SOLIDARITY_RELATION_HIT = -8
RIVAL_BLOC_WARINESS_HIT = -3
RIVAL_BLOC_THRESHOLD = -30


def _shift_relations(actor, target, delta: float) -> None:
    """Apply a mutual relation delta between two nations and clamp both
    sides immediately, so every caller (direct order or third-party
    reaction) leaves relations in a valid, bounded state."""
    actor.relations[target.id] = actor.relation(target.id) + delta
    target.relations[actor.id] = target.relation(actor.id) + delta
    actor.clamp_stats()
    target.clamp_stats()


def _enter_war(world: World, side_a, side_b) -> None:
    """Put two nations at war with each other (idempotent), without the
    relations penalty of a fresh declaration -- used both by a direct
    declare_war and by an ally invoking its defense pact."""
    if side_b.id in side_a.at_war_with:
        return
    side_a.alliances.discard(side_b.id)
    side_b.alliances.discard(side_a.id)
    side_a.at_war_with.add(side_b.id)
    side_b.at_war_with.add(side_a.id)


def _react_third_parties(world: World, actor, target, event: str) -> None:
    """The rest of the world doesn't just watch: allies and rivals of the
    two participants shift their own stance in response to what just
    happened. This is what makes the simulation feel alive without any
    AI/LLM call -- it's a fixed rule applied to every bystander nation.

    Alliances are formal mutual-defense pacts (this is what makes NATO act
    like NATO): attacking any member is treated as attacking the whole
    bloc, so every other ally invokes its defense obligation and joins the
    war against the aggressor -- it isn't just a relations hit.
    """
    for other in world.alive_nations():
        if other.id in (actor.id, target.id):
            continue

        if event == "war":
            if target.id in other.alliances:
                _shift_relations(other, actor, ALLY_SOLIDARITY_RELATION_HIT)
                _enter_war(world, other, actor)
                world.log(
                    f"{other.name} invokes its defense pact with {target.name} "
                    f"and joins the war against {actor.name}."
                )
            elif actor.id in other.alliances:
                _shift_relations(other, target, ALLY_BACKING_RELATION_HIT)
                world.log(f"{other.name} backs its ally {actor.name} against {target.name}.")

        elif event == "embargo":
            if target.id in other.alliances:
                _shift_relations(other, actor, EMBARGO_SOLIDARITY_RELATION_HIT)

        elif event == "alliance":
            if other.relation(actor.id) < RIVAL_BLOC_THRESHOLD or other.relation(target.id) < RIVAL_BLOC_THRESHOLD:
                _shift_relations(other, actor, RIVAL_BLOC_WARINESS_HIT)
                _shift_relations(other, target, RIVAL_BLOC_WARINESS_HIT)


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
    # Sustained investment raises the nation's long-run ceiling, not just
    # its current economy -- otherwise every nation eventually converges on
    # the same global cap regardless of how much it actually invested.
    actor.economic_potential += 0.6


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
        _react_third_parties(world, actor, target, "alliance")


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
    _react_third_parties(world, actor, target, "embargo")


def _resolve_declare_war(world: World, order: Order) -> None:
    actor = world.get(order.actor_id)
    target = world.get(order.target_id)
    if target.id in actor.at_war_with:
        return
    _enter_war(world, actor, target)
    _shift_relations(actor, target, WAR_RELATION_HIT)
    world.log(f"{actor.name} declares war on {target.name}!")
    _react_third_parties(world, actor, target, "war")


def _resolve_sue_for_peace(world: World, order: Order) -> None:
    actor = world.get(order.actor_id)
    target = world.get(order.target_id)
    if target.id not in actor.at_war_with:
        return
    # Peace sticks if the target isn't clearly winning, or if both sides
    # have fought each other to a standstill (near-zero militaries) -- a
    # strict "is actor losing" check alone never fires on a tied stalemate,
    # which otherwise leaves wars stuck at 0 military forever.
    actor_winning = actor.military > target.military * 1.3
    mutually_exhausted = actor.military < 15 and target.military < 15
    if not actor_winning or mutually_exhausted:
        actor.at_war_with.discard(target.id)
        target.at_war_with.discard(actor.id)
        actor.truce_until[target.id] = world.turn + TRUCE_DURATION
        target.truce_until[actor.id] = world.turn + TRUCE_DURATION
        world.log(f"{actor.name} and {target.name} agree to a ceasefire.")
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
