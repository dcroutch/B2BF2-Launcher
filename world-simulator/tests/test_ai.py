import random
import unittest

from worldsim.ai import choose_order, score_order
from worldsim.models import Nation, World
from worldsim.orders import Order


def make_world(**overrides):
    a = Nation(id="a", name="A")
    b = Nation(id="b", name="B")
    for attr, value in overrides.get("a", {}).items():
        setattr(a, attr, value)
    for attr, value in overrides.get("b", {}).items():
        setattr(b, attr, value)
    return World(nations={"a": a, "b": b})


class TestScoreOrder(unittest.TestCase):
    def test_declare_war_scores_low_when_relations_fine(self):
        world = make_world()
        score = score_order(world, Order("a", "declare_war", "b"))
        self.assertLess(score, 0)

    def test_declare_war_scores_higher_with_hostility_and_power_edge(self):
        world = make_world(a={"military": 90, "stability": 80}, b={"military": 20})
        world.get("a").relations["b"] = -80
        score = score_order(world, Order("a", "declare_war", "b"))
        self.assertGreater(score, 0)

    def test_invest_economy_more_attractive_when_poor(self):
        rich = make_world(a={"economy": 90})
        poor = make_world(a={"economy": 10})
        rich_score = score_order(rich, Order("a", "invest_economy"))
        poor_score = score_order(poor, Order("a", "invest_economy"))
        self.assertGreater(poor_score, rich_score)

    def test_sue_for_peace_favored_when_losing(self):
        world = make_world(a={"military": 10}, b={"military": 90})
        world.get("a").at_war_with.add("b")
        score = score_order(world, Order("a", "sue_for_peace", "b"))
        self.assertGreater(score, 0)


class TestChooseOrder(unittest.TestCase):
    def test_choose_order_is_deterministic_given_seed(self):
        world1 = make_world()
        world2 = make_world()
        order1 = choose_order(world1, "a", random.Random(7))
        order2 = choose_order(world2, "a", random.Random(7))
        self.assertEqual(order1, order2)

    def test_choose_order_returns_legal_order(self):
        world = make_world()
        order = choose_order(world, "a", random.Random(1))
        self.assertEqual(order.actor_id, "a")


if __name__ == "__main__":
    unittest.main()
