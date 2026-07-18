"""Core data model: Nation and World."""
from __future__ import annotations

from dataclasses import dataclass, field

# Major raw materials/commodities a nation can hold, produce, and trade.
# Global market_prices on World track each commodity's relative scarcity.
RESOURCE_TYPES = ("energy", "food", "metals", "oil", "tech_components")

# Major domestic economic sectors. Their combined strength is a second,
# slower-moving input into a nation's economy alongside economic_potential --
# investing in a specific sector (via invest_sector) raises that sector and
# produces the commodity it depends on.
SECTOR_TYPES = ("agriculture", "industry", "energy_sector", "technology", "services")

# Which raw material each sector's output is tied to (services isn't
# materials-bound -- it's the "everything else" sector: finance, retail,
# government, etc.).
SECTOR_COMMODITY = {
    "agriculture": "food",
    "industry": "metals",
    "energy_sector": "energy",
    "technology": "tech_components",
    "services": None,
}

# Forms of government. "democracy" holds fixed-term elections; "parliamentary"
# also holds fixed-term elections but can additionally be brought down early
# by a vote of no confidence; "authoritarian" holds neither -- an unpopular
# authoritarian regime can only fall through the existing stability-collapse
# path, not the ballot box.
GOVERNMENT_TYPES = ("democracy", "parliamentary", "authoritarian")
ELECTED_GOVERNMENT_TYPES = ("democracy", "parliamentary")

# Turns between scheduled elections for elected governments.
ELECTION_TERM_LENGTH = 20

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
    # Domestic sentiment (0-100). Drifts with stability/prosperity and reacts
    # directly to specific player/AI decisions (wars, humiliating peace,
    # embargoes suffered, new alliances, ...). Feeds back into stability, so
    # a nation that governs against its own public eventually destabilizes
    # through the same collapse path as everything else -- no separate
    # "the public revolts" special case needed.
    public_opinion: float = 60.0
    # Domestic sector strength (0-100 each): agriculture, industry, energy,
    # technology, services. A second, slower lever on economy alongside
    # economic_potential -- see invest_sector.
    sectors: dict = field(default_factory=lambda: {s: 40.0 for s in SECTOR_TYPES})
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
    # Government/elections. "in_power" going False is a distinct end state
    # from "alive" going False: a nation can lose an election or be brought
    # down by a no-confidence vote while remaining perfectly stable and
    # economically intact -- it's a change of leadership, not a collapse.
    government_type: str = "democracy"
    election_due_turn: int = None
    in_power: bool = True

    def __post_init__(self):
        if self.economic_potential is None:
            self.economic_potential = self.economy
        if self.election_due_turn is None:
            self.election_due_turn = ELECTION_TERM_LENGTH

    def relation(self, other_id: str) -> float:
        return self.relations.get(other_id, 0.0)

    def clamp_stats(self) -> None:
        self.stability = clamp(self.stability)
        self.military = clamp(self.military)
        self.public_opinion = clamp(self.public_opinion)
        self.economic_potential = clamp(self.economic_potential)
        # Economy can run a bit above its long-run potential (a trade/war
        # boom or bust) but is capped relative to *that nation's* ceiling,
        # not a flat global 100 -- otherwise every nation's short-term
        # booms eventually stack up to the same uniform cap regardless of
        # how strong its underlying economy actually is.
        self.economy = clamp(self.economy, 0, self.economic_potential + 15)
        for s in SECTOR_TYPES:
            self.sectors[s] = clamp(self.sectors.get(s, 0.0))
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
    # Global relative price index per commodity (1.0 = baseline). Rises when
    # global stockpiles run scarce, falls when they're abundant; nations
    # holding a surplus of a commodity benefit when its price is high
    # (net exporters), nations short on it suffer (net importers) -- a real,
    # if simplified, supply-and-demand market shared by every nation.
    market_prices: dict = field(default_factory=lambda: {r: 1.0 for r in RESOURCE_TYPES})

    def alive_nations(self):
        return [n for n in self.nations.values() if n.alive]

    def get(self, nation_id: str) -> Nation:
        return self.nations[nation_id]

    def log(self, message: str) -> None:
        self.event_log.append(f"[T{self.turn}] {message}")
