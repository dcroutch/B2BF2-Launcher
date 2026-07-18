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
5. Random minor events (seeded, magnitude-randomized within a range —
   see "Minor events" below) can nudge stability/resources (drought,
   discovery, unrest) — small, bounded, always logged. Unrest-flavored
   events (civil unrest, corruption scandal) are only ever eligible for a
   nation whose own stability or public opinion has already degraded
   below a threshold; a stable, well-governed nation cannot draw one.
6. Win/lose/continue check; log turn summary; increment turn counter.

## Minor events: not fixed, gated by domestic state, not predictable

`engine._maybe_trigger_minor_event` replaced an earlier flat design (a
fixed 8% chance, then `random.choice` over one flat tuple of 8 events
with hardcoded deltas) that had two problems: (1) civil unrest and
corruption scandal could hit *any* nation regardless of how well it was
actually governed, including one at 90 stability/90 opinion, which reads
as arbitrary rather than a consequence of anything; (2) every occurrence
of "the same" event applied an identical, hardcoded delta, so a min-maxing
player replaying the same opening moves with the same seed would see
bit-for-bit identical outcomes forever.

Now:
- **Unrest gating**: `UNREST_EVENTS` (civil_unrest, corruption_scandal)
  only enter the roll's pool when `nation.stability < UNREST_STABILITY_THRESHOLD`
  (40) or `nation.public_opinion < UNREST_OPINION_THRESHOLD` (40) --
  i.e. the nation is already, demonstrably struggling as a result of
  whatever choices (player or AI) got it there. `POSITIVE_EVENTS` and the
  weather/supply-shock `NEUTRAL_EVENTS` (drought) remain available to
  everyone, since a drought isn't a verdict on governance quality the way
  unrest is.
- **State-responsive chance, not a flat coin flip**: the overall chance of
  *any* event this turn is `BASE_EVENT_CHANCE` (6%), bumped by
  `STRUGGLING_EVENT_CHANCE_BONUS` (+5%) when the nation is already
  struggling -- more is happening to a nation in domestic trouble, not
  just worse things when something does happen.
- **Randomized magnitude**: every event's stability/opinion/resource
  deltas are now `(lo, hi)` ranges sampled via `rng.uniform(...)`, not
  fixed constants -- no two occurrences of "the same" event play out
  identically, even across an otherwise-identical replay.

This resolution mechanism is still fully deterministic given a seed +
identical actions (a hard requirement for testability), but the *seed
itself* is no longer fixed in either front end: `cli.py` used to
hardcode `seed = 42`, meaning literally every terminal session with the
same opening moves saw the exact same AI behavior and events forever --
a memorizable, forced-optimal script rather than a world that responds to
choices plus genuine randomness. It now draws a fresh seed
(`secrets.randbelow`) per session, matching what `web.py` already did.

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

