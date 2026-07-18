"""Order types and their resolution logic.

Orders are resolved in fixed priority buckets each turn (diplomacy -> economy
-> military) so resolution order never depends on nation iteration order.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from .models import ELECTION_TERM_LENGTH, GOVERNMENT_TYPES, SECTOR_COMMODITY, SECTOR_TYPES, World

ORDER_TYPES = (
    "pass",
    "build_military",
    "invest_economy",
    "invest_sector",
    "improve_relations",
    "propose_alliance",
    "break_alliance",
    "trade_pact",
    "impose_embargo",
    "declare_war",
    "sue_for_peace",
    # Self-only, like invest_sector: no other nation can ever be the target
    # of this order, so no input text can change *another* nation's form of
    # government -- only the actor's own.
    "modify_constitution",
    # A catch-all for erratic, chaotic, or otherwise unmodeled player intent
    # (see worldsim/parser.py) -- still resolves deterministically, just
    # through a sentiment-scored generic gesture instead of a fixed effect.
    "wildcard",
)

# Lower number resolves first.
PRIORITY = {
    "improve_relations": 0,
    "propose_alliance": 0,
    "break_alliance": 0,
    "trade_pact": 0,
    "impose_embargo": 0,
    "sue_for_peace": 0,
    "wildcard": 0,
    "invest_economy": 1,
    "invest_sector": 1,
    "build_military": 1,
    "modify_constitution": 1,
    "declare_war": 2,
    "pass": 3,
}


@dataclass(frozen=True)
class Order:
    actor_id: str
    type: str
    target_id: Optional[str] = None
    # Free-form extra parameter: sector name for invest_sector, new
    # government type for modify_constitution, raw player text for
    # wildcard. Unused by every other order type.
    detail: Optional[str] = None

    def __post_init__(self):
        if self.type not in ORDER_TYPES:
            raise ValueError(f"Unknown order type: {self.type}")
        if self.type in TARGETED_ORDERS and not self.target_id:
            raise ValueError(f"Order {self.type} requires a target_id")
        if self.target_id is not None and self.target_id == self.actor_id:
            raise ValueError(f"Order {self.type} cannot target its own actor")
        if self.type == "invest_sector" and self.detail not in SECTOR_TYPES:
            raise ValueError(f"invest_sector requires detail to be one of {SECTOR_TYPES}")
        if self.type == "modify_constitution" and self.detail not in GOVERNMENT_TYPES:
            raise ValueError(f"modify_constitution requires detail to be one of {GOVERNMENT_TYPES}")


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

WAR_OPINION_HIT_JUSTIFIED = -3
WAR_OPINION_HIT_UNPROVOKED = -10
RALLY_AROUND_FLAG_OPINION_BOOST = 6
EMBARGO_RECEIVED_OPINION_HIT = -4
ALLIANCE_OPINION_BOOST = 3
PEACE_HUMILIATION_OPINION_HIT = -6
PEACE_RELIEF_OPINION_BOOST = 2


def legal_orders(world: World, actor_id: str):
    """Yield every legal Order the given nation could issue this turn."""
    actor = world.get(actor_id)
    yield Order(actor_id, "pass")
    yield Order(actor_id, "build_military")
    yield Order(actor_id, "invest_economy")
    for sector in SECTOR_TYPES:
        yield Order(actor_id, "invest_sector", detail=sector)
    for government_type in GOVERNMENT_TYPES:
        if government_type != actor.government_type:
            yield Order(actor_id, "modify_constitution", detail=government_type)
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


def _resolve_invest_sector(world: World, order: Order) -> None:
    actor = world.get(order.actor_id)
    sector = order.detail
    cost = min(10.0, actor.economy * 0.15)
    actor.economy -= cost
    actor.sectors[sector] = actor.sectors.get(sector, 0.0) + cost
    commodity = SECTOR_COMMODITY.get(sector)
    if commodity:
        actor.resources[commodity] = actor.resources.get(commodity, 0.0) + 5
    sector_label = sector.replace("_sector", "").replace("_", " ")
    world.log(f"{actor.name} invests in its {sector_label} sector.")


CONSTITUTION_COUP_OPINION_HIT = -25
CONSTITUTION_COUP_STABILITY_HIT = -15
CONSTITUTION_COUP_RELATION_HIT = -12
CONSTITUTION_LIBERALIZATION_OPINION_BOOST = 15
CONSTITUTION_TRANSITION_STABILITY_HIT = -5
CONSTITUTION_REFORM_OPINION_DELTA = 3


def _resolve_modify_constitution(world: World, order: Order) -> None:
    """Change the actor's own government type -- this order has no
    target_id at all, so no player input can ever change *another*
    nation's constitution, only their own (see worldsim/parser.py)."""
    actor = world.get(order.actor_id)
    old_type = actor.government_type
    new_type = order.detail
    if new_type == old_type:
        world.log(f"{actor.name} reaffirms its existing {old_type} constitution.")
        return

    was_elected = old_type in ("democracy", "parliamentary")
    becomes_elected = new_type in ("democracy", "parliamentary")

    if was_elected and not becomes_elected:
        # A coup: abolishing elected government for authoritarian rule.
        actor.public_opinion += CONSTITUTION_COUP_OPINION_HIT
        actor.stability += CONSTITUTION_COUP_STABILITY_HIT
        world.log(f"{actor.name} abolishes its {old_type} constitution and imposes {new_type} rule.")
        condemners = 0
        for other in world.alive_nations():
            if other.id == actor.id:
                continue
            if other.government_type in ("democracy", "parliamentary"):
                _shift_relations(other, actor, CONSTITUTION_COUP_RELATION_HIT)
                condemners += 1
        if condemners:
            world.log(f"The world's democracies condemn {actor.name}'s power grab.")
    elif not was_elected and becomes_elected:
        # Democratization: elections are scheduled for the new term.
        actor.public_opinion += CONSTITUTION_LIBERALIZATION_OPINION_BOOST
        actor.stability += CONSTITUTION_TRANSITION_STABILITY_HIT
        actor.election_due_turn = world.turn + ELECTION_TERM_LENGTH
        world.log(f"{actor.name} adopts a {new_type} constitution and schedules elections.")
    else:
        # A reform between two elected systems (democracy <-> parliamentary).
        actor.public_opinion += CONSTITUTION_REFORM_OPINION_DELTA
        world.log(f"{actor.name} reforms its constitution from {old_type} to {new_type}.")

    actor.government_type = new_type


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
        actor.public_opinion += ALLIANCE_OPINION_BOOST
        target.public_opinion += ALLIANCE_OPINION_BOOST
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
    target.public_opinion += EMBARGO_RECEIVED_OPINION_HIT
    world.log(f"{actor.name} imposes an embargo on {target.name}.")
    _react_third_parties(world, actor, target, "embargo")


