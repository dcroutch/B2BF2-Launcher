"""Deterministic, rule-based decision-making for non-player nations.

No machine learning and no network calls: each legal order is scored by a
pure function of visible world state, and the highest-scoring order wins.
Ties are broken by a seeded RNG so behavior is reproducible given a seed.
"""
from __future__ import annotations

import random

from .models import World
from .orders import Order, legal_orders


def score_order(world: World, order: Order) -> float:
    actor = world.get(order.actor_id)
    target = world.get(order.target_id) if order.target_id else None

    if order.type == "pass":
        return 0.1

    if order.type == "build_military":
        # More attractive when at war or facing a stronger rival.
        threat = max((world.get(t).military for t in actor.at_war_with), default=0)
        base = 1.0 + (threat - actor.military) * 0.05
        return base if actor.economy > 20 else -5

    if order.type == "invest_economy":
        # More attractive the weaker the economy is.
        return 3.0 + (60 - actor.economy) * 0.05

    if order.type == "improve_relations":
        # Prioritize neutral/slightly-negative relations we can still fix.
        rel = actor.relation(target.id)
        if rel < -50:
            return -1  # too far gone, not worth it
        return 1.0 + (50 - rel) * 0.02

    if order.type == "propose_alliance":
        mutual_relation = min(actor.relation(target.id), target.relation(actor.id))
        return 4.0 + mutual_relation * 0.05

    if order.type == "break_alliance":
        # Only attractive if relations have soured badly.
        rel = actor.relation(target.id)
        return (-rel - 40) * 0.1 if rel < -40 else -10

    if order.type == "trade_pact":
        mutual_relation = min(actor.relation(target.id), target.relation(actor.id))
        return 2.0 + mutual_relation * 0.03 + (60 - actor.economy) * 0.02

    if order.type == "impose_embargo":
        rel = actor.relation(target.id)
        return (-rel) * 0.05 if rel < -20 else -10

    if order.type == "declare_war":
        rel = actor.relation(target.id)
        if rel > -30:
            return -20  # not hostile enough to justify war
        power_edge = actor.military - target.military
        stability_ok = actor.stability > 40
        score = power_edge * 0.1 + (-rel) * 0.05
        return score if stability_ok else score - 15

    if order.type == "sue_for_peace":
        # Want peace when losing (weaker military) or stability is low.
        losing = actor.military < target.military * 0.8
        exhausted = actor.stability < 35
        return 6.0 if (losing or exhausted) else -5

    return -100  # unknown order types never win


def choose_order(world: World, actor_id: str, rng: random.Random) -> Order:
    """Pick the highest-scoring legal order for actor_id (seeded tie-break)."""
    candidates = list(legal_orders(world, actor_id))
    scored = [(score_order(world, o), rng.random(), o) for o in candidates]
    scored.sort(key=lambda t: (t[0], t[1]), reverse=True)
    return scored[0][2]
