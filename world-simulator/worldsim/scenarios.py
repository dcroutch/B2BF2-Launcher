"""Starting-world presets. Pure data (+ light seeding helpers), no turn logic.

The roster covers all nations widely considered "major" or "moderate" powers
in the mid-2026 geopolitical snapshot documented in RESEARCH.md: the major
powers anchor the multipolar order (US, China, Russia, India, Germany, UK,
France, Japan); the moderate powers are the regional heavyweights whose
alignment and resource base shape each region's balance of power.
"""
from __future__ import annotations

from .models import Nation, World

# Per-nation commodity/sector profiles for the nations most associated with a
# given raw material or industry in the real world -- everyone else keeps
# the flat 50/40 defaults. (nation_id -> {resource_or_sector: value})
RESOURCE_PROFILES = {
    "saudi_arabia": {"oil": 140},
    "russia": {"oil": 120, "energy": 130, "metals": 90},
    "usa": {"oil": 90, "tech_components": 110, "food": 90},
    "china": {"metals": 110, "tech_components": 100, "energy": 70},
    "australia": {"metals": 130, "food": 90},
    "canada": {"energy": 100, "food": 100, "metals": 90},
    "brazil": {"food": 120, "metals": 80},
    "iran": {"oil": 110, "energy": 90},
    "nigeria": {"oil": 100},
    "vietnam": {"food": 90},
    "argentina": {"food": 110},
    "south_korea": {"tech_components": 120},
    "japan": {"tech_components": 130},
    "germany": {"tech_components": 100, "metals": 80},
    "india": {"food": 90, "tech_components": 80},
}

SECTOR_PROFILES = {
    "usa": {"technology": 80, "services": 75, "industry": 60},
    "china": {"industry": 85, "technology": 70, "agriculture": 55},
    "japan": {"technology": 85, "industry": 65},
    "south_korea": {"technology": 80, "industry": 65},
    "germany": {"industry": 75, "technology": 65},
    "saudi_arabia": {"energy_sector": 90, "services": 50},
    "russia": {"energy_sector": 85, "industry": 60},
    "brazil": {"agriculture": 75, "industry": 45},
    "australia": {"agriculture": 65, "industry": 50},
    "canada": {"agriculture": 60, "energy_sector": 70},
    "india": {"services": 60, "agriculture": 55, "technology": 50},
    "nigeria": {"energy_sector": 60, "agriculture": 45},
    "vietnam": {"agriculture": 60, "industry": 55},
    "argentina": {"agriculture": 70},
}

# Real-world-flavored starting form of government per nation; unlisted
# nations default to "democracy" (presidential-style, fixed-term elections,
# no early no-confidence removal). Parliamentary systems can additionally
# be brought down early by a vote of no confidence under extreme, sustained
# public/stability distress; authoritarian systems hold no real elections
# at all -- an unpopular one can only fall through the ordinary stability
# collapse path.
GOVERNMENT_PROFILES = {
    "uk": "parliamentary",
    "germany": "parliamentary",
    "japan": "parliamentary",
    "india": "parliamentary",
    "canada": "parliamentary",
    "australia": "parliamentary",
    "israel": "parliamentary",
    "italy": "parliamentary",
    "spain": "parliamentary",
    "china": "authoritarian",
    "russia": "authoritarian",
    "saudi_arabia": "authoritarian",
    "iran": "authoritarian",
    "egypt": "authoritarian",
    "vietnam": "authoritarian",
}

# id, name, stability, military, economy (0-100 proxies, not literal GDP/army
# figures -- relative ordering is what matters for gameplay balance).
MAJOR_POWERS = [
    ("usa", "United States", 62, 85, 90),
    ("china", "China", 68, 80, 88),
    ("russia", "Russia", 55, 78, 45),
    ("india", "India", 60, 55, 62),
    ("germany", "Germany", 70, 40, 70),
    ("uk", "United Kingdom", 65, 50, 68),
    ("france", "France", 62, 52, 66),
    ("japan", "Japan", 72, 45, 72),
]

