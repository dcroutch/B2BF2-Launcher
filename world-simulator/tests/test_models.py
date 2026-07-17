import unittest

from worldsim.models import Nation, World, clamp


class TestClamp(unittest.TestCase):
    def test_clamp_within_range(self):
        self.assertEqual(clamp(50), 50)

    def test_clamp_above_max(self):
        self.assertEqual(clamp(150), 100)

    def test_clamp_below_min(self):
        self.assertEqual(clamp(-10), 0)

    def test_clamp_custom_bounds(self):
        self.assertEqual(clamp(250, 0, 200), 200)


class TestNation(unittest.TestCase):
    def test_default_relation_is_zero(self):
        n = Nation(id="a", name="A")
        self.assertEqual(n.relation("b"), 0)

    def test_clamp_stats_bounds_all_fields(self):
        n = Nation(id="a", name="A", stability=200, military=-50, economy=999)
        n.resources["food"] = 999
        n.clamp_stats()
        self.assertEqual(n.stability, 100)
        self.assertEqual(n.military, 0)
        # Economy is capped relative to this nation's own economic_potential
        # (clamped to 100), not a flat 100 -- see test_economy_ceiling_is_
        # relative_to_economic_potential for the differentiation this buys.
        self.assertEqual(n.economy, 115)
        self.assertEqual(n.resources["food"], 200)

    def test_economy_ceiling_is_relative_to_economic_potential(self):
        n = Nation(id="a", name="A", economy=40, economic_potential=40)
        n.economy = 1000
        n.clamp_stats()
        self.assertEqual(n.economy, 55)  # potential (40) + 15 headroom

    def test_clamp_stats_bounds_relations(self):
        n = Nation(id="a", name="A")
        n.relations["b"] = 500
        n.relations["c"] = -500
        n.clamp_stats()
        self.assertEqual(n.relations["b"], 100)
        self.assertEqual(n.relations["c"], -100)


class TestWorld(unittest.TestCase):
    def test_alive_nations_excludes_dead(self):
        a = Nation(id="a", name="A")
        b = Nation(id="b", name="B", alive=False)
        world = World(nations={"a": a, "b": b})
        self.assertEqual(world.alive_nations(), [a])

    def test_log_prefixes_turn(self):
        world = World(nations={}, turn=3)
        world.log("hello")
        self.assertEqual(world.event_log, ["[T3] hello"])


if __name__ == "__main__":
    unittest.main()
