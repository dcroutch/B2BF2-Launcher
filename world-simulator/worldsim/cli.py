"""Interactive terminal game loop. No AI/LLM calls: the world advances via
worldsim.engine, which is pure deterministic arithmetic, and player intent
is parsed by worldsim.parser's fixed keyword rules -- not a language model."""
from __future__ import annotations

import random

from .engine import game_status, run_turn
from .models import World
from .orders import Order, legal_orders
from .parser import parse_command
from .scenarios import default_world, list_nation_ids

VALID_NATION_IDS = set(list_nation_ids())

MAX_TURNS = 100


def print_status(world: World, player_id: str) -> None:
    p = world.get(player_id)
    print(f"\n=== Turn {world.turn} — {p.name} ({p.government_type}) ===")
    print(
        f"Stability {p.stability:.0f} | Military {p.military:.0f} | "
        f"Economy {p.economy:.0f} | Public opinion {p.public_opinion:.0f}"
    )
    if p.government_type != "authoritarian":
        turns_to_election = p.election_due_turn - world.turn
        print(f"Next election in {max(turns_to_election, 0)} turn(s) (win threshold: 50 approval)")
    print(f"Sectors: {{{', '.join(f'{k}: {v:.0f}' for k, v in p.sectors.items())}}}")
    print(f"Resources: {{{', '.join(f'{k}: {v:.0f}' for k, v in p.resources.items())}}}")
    if p.alliances:
        print(f"Allies: {', '.join(world.get(a).name for a in p.alliances)}")
    if p.at_war_with:
        print(f"At war with: {', '.join(world.get(a).name for a in p.at_war_with)}")
    other_summaries = []
    for n in world.alive_nations():
        if n.id == player_id:
            continue
        other_summaries.append(f"{n.name}(stab {n.stability:.0f}/mil {n.military:.0f}/econ {n.economy:.0f})")
    print("World: " + ", ".join(other_summaries))


def choose_player_order(world: World, player_id: str) -> Order:
    options = list(legal_orders(world, player_id))
    print("\nChoose an order:")
    for i, order in enumerate(options):
        if order.target_id:
            label = f"{order.type} -> {world.get(order.target_id).name}"
        elif order.detail:
            label = f"{order.type} ({order.detail})"
        else:
            label = order.type
        print(f"  {i}: {label}")
    while True:
        raw = input("Order number: ").strip()
        if raw.isdigit() and 0 <= int(raw) < len(options):
            return options[int(raw)]
        print("Invalid choice, try again.")


def get_player_order(world: World, player_id: str) -> Order:
    """Free text is the primary interface: type anything, including erratic
    or unrealistic statements ("demand a refund of the Louisiana Purchase")
    -- it always resolves to something. Type 'menu' for a numbered list of
    known, well-defined actions instead."""
    text = input("\nWhat does your nation do? (or 'menu' for a list): ").strip()
    if not text:
        return Order(player_id, "pass")
    if text.lower() == "menu":
        return choose_player_order(world, player_id)
    return parse_command(world, player_id, text)


def main() -> None:
    print("=== Concert of Nations ===")
    print("A deterministic, offline geopolitical strategy sim (no AI required).")
    print("Type what your nation does in plain English -- 'menu' lists known actions.")
    print("Available nations: " + ", ".join(list_nation_ids()))
    player_id = input("Choose your nation [usa]: ").strip() or "usa"
    while player_id not in VALID_NATION_IDS:
        print(f"Unknown nation '{player_id}'. Choose from: {', '.join(list_nation_ids())}")
        player_id = input("Choose your nation [usa]: ").strip() or "usa"
    seed = 42
    world = default_world(player_id=player_id, seed=seed)
    rng = random.Random(seed)

    status = None
    while status is None:
        print_status(world, player_id)
        order = get_player_order(world, player_id)
        run_turn(world, [order], rng)
        for line in world.event_log[-5:]:
            print(line)
        status = game_status(world, player_id, max_turns=MAX_TURNS)

    print(f"\n=== GAME OVER: {status.upper()} ===")


if __name__ == "__main__":
    main()
