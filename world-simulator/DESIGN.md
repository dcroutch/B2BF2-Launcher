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

## Nation roster

28 nations covering every power widely considered "major" or "moderate" in
the mid-2026 snapshot (RESEARCH.md): 8 major powers (US, China, Russia,
India, Germany, UK, France, Japan) anchor the multipolar order; 20 moderate
regional powers (Brazil, Canada, Australia, South Korea, Indonesia, Turkey,
Saudi Arabia, Iran, Israel, Egypt, Nigeria, South Africa, Mexico, Pakistan,
Vietnam, Poland, Italy, Spain, Ukraine, Argentina) contest resources and
alliances around them. Starting relations, a pre-seeded NATO-style mutual
alliance bloc, an informal BRICS-style warm-relations bloc, real-world-flavored
rivalries (US-Russia, India-Pakistan, Israel-Iran, ...), and a few sanctions
regimes (US/UK/Germany embargo Russia, US embargoes Iran) give the world a
recognizable starting shape instead of a flat, arbitrary one. See
`worldsim/scenarios.py`.

## World reactions to player actions

The single biggest thing carried over from Pax Historia's feel -- "the world
reacts to what you do" -- without an LLM: every `declare_war`, `impose_embargo`,
and successful `propose_alliance` triggers a **third-party reaction pass**
(`orders._react_third_parties`) over every other living nation:

- Declare war on a nation -> its allies' relations toward you drop sharply
  (they condemn you) and your own allies' relations toward your target drop
  too (they back you) -- both logged as narrative event lines.
- Impose an embargo -> the target's allies cool toward you.
- Form a new alliance -> nations hostile to either new member grow warier of
  both (a new bloc reads as a threat to existing rivals).

These are fixed, deterministic rules (no randomness, no LLM), but because
they update `relations` immediately, they feed directly into every other
nation's next-turn AI scoring (`ai.score_order`) -- so a war you start can
visibly ripple into new alliances, embargoes, and eventually wars between
nations that were never involved in the original conflict. That's the
"emergent, reactive world" property, produced entirely by arithmetic.

## Tuning fixes (post-playtest)

A long simulated playtest surfaced three problems and each was fixed at the
mechanics level, not by special-casing:

- **Economies converging to a flat cap.** Every nation's economy monotonically
  climbed to the same global ceiling regardless of starting strength, erasing
  all differentiation. Fixed by giving each nation an `economic_potential`
  (a long-run ceiling, raised permanently by sustained `invest_economy`
  orders) and clamping `economy` to `economic_potential + 15`, not a flat 100
  -- so a nation's economic strength now reflects what it actually built up
  or lost to war/sanctions, not a shared cap.
- **Wars stuck in a permanent stalemate at zero military.** `sue_for_peace`
  only fired when one side was clearly losing, so two nations ground down to
  0 military each just stayed at war forever. Fixed by also accepting peace
  on mutual exhaustion (both militaries below 15).
- **War/peace flicker.** Even after peace, relations stayed catastrophically
  negative (nothing healed them), and `improve_relations` scored as "not
  worth it" once relations were very negative -- so nations flipped between
  declaring war and suing for peace almost every turn. Fixed three ways:
  relations now slowly heal toward neutral each turn when not at war;
  `improve_relations` no longer bottoms out to a fixed penalty at very
  negative relations; and a successful peace now sets a `truce_until` turn
  on both sides, blocking a fresh `declare_war` between them for
  `TRUCE_DURATION` (5) turns -- a real ceasefire instead of an instant
  re-declaration.

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

## Free text, the actor-lock guarantee, and chaotic input

Pax Historia's biggest departure from a fixed menu is free-text orders. We
now support that (`worldsim/parser.py`) without an LLM: a fixed, ordered
keyword table maps phrases to order types, and a nation-alias lookup
extracts the target. Two properties matter more than parsing accuracy:

1. **The player can never issue an order for another nation.**
   `parse_command(world, player_id, text)` has exactly one code path that
   constructs an `Order`, and it always passes `player_id` as `actor_id` --
   there is no branch anywhere that could set a different actor from text.
   On top of that structural guarantee, text whose apparent subject is a
   *different* nation ("China declares war on Russia") is detected (the
   other nation's name appears before any recognized verb) and downgraded
   to a `wildcard` order -- the player's own nation making a rhetorical
   statement about China, never an order China carries out.
2. **Nothing the player types is ever dropped or crashes the game.** If no
   keyword matches (chaotic, erratic, or simply unrealistic input -- "demand
   France refund the Louisiana Purchase") the input becomes a `wildcard`
   order. `_resolve_wildcard` (orders.py) scores the raw text against a
   small, fixed hostile/friendly word list and applies a proportionate,
   logged reaction: relations shift toward whatever nation was named,
   public opinion shifts if none was, and a strongly hostile wildcard
   (score >= 2) triggers the same ally-solidarity reaction real embargoes
   do. It's still 100% deterministic arithmetic -- just applied to
   unstructured input instead of a fixed order type.

## Public opinion, sectors, and commodities

- **Public opinion** (`Nation.public_opinion`) is a second domestic stat,
  independent of `stability`, that specific decisions move directly: an
  unprovoked war costs far more opinion than one against an already-hostile
  rival; the attacked side gets a short rally-around-the-flag boost; losing
  a war and suing for peace is a humiliation hit; a new alliance is a
  boost. It also drifts passively toward a target set by prosperity and
  stability. It then feeds back into stability's own drift target -- so a
  government that keeps winning "on paper" (strong economy) but has
  alienated its public still destabilizes and can still collapse, through
  the same single collapse path as everything else (no separate "the
  public revolts" special case).
- **Sectors** (`Nation.sectors`: agriculture, industry, energy, technology,
  services) are a second, slower lever on economy alongside
  `economic_potential`. `invest_sector` (reachable via free text, e.g.
  "invest in our technology sector", or the numbered menu) grows one
  sector and produces the raw material it depends on
  (`SECTOR_COMMODITY` in models.py).
- **Commodities and markets**: `RESOURCE_TYPES` covers five major raw
  materials (energy, food, metals, oil, tech components). `World.market_prices`
  is a single shared relative-price index per commodity, driven by total
  global stockpiles each turn (scarce -> price up, abundant -> price down).
  A nation's economy is nudged by whether it holds a surplus or deficit of
  each commodity relative to that shared price -- a real (if simplified)
  supply-and-demand market every nation trades in, not a per-nation number.
  `scenarios.py` seeds real-world-flavored starting profiles (Saudi
  Arabia/Russia lead oil, Japan/South Korea lead technology, Brazil/
  Argentina lead food, ...) so nations start economically differentiated,
  not just militarily/diplomatically.

## Testing strategy

Unit tests per module (models validity, each order's resolution effect in
isolation, AI scoring picks the expected order for constructed states, engine
runs N turns without crashing/producing out-of-range stats). No UI test needed
since CLI is a thin wrapper over `engine`.
