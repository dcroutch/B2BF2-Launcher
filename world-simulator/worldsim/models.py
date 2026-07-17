"""Core data model: Nation and World."""
from __future__ import annotations

from dataclasses import dataclass, field

RESOURCE_TYPES = ("rare_earths", "energy", "food")

STAT_MIN, STAT_MAX = 0, 100


def clamp(value: float, lo: float = STAT_MIN, hi: float = STAT_MAX) -> float:
    return max(lo, min(hi, value))


@dataclass
class Nation:
    id: str
    name: str
    stability: float = 60.0
    military: float = 30.0
    economy: float = 50.0
    # Long-run economic ceiling this nation's economy drifts toward absent
    # active investment -- keeps nations differentiated instead of every
    # economy converging on the same global cap. Defaults to the starting
    # economy; sustained invest_economy orders raise it over time.
    economic_potential: float = None
    resources: dict = field(default_factory=lambda: {r: 50.0 for r in RESOURCE_TYPES})
    relations: dict = field(default_factory=dict)  # nation_id -> -100..100
    alliances: set = field(default_factory=set)
    trade_pacts: set = field(default_factory=set)
    embargoes_against: set = field(default_factory=set)  # nations this one embargoes
    at_war_with: set = field(default_factory=set)
    # nation_id -> turn number until which declaring war on that nation is
    # illegal (a ceasefire/armistice period after sue_for_peace succeeds).
    truce_until: dict = field(default_factory=dict)
    is_player: bool = False
    alive: bool = True

    def __post_init__(self):
        if self.economic_potential is None:
            self.economic_potential = self.economy

    def relation(self, other_id: str) -> float:
        return self.relations.get(other_id, 0.0)

    def clamp_stats(self) -> None:
        self.stability = clamp(self.stability)
        self.military = clamp(self.military)
        self.economic_potential = clamp(self.economic_potential)
        # Economy can run a bit above its long-run potential (a trade/war
        # boom or bust) but is capped relative to *that nation's* ceiling,
        # not a flat global 100 -- otherwise every nation's short-term
        # booms eventually stack up to the same uniform cap regardless of
        # how strong its underlying economy actually is.
        self.economy = clamp(self.economy, 0, self.economic_potential + 15)
        for r in RESOURCE_TYPES:
            self.resources[r] = clamp(self.resources.get(r, 0.0), 0, 200)
        for other_id in self.relations:
            self.relations[other_id] = clamp(self.relations[other_id], -100, 100)


@dataclass
class World:
    nations: dict  # id -> Nation
    turn: int = 0
    event_log: list = field(default_factory=list)
    seed: int = 0

    def alive_nations(self):
        return [n for n in self.nations.values() if n.alive]

    def get(self, nation_id: str) -> Nation:
        return self.nations[nation_id]

    def log(self, message: str) -> None:
        self.event_log.append(f"[T{self.turn}] {message}")
