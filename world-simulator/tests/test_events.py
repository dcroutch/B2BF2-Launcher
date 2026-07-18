import random
import unittest

from worldsim.engine import (
    UNREST_EVENTS,
    UNREST_OPINION_THRESHOLD,
    UNREST_STABILITY_THRESHOLD,
    _maybe_trigger_minor_event,
)
from worldsim.models import Nation, World


def make_world(**overrides):
    a = Nation(id="a", name="A")
    for attr, value in overrides.get("a", {}).items():
        setattr(a, attr, value)
    return World(nations={"a": a})


UNREST_EVENT_NAMES = {name for name, *_ in UNREST_EVENTS}


class TestUnrestGatedByDomesticStats(unittest.TestCase):
    """Core requirement: civil unrest / corruption scandal must never fire
    on an otherwise-stable, well-governed nation -- only once its own
    stability or public opinion has already degraded."""

    def test_a_healthy_nation_never_gets_an_unrest_event(self):
        world = make_world(a={"stability": 90.0, "public_opinion": 90.0})
        nation = world.get("a")
        for seed in range(500):
            rng = random.Random(seed)
            nation.stability, nation.public_opinion = 90.0, 90.0
            before_log = len(world.event_log)
            _maybe_trigger_minor_event(world, nation, rng)
            if len(world.event_log) > before_log:
                last = world.event_log[-1]
                for name in UNREST_EVENT_NAMES:
                    self.assertNotIn(name.replace("_", " "), last)

    def test_a_struggling_nation_can_get_an_unrest_event(self):
        world = make_world(a={
            "stability": UNREST_STABILITY_THRESHOLD - 1,
            "public_opinion": UNREST_OPINION_THRESHOLD - 1,
        })
        nation = world.get("a")
        got_unrest = False
        for seed in range(500):
            rng = random.Random(seed)
            nation.stability = UNREST_STABILITY_THRESHOLD - 1
            nation.public_opinion = UNREST_OPINION_THRESHOLD - 1
            before_log = len(world.event_log)
            _maybe_trigger_minor_event(world, nation, rng)
            if len(world.event_log) > before_log:
                last = world.event_log[-1]
                if any(name.replace("_", " ") in last for name in UNREST_EVENT_NAMES):
                    got_unrest = True
                    break
        self.assertTrue(got_unrest, "expected at least one unrest event over 500 rolls while struggling")

    def test_stability_alone_below_threshold_is_enough_to_be_eligible(self):
        # Either stat crossing the threshold makes the nation "struggling"
        # -- doesn't require both at once.
        world = make_world(a={"stability": UNREST_STABILITY_THRESHOLD - 1, "public_opinion": 95.0})
        nation = world.get("a")
        got_unrest = False
        for seed in range(500):
            rng = random.Random(seed)
            nation.stability = UNREST_STABILITY_THRESHOLD - 1
            nation.public_opinion = 95.0
            before_log = len(world.event_log)
            _maybe_trigger_minor_event(world, nation, rng)
            if len(world.event_log) > before_log:
                last = world.event_log[-1]
                if any(name.replace("_", " ") in last for name in UNREST_EVENT_NAMES):
                    got_unrest = True
                    break
        self.assertTrue(got_unrest)


class TestEventMagnitudesAreRandomizedNotFixed(unittest.TestCase):
    def test_repeated_bumper_harvest_style_events_vary_in_magnitude(self):
        # Force events every roll by using a very struggling nation with a
        # high chance, then check the actual stability/opinion deltas
        # applied aren't always identical -- i.e. magnitudes are sampled
        # from a range, not fixed constants baked into a lookup table.
        deltas = set()
        for seed in range(200):
            world = make_world(a={"stability": 10.0, "public_opinion": 10.0})
            nation = world.get("a")
            rng = random.Random(seed)
            before = nation.stability
            _maybe_trigger_minor_event(world, nation, rng)
            if world.event_log:
                deltas.add(round(nation.stability - before, 4))
        # If magnitudes were fixed constants there'd be only a handful of
        # distinct values (one per event type); randomized ranges produce
        # far more distinct outcomes.
        self.assertGreater(len(deltas), 5)


class TestEventChanceRespondsToDomesticState(unittest.TestCase):
    def test_struggling_nations_see_events_more_often(self):
        healthy_events = 0
        struggling_events = 0
        for seed in range(1000):
            world = make_world(a={"stability": 90.0, "public_opinion": 90.0})
            rng = random.Random(seed)
            before = len(world.event_log)
            _maybe_trigger_minor_event(world, world.get("a"), rng)
            if len(world.event_log) > before:
                healthy_events += 1

        for seed in range(1000):
            world = make_world(a={"stability": 20.0, "public_opinion": 20.0})
            rng = random.Random(seed)
            before = len(world.event_log)
            _maybe_trigger_minor_event(world, world.get("a"), rng)
            if len(world.event_log) > before:
                struggling_events += 1

        self.assertGreater(struggling_events, healthy_events)


if __name__ == "__main__":
    unittest.main()
