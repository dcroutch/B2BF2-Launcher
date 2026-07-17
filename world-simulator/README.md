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

```
cd world-simulator
python3 run.py
```

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
- `tests/` — unit tests per module.
