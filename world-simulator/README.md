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

You'll pick a nation, then each turn choose one order (build military,
invest in the economy, improve relations, propose an alliance, impose an
embargo, declare war, sue for peace, ...). The other nine nations pick their
own orders using the same deterministic scoring rules, seeded for
reproducible runs.

## Run tests

```
cd world-simulator
python3 -m unittest discover -s tests -v
```

## Layout

- `worldsim/models.py` — `Nation` / `World` data model.
- `worldsim/orders.py` — the fixed order menu and how each order resolves.
- `worldsim/ai.py` — deterministic scoring heuristics for AI-controlled nations.
- `worldsim/engine.py` — turn loop: gather orders, resolve, apply passive
  effects (war exhaustion, embargoes, stability drift, minor events), check
  win/loss.
- `worldsim/scenarios.py` — starting-world preset (data only).
- `worldsim/cli.py` — interactive terminal loop.
- `tests/` — unit tests per module.
