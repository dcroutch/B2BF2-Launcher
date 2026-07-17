# Research

## Pax Historia — what it is

Pax Historia is a browser-based alternate-history grand strategy sandbox. Players
pick a nation and a historical (or fictional) starting point, then steer that
nation turn by turn using **free-text commands** ("invade Algeria", "propose a
trade pact with Brazil") instead of fixed menus. Every other country on the map
is an AI agent that reacts to the player's moves and to each other, generating
narrative and consequences on the fly rather than pulling from a scripted
outcome tree. Founded 2024, YC W2026, ~35k daily active users, 20M+ rounds
played, 4,000+ community presets. It runs almost 5M AI (LLM) requests/month
through OpenRouter to power the simulation.

Sources:
- https://paxhistoria.fandom.com/wiki/Pax_Historia
- https://wiki.paxhistoria.co/wiki/Getting_Started
- https://www.ycombinator.com/companies/pax-historia

### What makes it fun (the parts worth keeping)
- **Free-form agency**: you're not picking from 4 canned options, you're
  steering a whole nation with open-ended intents (military, diplomatic,
  economic, internal).
- **Living world**: other nations act on their own interests, form and break
  alliances, and react to what you do — the world doesn't wait for you.
- **Turn-based cadence**: a rhythm of "issue orders → see the world move →
  issue orders again" that's readable and low-friction.
- **Emergent narrative**: interesting stories come from mechanical interactions
  (an alliance snub triggers a war, a resource shortage triggers a coup), not
  from hand-authored plot.
- **Presets/scenarios**: a wide variety of starting worlds keeps replay value
  high.

### What we are explicitly NOT copying
Pax Historia's "AI nation" reactions and free-text parsing are implemented by
calling an LLM for every AI turn. That's the one piece we're leaving out per
the task requirements — no AI calls, no token limits, fully deterministic /
rule-based simulation that runs instantly and offline.

## Global geopolitics — high-level snapshot (mid-2026)

Used as flavor/reference for scenario design, not as a literal data feed:

- **Multipolar fragmentation**: a majority of analysts expect a "multipolar or
  fragmented order" over the next decade rather than a return to a single
  rules-based hegemonic system. Old post-WWII/post-Cold-War institutions are
  losing grip; blocs form around economic security instead.
- **US–China structural rivalry**: relations are "steady but antagonistic" —
  periodic trade truces and summits layered on top of a persistent contest
  over tariffs, export controls (esp. rare earths/semiconductors), and
  manufacturing overcapacity.
- **Geoeconomic tools as the main weapon**: tariffs, export controls, local
  content mandates, industrial subsidies, and strategic ownership stakes are
  used by governments to secure "economic security" — trade policy has become
  a security policy.
- **Regional flashpoints**: South Asia (India–Pakistan/Kashmir/water disputes)
  is flagged as the most combustible interstate-conflict risk; active wars
  continue in Eastern Europe (Ukraine), the Middle East, and parts of Latin
  America (Venezuela) and Asia.
- **Strategic resources as leverage**: critical minerals, rare earths,
  semiconductors, and biotech are treated as national-security assets, worth
  fighting over economically.
- **Climate & polarization as background stressors**: extreme weather and
  domestic societal polarization/misinformation compound interstate risk.

Sources:
- https://www.weforum.org/press/2026/01/global-risks-report-2026-geopolitical-and-economic-risks-rise-in-new-age-of-competition/
- https://www.stimson.org/2026/top-ten-global-risks-for-2026/
- https://www.cidob.org/en/publications/world-2026-ten-issues-will-shape-international-agenda

### Design takeaway
The game's simulation rules should reward/punish the same levers real states
use: military buildup & conquest, alliance/trade-bloc formation, resource
control (a small set of strategic resources), tariffs/embargoes, and internal
stability. That gives "geopolitically plausible" emergent stories without
needing an LLM to invent them.
