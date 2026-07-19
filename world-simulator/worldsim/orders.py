"""Order types and their resolution logic.

Orders are resolved in fixed priority buckets each turn (diplomacy -> economy
-> military) so resolution order never depends on nation iteration order.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from .models import ELECTION_TERM_LENGTH, GOVERNMENT_TYPES, SECTOR_COMMODITY, SECTOR_TYPES, STAT_MAX, World


def _pick_variant(options: tuple, *seed_parts) -> str:
    """Deterministically pick one of several equivalent phrasings for the
    same event, so the same kind of thing happening over and over (a trade
    pact, a sector investment, an election) doesn't read as the identical
    canned sentence every time -- without needing an RNG threaded through
    every resolver (there isn't one available here) and without breaking
    determinism (Python's builtin hash() is salted per-process by default,
    which would make "the same seed replays identically" false; this uses
    a stable, order-dependent sum instead)."""
    if len(options) == 1:
        return options[0]
    total = 0
    for part in seed_parts:
        for ch in str(part):
            total = (total * 31 + ord(ch)) % 1_000_003
    return options[total % len(options)]

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
    # Forced conquest: only legal against a nation the actor is already at
    # war with and has crushed decisively (see legal_orders).
    "annex",
    # A nation voting to peacefully dissolve into another. This is a
    # self-only-in-spirit order in that it can only ever remove *the
    # actor itself* from the map, never force another nation to disband.
    "propose_accession",
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
    "propose_accession": 0,
    "wildcard": 0,
    "invest_economy": 1,
    "invest_sector": 1,
    "build_military": 1,
    "modify_constitution": 1,
    "declare_war": 2,
    "annex": 2,
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
    "annex",
    "propose_accession",
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

# A war can be ended by outright conquest once the actor has crushed the
# target this decisively -- either the target's military has collapsed to
# a token force, or the actor's is overwhelming relative to it.
ANNEX_MILITARY_FLOOR = 15.0
ANNEX_DOMINANCE_RATIO = 3.0
ANNEX_MIN_ACTOR_MILITARY = 15.0

# High enough mutual trust that a population would plausibly vote to give
# up sovereignty and join a neighbor outright, rather than just allying.
ACCESSION_RELATION_THRESHOLD = 70.0


def _is_annex_eligible(actor, target) -> bool:
    if actor.military < ANNEX_MIN_ACTOR_MILITARY:
        return False
    return target.military < ANNEX_MILITARY_FLOOR or actor.military > target.military * ANNEX_DOMINANCE_RATIO


def is_engaged(actor, other) -> bool:
    """Whether `actor` already has some real relationship with `other` --
    an alliance, trade pact, war, embargo, or a relation score that isn't
    still at its untouched default. Used to let a background nation
    (Nation.is_background) surface in legal_orders/the menu once the
    player has actually interacted with it, instead of either being
    permanently invisible there or bloating every menu with ~190 mostly
    irrelevant entries from turn one."""
    return (
        other.id in actor.alliances
        or other.id in actor.trade_pacts
        or other.id in actor.at_war_with
        or other.id in actor.embargoes_against
        or actor.relation(other.id) != 0.0
    )


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
        # Background nations (Nation.is_background) are real, addressable
        # targets via free text at any time, but only clutter the AI's
        # decision space and the player's numbered menu once genuinely
        # engaged -- an AI nation never initiates contact with one at all,
        # keeping ~190 inert reference states from ever being autonomously
        # targeted or from ballooning every menu into thousands of entries.
        if other.is_background and not (actor.is_player and is_engaged(actor, other)):
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
            if mutual_relation >= ACCESSION_RELATION_THRESHOLD:
                yield Order(actor_id, "propose_accession", other.id)
        else:
            yield Order(actor_id, "sue_for_peace", other.id)
            if _is_annex_eligible(actor, other):
                yield Order(actor_id, "annex", other.id)


ALLY_SOLIDARITY_RELATION_HIT = -20
ALLY_BACKING_RELATION_HIT = -15
EMBARGO_SOLIDARITY_RELATION_HIT = -8
RIVAL_BLOC_WARINESS_HIT = -3
RIVAL_BLOC_THRESHOLD = -30

DEFENSE_PACT_MESSAGES = (
    "{o} invokes its defense pact with {t} and joins the war against {a}.",
    "Honoring its treaty with {t}, {o} enters the war against {a}.",
    "{o} answers the call of its alliance with {t}, declaring war on {a}.",
)
ALLY_BACKING_MESSAGES = (
    "{o} backs its ally {a} against {t}.",
    "{o} voices support for {a} in the standoff with {t}.",
    "{o} throws its diplomatic weight behind {a} against {t}.",
)


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
    side_a.trade_pacts.discard(side_b.id)
    side_b.trade_pacts.discard(side_a.id)
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
                world.log(_pick_variant(DEFENSE_PACT_MESSAGES, world.turn, other.id, actor.id).format(
                    o=other.name, t=target.name, a=actor.name
                ))
            elif actor.id in other.alliances:
                _shift_relations(other, target, ALLY_BACKING_RELATION_HIT)
                world.log(_pick_variant(ALLY_BACKING_MESSAGES, world.turn, other.id, target.id).format(
                    o=other.name, a=actor.name, t=target.name
                ))

        elif event == "embargo":
            if target.id in other.alliances:
                _shift_relations(other, actor, EMBARGO_SOLIDARITY_RELATION_HIT)

        elif event == "alliance":
            if other.relation(actor.id) < RIVAL_BLOC_THRESHOLD or other.relation(target.id) < RIVAL_BLOC_THRESHOLD:
                _shift_relations(other, actor, RIVAL_BLOC_WARINESS_HIT)
                _shift_relations(other, target, RIVAL_BLOC_WARINESS_HIT)


PASS_MESSAGES = (
    "{a} holds steady, making no major moves this month.",
    "{a}'s government stays the course, taking no significant action.",
    "{a} spends the month on routine governance, nothing eventful.",
)
BUILD_MILITARY_MESSAGES = (
    "{a} expands its armed forces.",
    "{a} ramps up military production.",
    "{a} funnels fresh spending into its armed forces.",
)
INVEST_ECONOMY_MESSAGES = (
    "{a} rolls out an economic stimulus package.",
    "{a} pours investment into its economy.",
    "{a}'s government moves to shore up its economy.",
)
IMPROVE_RELATIONS_MESSAGES = (
    "{a} extends a diplomatic overture toward {t}.",
    "{a} works to warm relations with {t}.",
    "{a} sends a goodwill delegation to {t}.",
)
INVEST_SECTOR_MESSAGES = (
    "{a} invests in its {s} sector.",
    "{a} pours resources into developing its {s} sector.",
    "{a} announces a push to modernize its {s} sector.",
)


def _resolve_pass(world: World, order: Order) -> None:
    # Bug fix: this used to produce zero log output at all -- the most
    # common possible order (an empty turn, or the implicit pass used by
    # advance_turns while skipping ahead) left no trace whatsoever that
    # anything had happened, which read as the game simply ignoring the
    # player.
    actor = world.get(order.actor_id)
    actor.stability += 1
    world.log(_pick_variant(PASS_MESSAGES, world.turn, actor.id).format(a=actor.name))


def _resolve_build_military(world: World, order: Order) -> None:
    actor = world.get(order.actor_id)
    # Once military is already at (or essentially at) its hard cap,
    # spending here would buy zero real gain -- clamp_stats silently
    # discards the overflow after this resolver runs, but the economic
    # cost would still have been paid for nothing. Charge only for the
    # military the nation can actually still gain.
    room = max(0.0, STAT_MAX - actor.military)
    if room <= 0.0:
        world.log(_pick_variant(BUILD_MILITARY_FULL_MESSAGES, world.turn, actor.id).format(a=actor.name))
        return
    spend = min(15.0, actor.economy * 0.2, room / 1.2)
    actor.economy -= spend
    actor.military += spend * 1.2
    # Bug fix: the normal (not-already-at-cap) case used to produce zero
    # log output at all, unlike every other order type -- the player would
    # spend economy on a military buildup and see no confirmation of it.
    world.log(_pick_variant(BUILD_MILITARY_MESSAGES, world.turn, actor.id).format(a=actor.name))


def _resolve_invest_economy(world: World, order: Order) -> None:
    # Bug fix: this used to produce zero log output at all -- one of the
    # most commonly issued orders left no confirmation whatsoever that it
    # had happened.
    actor = world.get(order.actor_id)
    actor.economy += 5 + actor.resources.get("energy", 0) * 0.02
    actor.stability += 0.5
    # Sustained investment raises the nation's long-run ceiling, not just
    # its current economy -- otherwise every nation eventually converges on
    # the same global cap regardless of how much it actually invested.
    actor.economic_potential += 0.6
    world.log(_pick_variant(INVEST_ECONOMY_MESSAGES, world.turn, actor.id).format(a=actor.name))


def _resolve_invest_sector(world: World, order: Order) -> None:
    actor = world.get(order.actor_id)
    sector = order.detail
    # Bug fix / rebalance: this used to cost up to 15% of economy per turn
    # while feeding back into economy only through a weak, heavily diluted
    # passive drift (see _apply_passive_effects' avg_sector term) -- a
    # player who spent several turns straight investing in one sector saw
    # their headline economy number visibly crater with no offsetting
    # payoff for turns on end, reading as "nothing happened." Sector
    # investment is still meant to be a slower, more structural lever than
    # invest_economy, not a free lunch, but it should still read as an
    # investment, not a drain: raise the nation's long-run economic
    # ceiling a little too, same as invest_economy does, so the passive
    # drift-toward-potential pulls economy back up over the next several
    # turns instead of the money just vanishing.
    cost = min(6.0, actor.economy * 0.1)
    actor.economy -= cost
    actor.sectors[sector] = actor.sectors.get(sector, 0.0) + cost * 1.3
    actor.economic_potential += cost * 0.4
    commodity = SECTOR_COMMODITY.get(sector)
    if commodity:
        actor.resources[commodity] = actor.resources.get(commodity, 0.0) + 5
    sector_label = sector.replace("_sector", "").replace("_", " ")
    world.log(_pick_variant(INVEST_SECTOR_MESSAGES, world.turn, actor.id, sector).format(
        a=actor.name, s=sector_label
    ))


CONSTITUTION_COUP_OPINION_HIT = -25
CONSTITUTION_COUP_STABILITY_HIT = -15
CONSTITUTION_COUP_RELATION_HIT = -12
CONSTITUTION_LIBERALIZATION_OPINION_BOOST = 15
CONSTITUTION_TRANSITION_STABILITY_HIT = -5
CONSTITUTION_REFORM_OPINION_DELTA = 3

COUP_MESSAGES = (
    "{a} abolishes its {old} constitution and imposes {new} rule.",
    "In a sudden power grab, {a} scraps its {old} constitution for {new} rule.",
)
LIBERALIZATION_MESSAGES = (
    "{a} adopts a {new} constitution and schedules elections.",
    "{a} turns toward {new} governance, announcing a new constitution and elections.",
)
CONSTITUTION_REFORM_MESSAGES = (
    "{a} reforms its constitution from {old} to {new}.",
    "{a} restructures its government, moving from {old} to {new}.",
)
BUILD_MILITARY_FULL_MESSAGES = (
    "{a}'s military is already at full strength; the buildup has nowhere to go.",
    "{a}'s armed forces are already at their peak; further spending would be wasted.",
)
ANNEX_MESSAGES = (
    "{a} annexes {t} outright, absorbing its territory and population.",
    "{a} formally annexes the defeated {t}, folding it into its own territory.",
)
ANNEX_FAILED_MESSAGES = (
    "{a} attempts to annex {t}, but its forces haven't been crushed decisively enough.",
    "{a} presses for annexation of {t}, but the war hasn't been decided yet.",
)
ACCESSION_REJECTED_MESSAGES = (
    "{a}'s population votes against joining {t}; ties remain close but sovereign.",
    "{a} narrowly rejects union with {t} at the ballot box, remaining independent.",
)
ACCESSION_MESSAGES = (
    "{a} votes to join {t} in a peaceful union.",
    "{a}'s population votes to dissolve into {t} in a peaceful union.",
)


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
        world.log(_pick_variant(COUP_MESSAGES, world.turn, actor.id).format(a=actor.name, old=old_type, new=new_type))
        condemners = 0
        for other in world.alive_nations():
            # Bug fix: this used to include every background nation
            # (Nation.is_background) too -- since ~180 of the ~190
            # background nations default to "democracy", any coup silently
            # set a real relations.dict entry between the actor and nearly
            # every background nation on Earth. is_engaged() (used to gate
            # background nations out of the menu and world-summary
            # display) treats any nonzero relation as "engaged," so this
            # permanently and invisibly flooded the actor's own menu and
            # world summary with ~180 background nations after a single
            # coup -- exactly the clutter that mechanism exists to avoid.
            if other.id == actor.id or other.is_background:
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
        world.log(_pick_variant(LIBERALIZATION_MESSAGES, world.turn, actor.id).format(a=actor.name, new=new_type))
    else:
        # A reform between two elected systems (democracy <-> parliamentary).
        actor.public_opinion += CONSTITUTION_REFORM_OPINION_DELTA
        world.log(_pick_variant(CONSTITUTION_REFORM_MESSAGES, world.turn, actor.id).format(a=actor.name, old=old_type, new=new_type))

    actor.government_type = new_type


def _resolve_improve_relations(world: World, order: Order) -> None:
    # Bug fix: this used to produce zero log output at all -- a targeted,
    # deliberate diplomatic order left no confirmation it had happened.
    actor = world.get(order.actor_id)
    target = world.get(order.target_id)
    _shift_relations(actor, target, 8)
    world.log(_pick_variant(IMPROVE_RELATIONS_MESSAGES, world.turn, actor.id, target.id).format(
        a=actor.name, t=target.name
    ))


ALLIANCE_MESSAGES = (
    "{a} and {t} form an alliance.",
    "{a} and {t} sign a mutual defense pact.",
    "{a} and {t} formally align, pledging to defend one another.",
)
ALLIANCE_REJECTED_MESSAGES = (
    "{t} isn't ready to formalize an alliance with {a} yet; relations aren't warm enough.",
    "{a}'s alliance proposal to {t} goes nowhere; trust between them still runs too thin.",
)
BREAK_ALLIANCE_MESSAGES = (
    "{a} breaks its alliance with {t}.",
    "{a} renounces its treaty with {t}.",
    "{a} walks away from its alliance with {t}, straining ties.",
)
TRADE_PACT_MESSAGES = (
    "{a} and {t} sign a trade pact.",
    "{a} and {t} open new trade channels.",
    "{a} and {t} strike a fresh trade agreement.",
)
TRADE_PACT_REJECTED_MESSAGES = (
    "{t} declines {a}'s trade overture; relations are too strained for a deal right now.",
    "{a}'s trade proposal to {t} falls through amid frosty relations.",
)
EMBARGO_MESSAGES = (
    "{a} imposes an embargo on {t}.",
    "{a} moves to economically isolate {t}.",
    "{a} cuts off trade with {t} in a new embargo.",
)
DECLARE_WAR_MESSAGES = (
    "{a} declares war on {t}!",
    "{a} launches an offensive against {t}!",
    "War breaks out as {a} attacks {t}!",
)
CEASEFIRE_MESSAGES = (
    "{a} and {t} agree to a ceasefire.",
    "{a} and {t} reach a truce, ending the fighting for now.",
    "Exhausted, {a} and {t} lay down arms in a ceasefire.",
)
PEACE_REJECTED_MESSAGES = (
    "{t} presses its advantage and rejects {a}'s peace offer.",
    "{t} refuses {a}'s peace overture, sensing victory within reach.",
    "{t} presses on, spurning {a}'s bid for peace.",
)


def _resolve_propose_alliance(world: World, order: Order) -> None:
    # Bug fix: this used to produce zero log output at all when the
    # relation threshold wasn't met -- a deliberate order the player typed
    # (e.g. "ally with Argentina") would silently do nothing with no
    # confirmation and no explanation, reading as the game ignoring the
    # player.
    actor = world.get(order.actor_id)
    target = world.get(order.target_id)
    if actor.relation(target.id) >= ALLIANCE_RELATION_THRESHOLD and target.relation(actor.id) >= ALLIANCE_RELATION_THRESHOLD:
        actor.alliances.add(target.id)
        target.alliances.add(actor.id)
        actor.public_opinion += ALLIANCE_OPINION_BOOST
        target.public_opinion += ALLIANCE_OPINION_BOOST
        world.log(_pick_variant(ALLIANCE_MESSAGES, world.turn, actor.id, target.id).format(a=actor.name, t=target.name))
        _react_third_parties(world, actor, target, "alliance")
    else:
        world.log(_pick_variant(ALLIANCE_REJECTED_MESSAGES, world.turn, actor.id, target.id).format(a=actor.name, t=target.name))


def _resolve_break_alliance(world: World, order: Order) -> None:
    actor = world.get(order.actor_id)
    target = world.get(order.target_id)
    if target.id in actor.alliances:
        actor.alliances.discard(target.id)
        target.alliances.discard(actor.id)
        _shift_relations(actor, target, BREAK_ALLIANCE_RELATION_HIT)
        world.log(_pick_variant(BREAK_ALLIANCE_MESSAGES, world.turn, actor.id, target.id).format(a=actor.name, t=target.name))


def _resolve_trade_pact(world: World, order: Order) -> None:
    # Bug fix: same silent-no-op gap as propose_alliance -- see comment
    # there.
    actor = world.get(order.actor_id)
    target = world.get(order.target_id)
    if actor.relation(target.id) >= 0 and target.relation(actor.id) >= 0:
        actor.trade_pacts.add(target.id)
        target.trade_pacts.add(actor.id)
        world.log(_pick_variant(TRADE_PACT_MESSAGES, world.turn, actor.id, target.id).format(a=actor.name, t=target.name))
    else:
        world.log(_pick_variant(TRADE_PACT_REJECTED_MESSAGES, world.turn, actor.id, target.id).format(a=actor.name, t=target.name))


def _resolve_impose_embargo(world: World, order: Order) -> None:
    actor = world.get(order.actor_id)
    target = world.get(order.target_id)
    actor.embargoes_against.add(target.id)
    actor.trade_pacts.discard(target.id)
    target.trade_pacts.discard(actor.id)
    _shift_relations(actor, target, EMBARGO_RELATION_HIT)
    target.public_opinion += EMBARGO_RECEIVED_OPINION_HIT
    world.log(_pick_variant(EMBARGO_MESSAGES, world.turn, actor.id, target.id).format(a=actor.name, t=target.name))
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
    world.log(_pick_variant(DECLARE_WAR_MESSAGES, world.turn, actor.id, target.id).format(a=actor.name, t=target.name))
    _react_third_parties(world, actor, target, "war")


def _resolve_sue_for_peace(world: World, order: Order) -> None:
    actor = world.get(order.actor_id)  # the one asking for peace
    target = world.get(order.target_id)  # the one who must agree to it
    if target.id not in actor.at_war_with:
        return
    # Peace sticks if the *target* (whose consent actually matters) isn't
    # clearly dominant, or if both sides have fought each other to a
    # standstill (near-zero militaries). Bug fix: this used to check
    # whether the *asker* was winning, which is nearly always false for
    # the losing side that realistically asks for peace -- meaning peace
    # always succeeded no matter how thoroughly the asker was being
    # crushed, and a decisively dominant side could never press its
    # advantage toward annexation. Now the side actually being asked to
    # stop fighting gets a real say.
    target_dominant = target.military > actor.military * 1.3
    mutually_exhausted = actor.military < 15 and target.military < 15
    if not target_dominant or mutually_exhausted:
        actor.at_war_with.discard(target.id)
        target.at_war_with.discard(actor.id)
        actor.truce_until[target.id] = world.turn + TRUCE_DURATION
        target.truce_until[actor.id] = world.turn + TRUCE_DURATION
        # Suing for peace while losing reads as humiliation; a mutual,
        # exhausted stalemate is just relief.
        losing = actor.military < target.military * 0.8
        actor.public_opinion += PEACE_HUMILIATION_OPINION_HIT if losing else PEACE_RELIEF_OPINION_BOOST
        target.public_opinion += PEACE_RELIEF_OPINION_BOOST
        world.log(_pick_variant(CEASEFIRE_MESSAGES, world.turn, actor.id, target.id).format(a=actor.name, t=target.name))
    else:
        world.log(_pick_variant(PEACE_REJECTED_MESSAGES, world.turn, actor.id, target.id).format(a=actor.name, t=target.name))


# Sovereignty changes: a nation ceasing to exist as an independent actor,
# its territory/population/economy folded into another. Two flavors --
# forced (annex, and a stability collapse mid-war -- see engine.py) and
# peaceful (propose_accession) -- share the same merge mechanics but differ
# in transfer efficiency (conquest is wasteful; a voluntary union isn't)
# and in whether the rest of the world reacts with alarm.
ANNEX_ECONOMY_TRANSFER = 0.5
ANNEX_MILITARY_TRANSFER = 0.3
ANNEX_RESOURCE_TRANSFER = 0.5
ANNEX_STABILITY_HIT = -10
ANNEX_OPINION_HIT = -5
ANNEX_RIVAL_RELATION_HIT = -15

ACCESSION_ECONOMY_TRANSFER = 0.8
ACCESSION_MILITARY_TRANSFER = 0.8
ACCESSION_RESOURCE_TRANSFER = 0.8
ACCESSION_OPINION_BOOST = 5


def absorb_nation(world: World, conqueror, absorbed, *, peaceful: bool) -> None:
    """Merge `absorbed` into `conqueror` and erase `absorbed` from the
    world. Used by _resolve_annex, _resolve_propose_accession, and by
    engine._check_collapses (a stability collapse that happens to a
    nation still at war becomes annexation by the strongest enemy, not
    erasure)."""
    econ_frac = ACCESSION_ECONOMY_TRANSFER if peaceful else ANNEX_ECONOMY_TRANSFER
    mil_frac = ACCESSION_MILITARY_TRANSFER if peaceful else ANNEX_MILITARY_TRANSFER
    res_frac = ACCESSION_RESOURCE_TRANSFER if peaceful else ANNEX_RESOURCE_TRANSFER

    conqueror.economy += absorbed.economy * econ_frac
    conqueror.economic_potential += absorbed.economic_potential * econ_frac
    conqueror.military += absorbed.military * mil_frac
    for r in absorbed.resources:
        conqueror.resources[r] = conqueror.resources.get(r, 0.0) + absorbed.resources.get(r, 0.0) * res_frac

    if peaceful:
        conqueror.public_opinion += ACCESSION_OPINION_BOOST
    else:
        conqueror.stability += ANNEX_STABILITY_HIT
        conqueror.public_opinion += ANNEX_OPINION_HIT
        condemners = 0
        for other in world.alive_nations():
            # Bug fix: see the matching comment in _resolve_modify_constitution
            # -- this used to include every background nation too, silently
            # engaging the conqueror with ~180 of them on every forced
            # annexation.
            if other.id in (conqueror.id, absorbed.id) or other.is_background:
                continue
            if other.government_type in ("democracy", "parliamentary"):
                _shift_relations(other, conqueror, ANNEX_RIVAL_RELATION_HIT)
                condemners += 1
        if condemners:
            world.log(f"The world's democracies condemn {conqueror.name}'s annexation of {absorbed.name}.")

    absorbed.alive = False
    world.purge_nation_references(absorbed.id)
    conqueror.clamp_stats()


def _resolve_annex(world: World, order: Order) -> None:
    actor = world.get(order.actor_id)
    target = world.get(order.target_id)
    if target.id not in actor.at_war_with:
        return
    if not _is_annex_eligible(actor, target):
        world.log(_pick_variant(ANNEX_FAILED_MESSAGES, world.turn, actor.id, target.id).format(a=actor.name, t=target.name))
        return
    absorb_nation(world, actor, target, peaceful=False)
    world.log(_pick_variant(ANNEX_MESSAGES, world.turn, actor.id, target.id).format(a=actor.name, t=target.name))


def _resolve_propose_accession(world: World, order: Order) -> None:
    actor = world.get(order.actor_id)  # votes to dissolve into target
    target = world.get(order.target_id)  # absorbs actor
    mutual_relation = min(actor.relation(target.id), target.relation(actor.id))
    if mutual_relation < ACCESSION_RELATION_THRESHOLD:
        world.log(_pick_variant(ACCESSION_REJECTED_MESSAGES, world.turn, actor.id, target.id).format(a=actor.name, t=target.name))
        return
    absorb_nation(world, target, actor, peaceful=True)
    world.log(_pick_variant(ACCESSION_MESSAGES, world.turn, actor.id, target.id).format(a=actor.name, t=target.name))


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
    # Regression fix: a naive alliance-seeking sentence like "let's team up
    # with the UK in case anyone attacks us" used to score as an
    # *extraordinary demand* (worsening relations with the exact nation
    # the player wanted to befriend), purely because "attack" is a
    # hostile word and nothing offset it.
    "team up", "join forces", "protect", "defend", "partner", "ally",
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
    "annex": _resolve_annex,
    "propose_accession": _resolve_propose_accession,
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
