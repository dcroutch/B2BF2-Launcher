"""Interactive terminal game loop. No AI/LLM calls: the world advances via
worldsim.engine, which is pure deterministic arithmetic, and player intent
is parsed by worldsim.parser's fixed keyword rules -- not a language model."""
from __future__ import annotations

import random
import secrets
from typing import Optional

from .engine import TURN_LENGTH_MONTHS, advance_turns, game_status
from .models import World
from .orders import Order, is_engaged, legal_orders
from .parser import parse_commands
from .scenarios import default_world, list_nation_ids

VALID_NATION_IDS = set(list_nation_ids())

# The game has no turn cap: it runs until the player loses, wins by
# eliminating every other nation, or chooses to end it here.
QUIT_COMMANDS = {"quit", "exit", "end game", "end the game", "retire", "resign", "stop playing", "stop"}

# How many turns ("months") a single skip-ahead request can cover.
SKIP_OPTIONS = (1, 3, 6)


def print_status(world: World, player_id: str) -> None:
    p = world.get(player_id)
    print(f"\n=== Month {world.turn} — {p.name} ({p.government_type}) ===")
    print(
        f"Stability {p.stability:.0f} | Military {p.military:.0f} | "
        f"Economy {p.economy:.0f} | Public opinion {p.public_opinion:.0f}"
    )
    if p.government_type != "authoritarian":
        turns_to_election = p.election_due_turn - world.turn
        print(f"Next election in {max(turns_to_election, 0)} month(s) (win threshold: 50 approval)")
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
        # Background nations only show up here once actually engaged --
        # otherwise this line would list ~190 mostly-untouched reference
        # states every single turn.
        if n.is_background and not is_engaged(p, n):
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


def get_player_orders(world: World, player_id: str) -> Optional[list[Order]]:
    """Free text is the primary interface: type anything, including erratic
    or unrealistic statements ("demand a refund of the Louisiana Purchase")
    -- it always resolves to something. Separate several instructions for
    the same turn with a semicolon, a newline, or "and then" (e.g. "invest
    in energy; embargo Russia"). Type 'menu' for a numbered list of known,
    well-defined actions instead (always a single order), or 'quit' to end
    the session.

    Returns None to signal the player chose to end the game -- this is a
    UI-level choice handled entirely here, not a world-state outcome, so
    it never flows through game_status()."""
    text = input(
        "\nWhat does your nation do? (separate multiple instructions with ';', "
        "or 'menu' for a list, 'quit' to end): "
    ).strip()
    if not text:
        return [Order(player_id, "pass")]
    if text.lower() in QUIT_COMMANDS:
        return None
    if text.lower() == "menu":
        return [choose_player_order(world, player_id)]
    return parse_commands(world, player_id, text)


def get_skip_turns() -> int:
    raw = input(f"Skip ahead how many months? {SKIP_OPTIONS} [1]: ").strip()
    if not raw:
        return 1
    try:
        n = int(raw)
    except ValueError:
        return 1
    return n if n > 0 else 1


def main() -> None:
    print("=== Concert of Nations ===")
    print("A deterministic, offline geopolitical strategy sim (no AI required).")
    print(f"Each turn represents {TURN_LENGTH_MONTHS} month(s).")
    print("Type what your nation does in plain English -- 'menu' lists known actions.")
    print("Queue multiple instructions for the same turn with ';', and skip ahead several")
    print("months at once instead of stopping for input every turn.")
    print("Available nations: " + ", ".join(list_nation_ids()))
    player_id = input("Choose your nation [usa]: ").strip() or "usa"
    while player_id not in VALID_NATION_IDS:
        print(f"Unknown nation '{player_id}'. Choose from: {', '.join(list_nation_ids())}")
        player_id = input("Choose your nation [usa]: ").strip() or "usa"
    # A fresh random seed per session -- a hardcoded seed here would make
    # every replay of "the same" opening moves produce bit-for-bit
    # identical AI behavior and minor events, effectively handing players
    # one memorizable optimal script instead of a world that responds to
    # their choices plus genuine randomness.
    seed = secrets.randbelow(1_000_000)
    world = default_world(player_id=player_id, seed=seed)
    rng = random.Random(seed)

    status = None
    while status is None:
        print_status(world, player_id)
        orders = get_player_orders(world, player_id)
        if orders is None:
            print(f"\n=== GAME ENDED (month {world.turn}, by your choice) ===")
            print_status(world, player_id)
            return
        num_turns = get_skip_turns()
        digest = advance_turns(world, player_id, orders, num_turns, rng)
        print(f"\n--- {len(digest)} event(s) over the last {num_turns} month(s) ---")
        for line in digest:
            print(line)
        status = game_status(world, player_id)

    print(f"\n=== GAME OVER: {status.upper()} ===")


if __name__ == "__main__":
    main()
