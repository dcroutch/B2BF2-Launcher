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
        self.assertEqual(n.economy, 100)
        self.assertEqual(n.resources["food"], 200)

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
