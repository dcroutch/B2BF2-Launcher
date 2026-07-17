"""Interactive terminal game loop. No AI/LLM calls: the world advances via
worldsim.engine, which is pure deterministic arithmetic."""
from __future__ import annotations

import random

from .engine import game_status, run_turn
from .models import World
from .orders import Order, legal_orders
from .scenarios import default_world, list_nation_ids

VALID_NATION_IDS = set(list_nation_ids())

MAX_TURNS = 100


def print_status(world: World, player_id: str) -> None:
    p = world.get(player_id)
    print(f"\n=== Turn {world.turn} — {p.name} ===")
    print(f"Stability {p.stability:.0f} | Military {p.military:.0f} | Economy {p.economy:.0f}")
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
    # Trim the (very long) list for readability: show non-targeted orders
    # plus targeted orders against nations with the most notable relations.
    print("\nChoose an order:")
    for i, order in enumerate(options):
        target = f" -> {world.get(order.target_id).name}" if order.target_id else ""
        print(f"  {i}: {order.type}{target}")
    while True:
        raw = input("Order number: ").strip()
        if raw.isdigit() and 0 <= int(raw) < len(options):
            return options[int(raw)]
        print("Invalid choice, try again.")


def main() -> None:
    print("=== Concert of Nations ===")
    print("A deterministic, offline geopolitical strategy sim (no AI required).")
    print("Available nations: " + ", ".join(list_nation_ids()))
    player_id = input("Choose your nation [aurelia]: ").strip() or "aurelia"
    while player_id not in VALID_NATION_IDS:
        print(f"Unknown nation '{player_id}'. Choose from: {', '.join(list_nation_ids())}")
        player_id = input("Choose your nation [aurelia]: ").strip() or "aurelia"
    seed = 42
    world = default_world(player_id=player_id, seed=seed)
    rng = random.Random(seed)

    status = None
    while status is None:
        print_status(world, player_id)
        order = choose_player_order(world, player_id)
        run_turn(world, [order], rng)
        for line in world.event_log[-5:]:
            print(line)
        status = game_status(world, player_id, max_turns=MAX_TURNS)

    print(f"\n=== GAME OVER: {status.upper()} ===")


if __name__ == "__main__":
    main()
