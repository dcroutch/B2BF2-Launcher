import unittest

from worldsim.models import Nation, World
from worldsim.orders import Order, legal_orders, resolve_orders


def make_world(**overrides):
    a = Nation(id="a", name="A")
    b = Nation(id="b", name="B")
    for attr, value in overrides.get("a", {}).items():
        setattr(a, attr, value)
    for attr, value in overrides.get("b", {}).items():
        setattr(b, attr, value)
    return World(nations={"a": a, "b": b})


class TestOrderValidation(unittest.TestCase):
    def test_self_targeted_order_is_rejected(self):
        with self.assertRaises(ValueError):
            Order("a", "declare_war", "a")


class TestLegalOrders(unittest.TestCase):
    def test_declare_war_not_offered_if_already_at_war(self):
        world = make_world()
        world.get("a").at_war_with.add("b")
        world.get("b").at_war_with.add("a")
        types = [o.type for o in legal_orders(world, "a") if o.target_id == "b"]
        self.assertNotIn("declare_war", types)
        self.assertIn("sue_for_peace", types)

    def test_propose_alliance_requires_relation_threshold(self):
        world = make_world()
        types = [o.type for o in legal_orders(world, "a") if o.target_id == "b"]
        self.assertNotIn("propose_alliance", types)
        world.get("a").relations["b"] = 50
        world.get("b").relations["a"] = 50
        types = [o.type for o in legal_orders(world, "a") if o.target_id == "b"]
        self.assertIn("propose_alliance", types)

    def test_propose_alliance_not_offered_if_relation_one_sided(self):
        world = make_world()
        world.get("a").relations["b"] = 50
        world.get("b").relations["a"] = -10
        types = [o.type for o in legal_orders(world, "a") if o.target_id == "b"]
        self.assertNotIn("propose_alliance", types)


class TestResolveOrders(unittest.TestCase):
    def test_declare_war_sets_mutual_war_state(self):
        world = make_world()
        resolve_orders(world, [Order("a", "declare_war", "b")])
        self.assertIn("b", world.get("a").at_war_with)
        self.assertIn("a", world.get("b").at_war_with)
        self.assertLess(world.get("a").relation("b"), 0)

    def test_improve_relations_is_mutual(self):
        world = make_world()
        resolve_orders(world, [Order("a", "improve_relations", "b")])
        self.assertEqual(world.get("a").relation("b"), 8)
        self.assertEqual(world.get("b").relation("a"), 8)

    def test_propose_alliance_fails_below_threshold(self):
        world = make_world()
        resolve_orders(world, [Order("a", "propose_alliance", "b")])
        self.assertNotIn("b", world.get("a").alliances)

    def test_propose_alliance_succeeds_when_mutual_high_relations(self):
        world = make_world()
        world.get("a").relations["b"] = 50
        world.get("b").relations["a"] = 50
        resolve_orders(world, [Order("a", "propose_alliance", "b")])
        self.assertIn("b", world.get("a").alliances)
        self.assertIn("a", world.get("b").alliances)

    def test_declare_war_breaks_existing_alliance(self):
        world = make_world()
        world.get("a").alliances.add("b")
        world.get("b").alliances.add("a")
        resolve_orders(world, [Order("a", "declare_war", "b")])
        self.assertNotIn("b", world.get("a").alliances)

    def test_sue_for_peace_rejected_when_actor_dominant(self):
        world = make_world(a={"military": 90}, b={"military": 10})
        world.get("a").at_war_with.add("b")
        world.get("b").at_war_with.add("a")
        resolve_orders(world, [Order("a", "sue_for_peace", "b")])
        self.assertIn("b", world.get("a").at_war_with)

    def test_sue_for_peace_accepted_when_not_dominant(self):
        world = make_world(a={"military": 40}, b={"military": 40})
        world.get("a").at_war_with.add("b")
        world.get("b").at_war_with.add("a")
        resolve_orders(world, [Order("a", "sue_for_peace", "b")])
        self.assertNotIn("b", world.get("a").at_war_with)

    def test_build_military_converts_economy(self):
        world = make_world(a={"economy": 50, "military": 10})
        resolve_orders(world, [Order("a", "build_military", None)])
        self.assertLess(world.get("a").economy, 50)
        self.assertGreater(world.get("a").military, 10)

    def test_resolution_order_diplomacy_before_military(self):
        # An alliance formed this turn should still be broken by a
        # simultaneous declare_war on the same target (military resolves
        # after diplomacy, per PRIORITY), proving priority ordering works.
        world = make_world()
        world.get("a").relations["b"] = 50
        world.get("b").relations["a"] = 50
        resolve_orders(world, [
            Order("a", "propose_alliance", "b"),
            Order("a", "declare_war", "b"),
        ])
        self.assertNotIn("b", world.get("a").alliances)
        self.assertIn("b", world.get("a").at_war_with)


if __name__ == "__main__":
    unittest.main()
