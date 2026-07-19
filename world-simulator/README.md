# Concert of Nations

A turn-based, deterministic geopolitical strategy sandbox inspired by
[Pax Historia](https://www.paxhistoria.co/) — pick a nation, issue orders,
watch a fragmented multipolar world of **28 nations** (all the powers
widely considered "major" or "moderate" — see the roster below) react — but
with **no AI/LLM dependency**. Every non-player nation is driven by a
scored, rule-based decision function (see `worldsim/ai.py`), and every war,
embargo, or new alliance triggers a deterministic **third-party reaction
pass** so allies and rivals shift their stance in response to what you
actually did (see `worldsim/orders.py::_react_third_parties`). The game runs
instantly and fully offline, with no token limits or network calls.

## Nation roster

**Major powers:** United States, China, Russia, India, Germany, United
Kingdom, France, Japan.

**Moderate powers:** Brazil, Canada, Australia, South Korea, Indonesia,
Turkey, Saudi Arabia, Iran, Israel, Egypt, Nigeria, South Africa, Mexico,
Pakistan, Vietnam, Poland, Italy, Spain, Ukraine, Argentina.

The starting world seeds a NATO-style mutual alliance bloc, an informal
BRICS-style warm-relations bloc, real-world-flavored rivalries (US-Russia,
India-Pakistan, Israel-Iran, ...), and a few sanctions regimes — so play
starts from a recognizable geopolitical shape.

See `RESEARCH.md` for background on Pax Historia and the geopolitical
snapshot that informed the design, and `DESIGN.md` for the full design doc.

## Play

**Terminal:**

```
cd world-simulator
python3 run.py
```

**Web app:**

```
cd world-simulator
python3 run_web.py
```

then open http://127.0.0.1:8000/ in a browser. This is a small stdlib-only
JSON API (`worldsim/web.py`, built on `wsgiref` — no Flask/Django, no
external dependencies) serving a single embedded HTML/CSS/JS page in front
of the exact same deterministic engine the CLI uses. Game state lives
server-side per browser session (an httponly cookie), so multiple people
can each play their own game against the same running server. Same rules
apply: free text or a menu, no AI/LLM anywhere, no turn cap.

Type what your nation does in plain English each turn — "invade Iran",
"embargo Russia", "invest in our technology sector", "propose an alliance
with Japan" — or type `menu` for a numbered list of well-defined actions.
Free text is parsed by a **fixed keyword list** (`worldsim/parser.py`), not
an LLM, so it's instant and deterministic; anything it doesn't recognize —
including deliberately unrealistic input like "demand France refund the
Louisiana Purchase" — still resolves to *something* via a sentiment-scored
`wildcard` reaction instead of being silently dropped.

**You can only ever act as your own nation.** The parser structurally
returns `Order(actor_id=player_id, ...)` no matter what the text says — "make
China declare war on Russia" cannot make China do anything; it's downgraded
to a rhetorical statement *by your own nation, about China*, never an order
carried out *by* China. See `tests/test_parser.py::TestActorLockGuarantee`.

All 27 other nations pick their own orders every turn using the same
deterministic scoring rules (`worldsim/ai.py`), seeded for reproducible runs.

**There is no turn cap.** The game runs until exactly one of three things
happens: you lose (your nation collapses, or your government falls to an
election defeat / no-confidence vote / annexation), you win by eliminating
every other nation, or you type `quit` (or `exit`/`retire`/...) to end the
session on your own terms — that's a UI-level choice, reported as "GAME
ENDED" rather than a win or loss verdict.

## Beyond the core loop

- **Public opinion** (`Nation.public_opinion`) is a distinct stat from
  stability: wars, embargoes suffered, humiliating peace terms, and even
  wildcard rhetoric shift it, and it feeds back into stability — a nation
  can be objectively prosperous and still destabilize if it governs against
  its own public.
- **Sectors and commodities**: each nation has five domestic sectors
  (agriculture, industry, energy, technology, services) and five raw
  materials (energy, food, metals, oil, tech components), seeded with
  real-world-flavored profiles (Saudi Arabia/Russia lead oil, Japan/South
  Korea lead technology, Brazil/Argentina lead food, ...). `invest_sector`
  grows a specific sector and its commodity.
- **Global commodity markets** (`World.market_prices`): each commodity's
  price is a shared, world-wide supply/demand index — a nation with a
  surplus of a scarce commodity benefits as an exporter; a nation short on
  it suffers as an importer. Everyone trades in the same market.
- **Government and elections** (`Nation.government_type`): every nation is a
  `democracy`, `parliamentary` system, or `authoritarian` regime.
  Democracies and parliamentary systems hold a scheduled election every 20
  turns — **lose one as the player and the game ends**; win and you're
  re-elected. Parliamentary systems can additionally fall early to a *vote
  of no confidence* under sustained extreme unpopularity (low approval
  *and* low stability at once) — authoritarian regimes hold neither and can
  only fall through an ordinary stability collapse. `modify_constitution`
  (e.g. "seize absolute power and establish a dictatorship", "restore
  parliamentary democracy") changes your *own* nation's government —
  abolishing an elected government for authoritarian rule costs a large
  public-opinion/stability hit and visibly alarms every other democracy in
  the world. **This order has no target — it is structurally impossible for
  it to change any nation's government but the actor's own.** A statement
  asserting an outcome for a *different* nation ("With a vote of 85%,
  Canada instituted a communist constitution") is never taken as fact; it's
  downgraded to the same rhetorical wildcard as any other impersonation
  attempt, and Canada's government is untouched. The exact same "X% of the
  population voted..." framing *does* still work as a real order when you
  are playing as that nation — only the claimed vote share is ignored (it's
  never parsed into `public_opinion` or used to skip the normal coup
  penalty); the underlying government change and its domestic/international
  reactions apply exactly as if you'd said it plainly — see
  `tests/test_government.py::TestParserCannotDictateOtherNationsGovernment`
  and `::TestSelfDirectedRegimeChangeWithPopulationFraming`.

## Conquest, annexation, civil war, and accession

Sovereignty is no longer permanent. There are four ways a nation stops
being an independent actor:

- **`annex`** — forced conquest. Only legal against a nation you're
  already at war with and have crushed decisively (its military under 15,
  or yours more than 3x theirs). Absorbs half its economy/resources and
  30% of its remaining military; costs you stability and public opinion,
  and every other democracy's relations toward you cool ("The world's
  democracies condemn X's annexation of Y").
- **Collapse-during-war** — a nation whose stability hits 0 *while still
  at war* is no longer just erased: the strongest enemy still fighting it
  annexes the wreckage automatically. Sustained war is now a real,
  reachable path to conquest, not just attrition that quietly resolves
  itself. (A nation that collapses with no war in progress still simply
  fails, as before.)
- **Civil war / rebel factions** — a nation governing badly enough for
  long enough (very low stability *and* very low public opinion at once)
  risks part of itself breaking away into an independent rebel faction — a
  brand-new `Nation`, born at war with its parent, that plays by the exact
  same rules as everyone else from that point on (can sue for peace, ally,
  grow, even eventually vote to rejoin via accession). Domestic fracturing
  is emergent, not scripted.
- **`propose_accession`** — peaceful, voluntary union. Only available
  between two nations with very high mutual relations (both sides, not
  just one); the smaller nation dissolves into the larger one at a much
  better transfer rate than conquest (80% vs. 50%), with no international
  alarm.
- **`invite_accession`** — the other direction of the same mechanic: a
  nation that is genuinely the stronger, more prosperous side of a
  high-trust pair can invite the weaker one to join it, instead of only
  ever being able to ask to join someone else. Same relation bar and
  transfer rate as `propose_accession`; AI nations will pursue it on
  their own (unlike `propose_accession`, it never costs them their own
  existence), and it's a genuine non-military win path for the player —
  build up the economy, keep relations warm, and friendly rivals can be
  drawn into voluntary union instead of conquered.

**Bug fixed as part of this**: `sue_for_peace` used to check whether the
*asker* was dominant before accepting a ceasefire — which is backwards,
since the losing side (the realistic asker) is essentially never dominant,
so peace always succeeded no matter how thoroughly they were being
crushed. It now checks whether the *target* (whose consent actually
matters) is dominant, so a decisively winning side can reject peace and
press its advantage toward annexation instead.

## Run tests

```
cd world-simulator
python3 -m unittest discover -s tests -v
```

## Layout

- `worldsim/models.py` — `Nation` / `World` data model (stats, sectors,
  commodities, market prices).
- `worldsim/orders.py` — the order menu (including `invest_sector` and the
  `wildcard` catch-all) and how each order resolves.
- `worldsim/parser.py` — deterministic free-text -> Order parser, with the
  actor-lock guarantee.
- `worldsim/ai.py` — deterministic scoring heuristics for AI-controlled nations.
- `worldsim/engine.py` — turn loop: gather orders, resolve, apply passive
  effects (war exhaustion, embargoes, public opinion, market prices, minor
  events), check win/loss.
- `worldsim/scenarios.py` — starting-world preset (data only).
- `worldsim/cli.py` — interactive terminal loop (free text, with a `menu` fallback).
- `worldsim/web.py` — stdlib-only WSGI JSON API + embedded single-page UI
  (`run_web.py` is the entry point).
- `tests/` — unit tests per module.
