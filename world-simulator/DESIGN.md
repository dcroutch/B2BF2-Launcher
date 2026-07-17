# Design Doc — "Concert of Nations"

A deterministic, rule-based, turn-based geopolitical strategy game inspired by
Pax Historia's structure (pick a nation, issue orders, watch the world react)
but with **zero AI/LLM dependency**. Every non-player nation is driven by a
scored-priority rule engine, so there's no network call, no token budget, and
the game runs instantly, offline, and reproducibly (seeded RNG).

## Goals / non-goals

- Goal: turn-based sandbox, player picks a nation among N (default 10),
  issues 1+ orders per turn from a fixed action set, world advances a turn,
  AI nations pick their own orders via deterministic scoring heuristics.
- Goal: emergent stories from mechanics — wars, alliances, trade blocs,
  embargoes, coups — via simple, legible rules.
- Goal: no AI/LLM calls anywhere. No token limits, no network required.
- Non-goal: free-text command parsing (Pax Historia's NLP layer). We use a
  small fixed menu of order types instead — same "agency", no NLP needed.
- Non-goal: map rendering / graphics. Text/CLI first; a JSON world-state
  export is provided so a future UI can be layered on without touching sim
  logic.

## Core model

**Nation** attributes: `stability` (0-100), `military` (0-100),
`economy` (0-100, GDP proxy), `resources` (dict of strategic resource ->
stockpile: rare_earths, energy, food), `relations` (dict nation_id -> -100..100),
`alliances` (set of nation_ids), `at_war_with` (set of nation_ids),
`is_player` (bool).

**World**: list of nations, a turn counter, an RNG seeded for reproducibility,
and a global `event_log`.

## Turn loop

1. Player selects orders for their nation (1-2 per turn).
2. Each AI nation scores every legal order against its own state + relations
   and picks the highest-scoring one (ties broken by seeded RNG) — this is
   the "AI" layer, entirely arithmetic, no ML/LLM.
3. All orders resolve simultaneously (order type has a fixed resolution
   priority: diplomacy → economy → military, to avoid order-dependence bugs).
4. Passive effects apply: economy grows/shrinks from stability & resources,
   stability drifts toward a target based on war exhaustion / prosperity,
   wars inflict military and stability losses on both sides each turn a war
   persists, embargoes drain the target's economy.
5. Random minor events (seeded) can nudge stability/resources (drought,
   discovery, unrest) — small, bounded, always logged.
6. Win/lose/continue check; log turn summary; increment turn counter.

## Orders (the fixed action menu — replaces free-text)

| Order | Effect |
|---|---|
| `build_military` | economy -> military conversion |
| `invest_economy` | stability/resources -> economy growth |
| `improve_relations(target)` | relations[target] += delta |
| `propose_alliance(target)` | forms alliance if relations high enough |
| `break_alliance(target)` | ends alliance, relations hit |
| `impose_embargo(target)` | target economy drain, relations hit |
| `declare_war(target)` | starts war, big relations/stability hit |
| `sue_for_peace(target)` | ends war if both sides willing / one is losing badly |
| `trade_pact(target)` | ongoing economy boost for both while relations stay positive |
| `pass` | no-op, small stability regen |

Each AI nation's decision function scores every legal order using its state
(e.g. a nation with military >> a rival's and poor relations is likely to
`declare_war`; a nation with low economy prioritizes `invest_economy` or
`trade_pact`) — pure functions, unit-testable, deterministic given the RNG
seed.

## Victory / failure conditions (single-player framing)

- Player nation's stability hits 0 -> collapse (loss).
- Player conquers (reduces to 0 stability while at war and holds military
  superiority) enough rival nations, or survives N turns as the strongest
  economy/military -> win states, reported at run end. Kept intentionally
  simple; scenario presets can define custom win conditions later.

## Project layout

```
world-simulator/
  RESEARCH.md
  DESIGN.md
  README.md
  worldsim/
    __init__.py
    models.py       # Nation, World dataclasses
    orders.py       # Order definitions + resolution logic
    ai.py           # deterministic scoring-based AI decision function
    engine.py       # turn loop, passive effects, events
    scenarios.py    # starting-world presets (data, no logic)
    cli.py          # interactive terminal game loop
  tests/
    test_models.py
    test_orders.py
    test_ai.py
    test_engine.py
  run.py            # entry point: python run.py
```

## Testing strategy

Unit tests per module (models validity, each order's resolution effect in
isolation, AI scoring picks the expected order for constructed states, engine
runs N turns without crashing/producing out-of-range stats). No UI test needed
since CLI is a thin wrapper over `engine`.