def _resolve_declare_war(world: World, order: Order) -> None:
    actor = world.get(order.actor_id)
    target = world.get(order.target_id)
    if target.id in actor.at_war_with:
        return
    # Public opinion: a "justified" war against an already-hostile rival
    # costs the aggressor little; an unprovoked war against a nation that
    # wasn't already a rival costs a lot more. The attacked side always
    # gets a short-lived rally-around-the-flag boost.
    pre_war_hostility = actor.relation(target.id)
    _enter_war(world, actor, target)
    _shift_relations(actor, target, WAR_RELATION_HIT)
    actor.public_opinion += (
        WAR_OPINION_HIT_JUSTIFIED if pre_war_hostility <= -50 else WAR_OPINION_HIT_UNPROVOKED
    )
    target.public_opinion += RALLY_AROUND_FLAG_OPINION_BOOST
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
        # Suing for peace while losing reads as humiliation; a mutual,
        # exhausted stalemate is just relief.
        losing = actor.military < target.military * 0.8
        actor.public_opinion += PEACE_HUMILIATION_OPINION_HIT if losing else PEACE_RELIEF_OPINION_BOOST
        target.public_opinion += PEACE_RELIEF_OPINION_BOOST
        world.log(f"{actor.name} and {target.name} agree to a ceasefire.")
    else:
        world.log(f"{target.name} rejects {actor.name}'s peace offer.")