There is no turn cap. `game_status` (engine.py) no longer accepts a
`max_turns` parameter and never forces a win/loss purely because the turn
counter reached some number -- a prior version did ("strongest at turn
100 wins"), which meant the game could hand out an artificial verdict
completely disconnected from what actually happened in play. The game now
runs until one of exactly three things happens:

- **Loss**: the player's nation collapses (stability 0, `alive = False`)
  or its government falls (election defeat, a parliamentary no-confidence
  vote, or being annexed/acceded away -- all surfaced through `in_power`/
  `alive`, see the government and conquest sections above).
- **Win**: the player is the sole surviving nation (`len(alive_nations())
  == 1`) -- i.e. actual conquest of everyone else, now reachable via the
  annexation/collapse-during-war/civil-war mechanics above.
- **Voluntary end**: the player types `quit`/`exit`/`retire`/etc. at the
  CLI prompt. This is handled entirely in `cli.py` (`get_player_order`
  returns `None` as a sentinel) -- it's a UI-level choice, not a
  world-state outcome, so it's reported separately ("GAME ENDED") rather
  than as a win or loss verdict.

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
    parser.py       # deterministic free-text -> Order parser
    web.py          # stdlib WSGI JSON API + embedded single-page UI
  tests/
    test_models.py
    test_orders.py
    test_ai.py
    test_engine.py
    test_web.py
  run.py            # entry point: python run.py (terminal)
  run_web.py        # entry point: python run_web.py (browser)
```

## Web app (worldsim/web.py)

Same engine, a different front end -- no game logic lives in this file,
only request handling and JSON/HTML serialization. Deliberately built on
just the standard library (`wsgiref.simple_server`, `http.cookies`,
`json`) rather than a framework like Flask, since the rest of the project
has zero external dependencies and this shouldn't be the exception.

- **Session model**: each browser gets an httponly cookie
  (`con_sid`) minted by `POST /api/new`; the actual `World`/`Random`/
  `player_id` live server-side in an in-memory `SESSIONS` dict keyed by
  that cookie value. Nothing about game state is trusted from the client
  beyond the order text/menu index -- the same trust boundary the CLI has,
  just over HTTP instead of stdin.
- **Endpoints**: `GET /` (the page), `GET /api/nations`, `POST /api/new`,
  `GET /api/state`, `POST /api/menu`, `POST /api/order` (either `{"text":
  ...}` through the same `parser.parse_command` the CLI uses, or
  `{"index": N}` against the same `legal_orders` list the menu came from),
  `POST /api/quit`. A finished game (`game_status` returns non-`None`) or
  an explicit quit both clear the session server-side.
- **Log delivery**: `event_log` is returned incrementally -- each session
  tracks a `log_cursor` (how much of `world.event_log` the client has
  already seen) so repeated polling/turns don't resend the whole growing
  log every time.
- **Routing fix found while testing**: the first version required an
  active session for *any* unrecognized path before checking whether the
  path was even a real route, so `GET /anything-typoed` returned "no
  active game" (400) instead of 404. Fixed by checking path/method against
  an explicit set of session-requiring routes first; everything else
  (including typos) now correctly 404s regardless of session state. Caught
  by `tests/test_web.py::TestIndexPage::test_unknown_path_is_404`.

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

## Government, elections, and checks and balances

- **Three government types** (`Nation.government_type`): `democracy`
  (fixed-term, presidential-style — can only be removed at a scheduled
  election), `parliamentary` (fixed-term elections *plus* an early-removal
  check-and-balance), `authoritarian` (no real elections at all).
- **Scheduled elections** (`engine._resolve_elections` / `_hold_election`):
  every elected government faces an election on `election_due_turn` (every
  `ELECTION_TERM_LENGTH` = 20 turns). The outcome is fully legible to the
  player: win if `public_opinion >= 50` at that moment, lose otherwise --
  no hidden randomness. For the player, losing sets `in_power = False`,
  which `game_status` treats as a loss condition distinct from the
  stability-collapse path (a nation can lose an election while perfectly
  stable and prosperous). For AI nations, a loss just installs a new
  administration with a reset approval rating and keeps the nation in play
  -- governments turn over in the background all game, not just the
  player's.
- **Parliamentary no-confidence** (`_resolve_elections`'s `elif` branch):
  only `parliamentary` systems can fall *between* elections, and only under
  genuinely extreme, simultaneous distress (`public_opinion < 15` and
  `stability < 25`) -- this is the "checks and balances remove the ruling
  power under extreme displeasure" mechanic, deliberately scoped tighter
  than a scheduled election loss so it can't be triggered by one bad turn.
  A `democracy` (presidential system) has no equivalent early-removal path
  by design -- modeling impeachment realistically was out of scope, so a
  presidential government simply serves out its term.
- **`modify_constitution`** (self-only order, no `target_id` at all --
  see below) lets a government change its own type: abolishing an elected
  government for `authoritarian` rule is modeled as a coup (large
  opinion/stability hit, every other elected government's relations toward
  the actor cool -- reusing `_shift_relations`, not a new reaction
  channel); adopting an elected constitution schedules a fresh election
  term; a reform between `democracy` and `parliamentary` is minor.

### The player cannot dictate outcomes for another nation by asserting them

This generalizes the actor-lock guarantee from free text
("declare war") to free text asserting *facts*
("with a vote of 85%, Canada instituted a communist constitution"). Two
things make this safe by construction, not by pattern-matching harder:

1. `modify_constitution` has no `target_id` -- there is no code path,
   parser bug, or malformed input that can make it change any nation's
   government except the actor's own, because the concept of "a different
   target" doesn't exist for this order type.
2. The parser's existing impersonation guard (a different nation named
   before any recognized verb -> downgrade to `wildcard`) already covers
   declarative "fact" statements about other nations, since it fires on
   *any* verb match, including `modify_constitution`'s. "Canada instituted
   a communist constitution" names Canada before the constitution-flavored
   keywords, so it becomes a wildcard rhetorical statement toward Canada
   (logged, sentiment-scored, relation-shifting) -- never an actual change
   to Canada's `government_type`. See
   `tests/test_government.py::TestParserCannotDictateOtherNationsGovernment`.

Crucially, the guard keys off *which nation is named*, not *whether a
nation is named at all*: `earliest_id != player_id` is the actual
condition. So "With a vote of 85% of the population, Canada enacts a
communist government" while playing as Canada does **not** trigger the
guard (`earliest_id == player_id`) and resolves to a real
`modify_constitution` order -- the claimed 85% is just flavor text in
`Order.detail`'s raw string, never parsed into a number or used anywhere;
the fixed coup penalty and reactions apply exactly as if the player had
said "we impose authoritarian rule." The same sentence with a *different*
nation playing still gets blocked, since then `earliest_id` (Canada) does
differ from `player_id`. See
`TestSelfDirectedRegimeChangeWithPopulationFraming` in the same file.

## Sovereignty changes: conquest, annexation, civil war, accession

A prior full-game playthrough reached turn-cap dominance but never true
conquest, because there was no mechanic for one nation to actually absorb
another -- wars only ever caused temporary attrition that recovered once
a ceasefire landed. This closes that gap with four related mechanics that
all funnel through one shared merge function.

### `absorb_nation` (orders.py)

A single function used by every path that removes a nation from the map
by folding it into another: `_resolve_annex`, `_resolve_propose_accession`,
and `engine._check_collapses`'s war-collapse branch. It takes a
`peaceful: bool` flag that controls transfer efficiency (conquest wastes
half of what it takes; a voluntary union keeps 80%) and whether the rest
of the world reacts with alarm (forced annexation alarms every other
democracy via `_shift_relations`; peaceful accession doesn't touch anyone
else's relations). It always: transfers a fraction of economy/economic_potential/
military/resources, sets `absorbed.alive = False`, and calls
`world.purge_nation_references(absorbed.id)` so no other nation is left
holding a stale alliance/trade-pact/war/embargo/truce reference to a
nation that no longer exists.

### Forced conquest: `annex`

Legal only against a nation the actor is already at war with *and* has
crushed decisively (`_is_annex_eligible`: target military under 15, or
actor's more than 3x the target's). This is deliberately the same
"crushed" threshold that triggers a losing side's own strong urge to sue
for peace -- which is exactly why the `sue_for_peace` bug fix below
mattered: without it, the losing side could always escape via peace
before the winner ever got a turn to annex.

### The `sue_for_peace` bug this all depended on fixing

`_resolve_sue_for_peace` checked `actor_winning = actor.military >
target.military * 1.3` where `actor` is *the nation asking for peace*.
Since the realistic asker is the losing side, `actor_winning` was nearly
always false, so peace nearly always succeeded -- meaning a decisively
dominant side could never press its advantage; the war just ended the
moment the loser asked, no matter how lopsided the fight was. Fixed to
check the *target's* (the side being asked, whose consent should actually
matter) dominance instead: `target_dominant = target.military >
actor.military * 1.3`. Now a losing side's peace offer can be rejected
("presses its advantage and rejects..."), which is what makes annexation
(and collapse-during-war annexation) reachable at all rather than
theoretical.

### Collapse-during-war becomes annexation, not erasure

`engine._check_collapses` used to just set `alive = False` on any nation
whose stability hit 0. Now: if that nation is still at war when it
collapses, the strongest nation among its `at_war_with` set (by military)
annexes it via `absorb_nation(..., peaceful=False)` instead. A nation that
collapses with no war in progress still just fails, unchanged. This is
what makes sustained warfare a *reliable* path to conquest -- you don't
have to time an explicit `annex` order perfectly; grinding an enemy down
across a long war eventually finishes the job on its own. Verified in a
400-turn simulation: Russia, fighting the whole NATO bloc after attacking
Poland, rejected multiple ceasefire offers while still dominant, then its
own stability collapsed from fighting on too many fronts at once, and the
strongest nation among its enemies (the US) automatically annexed it --
with a rebel faction (see below) having already broken off in the same
turn and surviving independently afterward.

### Civil war / rebel factions (`engine._maybe_trigger_civil_war`)

A nation with both stability and public opinion below extreme thresholds
(15 / 20) rolls a 12%-per-turn chance to fracture: a brand-new `Nation`
(`world.spawn_nation`) is created holding 30% of the parent's military,
economy, and resources; the parent keeps the other 70% plus an additional
stability/opinion shock for the trauma of the split. The rebel faction is
born at war with its parent and is otherwise a completely ordinary
nation from that point on -- no special-cased AI, no scripted rebel
behavior. It picks orders via the same `ai.score_order` everyone else
uses, meaning it can sue for peace, build alliances, invest in its
economy, or even vote to (re)join a nation later via `propose_accession`.
This is the "domestic fracturing into rebel zones" requirement: emergent,
not a one-off event.

### Peaceful accession (`propose_accession`)

The non-violent counterpart: legal only when *both* sides' relations
toward each other are already very high (>=70, checked both directions so
one side can't force it), a small nation can vote to dissolve into a
larger one. No target penalty, no international alarm, better transfer
efficiency than conquest -- modeling something like a plebiscite/merger
rather than a war of absorption. AI nations essentially never propose
this for themselves (scored -50 in `ai.py`, same pattern as
`modify_constitution`), keeping it a player-driven, deliberate choice
while remaining fully available to the player.

## Testing strategy

Unit tests per module (models validity, each order's resolution effect in
isolation, AI scoring picks the expected order for constructed states, engine
runs N turns without crashing/producing out-of-range stats). No UI test needed
since CLI is a thin wrapper over `engine`.