MODERATE_POWERS = [
    ("brazil", "Brazil", 52, 35, 50),
    ("canada", "Canada", 72, 30, 60),
    ("australia", "Australia", 74, 35, 58),
    ("south_korea", "South Korea", 68, 50, 65),
    ("indonesia", "Indonesia", 58, 30, 45),
    ("turkey", "Turkey", 50, 55, 42),
    ("saudi_arabia", "Saudi Arabia", 60, 50, 55),
    ("iran", "Iran", 48, 55, 35),
    ("israel", "Israel", 62, 65, 60),
    ("egypt", "Egypt", 45, 40, 32),
    ("nigeria", "Nigeria", 42, 30, 28),
    ("south_africa", "South Africa", 50, 25, 35),
    ("mexico", "Mexico", 55, 30, 42),
    ("pakistan", "Pakistan", 45, 50, 30),
    ("vietnam", "Vietnam", 60, 35, 40),
    ("poland", "Poland", 65, 40, 48),
    ("italy", "Italy", 58, 35, 55),
    ("spain", "Spain", 60, 30, 52),
    ("ukraine", "Ukraine", 40, 45, 25),
    ("argentina", "Argentina", 48, 25, 35),
]

DEFAULT_NATIONS = MAJOR_POWERS + MODERATE_POWERS

# A real-world-ish alliance bloc, pre-seeded as mutual Nation.alliances so
# the "attack one, anger them all" reaction mechanic has teeth from turn 0.
NATO_BLOC = ("usa", "uk", "france", "germany", "italy", "spain", "poland", "canada", "turkey")

# Loosely-aligned bloc: warm relations, but *not* a formal alliance -- a
# multipolar counterweight rather than a single unified front.
EASTERN_BLOC_RELATIONS = ("china", "russia", "india", "brazil", "south_africa")

# (nation_a, nation_b, relation) -- applied symmetrically. Approximates
# real-world alignment/tension at a glance; not a literal forecast.
SEED_RELATIONS = [
    ("usa", "russia", -55),
    ("usa", "china", -35),
    ("usa", "iran", -60),
    ("usa", "canada", 60),
    ("usa", "uk", 65),
    ("china", "japan", -20),
    ("china", "india", -15),
    ("china", "russia", 30),
    ("russia", "ukraine", -70),
    ("russia", "poland", -40),
    ("india", "pakistan", -65),
    ("israel", "iran", -75),
    ("saudi_arabia", "iran", -50),
    ("turkey", "israel", -20),
    ("south_korea", "japan", 20),
    ("brazil", "argentina", 25),
    ("egypt", "israel", 10),
]

# (embargoing_nation, target) -- real-world-flavored sanctions regimes,
# applied one-directionally like the impose_embargo order does.
SEED_EMBARGOES = [
    ("usa", "russia"),
    ("usa", "iran"),
    ("uk", "russia"),
    ("germany", "russia"),
]


def default_world(player_id: str = "usa", seed: int = 42) -> World:
    """A 28-nation multipolar world: eight major powers anchor the order,
    twenty moderate regional powers contest resources and alliances around
    them. No single hegemon -- several nations are close enough in strength
    that outcomes depend on the alliances and conflicts that form in play.
    """
    valid_ids = {n[0] for n in DEFAULT_NATIONS}
    if player_id not in valid_ids:
        raise ValueError(f"Unknown player_id: {player_id}")

    nations = {}
    for nid, name, stability, military, economy in DEFAULT_NATIONS:
        nation = Nation(
            id=nid,
            name=name,
            stability=float(stability),
            military=float(military),
            economy=float(economy),
            is_player=(nid == player_id),
            government_type=GOVERNMENT_PROFILES.get(nid, "democracy"),
        )
        for resource, value in RESOURCE_PROFILES.get(nid, {}).items():
            nation.resources[resource] = float(value)
        for sector, value in SECTOR_PROFILES.get(nid, {}).items():
            nation.sectors[sector] = float(value)
        nations[nid] = nation

    for i, a_id in enumerate(NATO_BLOC):
        for b_id in NATO_BLOC[i + 1:]:
            nations[a_id].alliances.add(b_id)
            nations[b_id].alliances.add(a_id)
            nations[a_id].relations[b_id] = 45
            nations[b_id].relations[a_id] = 45

    for i, a_id in enumerate(EASTERN_BLOC_RELATIONS):
        for b_id in EASTERN_BLOC_RELATIONS[i + 1:]:
            nations[a_id].relations[b_id] = nations[a_id].relation(b_id) + 20
            nations[b_id].relations[a_id] = nations[b_id].relation(a_id) + 20

    for a_id, b_id, relation in SEED_RELATIONS:
        nations[a_id].relations[b_id] = relation
        nations[b_id].relations[a_id] = relation

    for actor_id, target_id in SEED_EMBARGOES:
        nations[actor_id].embargoes_against.add(target_id)

    return World(nations=nations, seed=seed)


def list_nation_ids() -> list[str]:
    return [n[0] for n in DEFAULT_NATIONS]