# A lightweight, deterministic sentiment lexicon -- not a language model,
# just a fixed word list -- so wildly unusual player input ("demand a
# refund of the Louisiana Purchase") still gets a proportionate, legible
# reaction instead of being silently ignored or crashing the parser.
HOSTILE_WORDS = (
    "demand", "threat", "ultimatum", "attack", "seize", "annex", "invade",
    "destroy", "refund", "reparation", "punish", "conquer", "strike",
    "bomb", "sanction", "humiliate", "dominate", "reject", "insult",
)
FRIENDLY_WORDS = (
    "gift", "apolog", "support", "help", "praise", "honor", "celebrate",
    "thank", "donate", "forgive", "welcome", "invite", "gratitude",
    "friendship", "congratulat",
)
WILDCARD_RELATION_SCALE = -6
WILDCARD_DOMESTIC_SCALE = 1.5
WILDCARD_PROVOCATION_THRESHOLD = 2


def _sentiment_magnitude(text: str) -> int:
    """Crude, deterministic hostility score: positive = hostile, negative =
    friendly, 0 = ambiguous/neutral. Clamped to [-3, 3]."""
    lowered = text.lower()
    hostile = sum(1 for w in HOSTILE_WORDS if w in lowered)
    friendly = sum(1 for w in FRIENDLY_WORDS if w in lowered)
    return max(-3, min(3, hostile - friendly))


def _resolve_wildcard(world: World, order: Order) -> None:
    """Resolve an unmodeled, erratic, or unrealistic player statement.

    There's no fixed effect for "demand a refund of the Louisiana
    Purchase" -- instead this scores the statement's tone with a fixed
    word list and applies a proportionate, logged reaction. Chaotic input
    is never ignored and never crashes; it always produces *some*
    deterministic, in-world consequence.
    """
    actor = world.get(order.actor_id)
    text = (order.detail or "").strip()
    snippet = text if len(text) <= 70 else text[:67] + "..."
    magnitude = _sentiment_magnitude(text)
    target = world.get(order.target_id) if order.target_id else None

    if target is None:
        actor.public_opinion += magnitude * WILDCARD_DOMESTIC_SCALE
        world.log(f"{actor.name}'s government makes an unusual public statement: \"{snippet}\"")
        return

    _shift_relations(actor, target, magnitude * WILDCARD_RELATION_SCALE)
    if magnitude > 0:
        world.log(f"{actor.name} makes an extraordinary demand of {target.name}: \"{snippet}\"")
        world.log(f"{target.name} rebuffs the demand and relations sour.")
        if magnitude >= WILDCARD_PROVOCATION_THRESHOLD:
            _react_third_parties(world, actor, target, "embargo")
            world.log(f"{target.name}'s allies take note of {actor.name}'s provocation.")
    elif magnitude < 0:
        world.log(f"{actor.name} extends an unusual goodwill gesture to {target.name}: \"{snippet}\"")
        world.log(f"{target.name} is pleasantly surprised; relations warm slightly.")
    else:
        world.log(f"{actor.name} makes a puzzling statement toward {target.name}: \"{snippet}\"")
        world.log(f"{target.name} isn't sure what to make of it.")


RESOLVERS = {
    "pass": _resolve_pass,
    "build_military": _resolve_build_military,
    "invest_economy": _resolve_invest_economy,
    "invest_sector": _resolve_invest_sector,
    "modify_constitution": _resolve_modify_constitution,
    "improve_relations": _resolve_improve_relations,
    "propose_alliance": _resolve_propose_alliance,
    "break_alliance": _resolve_break_alliance,
    "trade_pact": _resolve_trade_pact,
    "impose_embargo": _resolve_impose_embargo,
    "declare_war": _resolve_declare_war,
    "sue_for_peace": _resolve_sue_for_peace,
    "wildcard": _resolve_wildcard,
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
