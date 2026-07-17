"""Starting-world presets. Pure data, no simulation logic."""
from __future__ import annotations

from .models import Nation, World

DEFAULT_NATIONS = [
    # id, name, stability, military, economy
    ("aurelia", "Aurelia", 65, 40, 60),
    ("borealis", "Borealis", 55, 55, 45),
    ("cathay", "Cathay", 70, 60, 65),
    ("dunmoor", "Dunmoor", 50, 30, 40),
    ("elysia", "Elysia", 60, 25, 55),
    ("faroth", "Faroth", 45, 45, 35),
    ("gallant", "Gallant", 58, 35, 50),
    ("harrow", "Harrow", 62, 50, 48),
    ("ithaka", "Ithaka", 52, 20, 42),
    ("juno", "Juno", 68, 38, 58),
]


def default_world(player_id: str = "aurelia", seed: int = 42) -> World:
    """A 10-nation world loosely modeled on a multipolar, fragmenting order:
    no single hegemon, a couple of strong economies, several mid-tier powers
    contesting resources and alliances.
    """
    if player_id not in {n[0] for n in DEFAULT_NATIONS}:
        raise ValueError(f"Unknown player_id: {player_id}")

    nations = {}
    for nid, name, stability, military, economy in DEFAULT_NATIONS:
        nations[nid] = Nation(
            id=nid,
            name=name,
            stability=float(stability),
            military=float(military),
            economy=float(economy),
            is_player=(nid == player_id),
        )

    # Seed a few starting relationships so the world doesn't feel flat.
    nations["aurelia"].relations["borealis"] = -20
    nations["borealis"].relations["aurelia"] = -20
    nations["cathay"].relations["dunmoor"] = 30
    nations["dunmoor"].relations["cathay"] = 30
    nations["faroth"].relations["gallant"] = -35
    nations["gallant"].relations["faroth"] = -35

    return World(nations=nations, seed=seed)


def list_nation_ids() -> list[str]:
    return [n[0] for n in DEFAULT_NATIONS]
