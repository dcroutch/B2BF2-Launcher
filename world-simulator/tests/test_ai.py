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

    def test_declare_war_is_discouraged_by_an_existing_war(self):
        # Regression: a nation hostile to two neighbors at once (the
        # Russia/Ukraine/Poland shape) used to score a second war exactly
        # as favorably as the first, regardless of how the first war was
        # going -- reliably invading both within the first few turns of
        # every game. Same matchup, only difference is whether the actor
        # is already fighting a third nation it isn't yet beating.
        a = Nation(id="a", name="A", military=80, stability=80)
        b = Nation(id="b", name="B", military=40)
        c = Nation(id="c", name="C", military=75)  # a isn't winning decisively
        a.relations["b"] = -50
        a.relations["c"] = -70
        b.relations["a"] = -50
        c.relations["a"] = -70
        world = World(nations={"a": a, "b": b, "c": c})

        score_not_at_war = score_order(world, Order("a", "declare_war", "b"))

        a.at_war_with.add("c")
        c.at_war_with.add("a")
        score_already_at_war = score_order(world, Order("a", "declare_war", "b"))

        self.assertLess(score_already_at_war, score_not_at_war)
        self.assertLess(score_already_at_war, 0)

    def test_declare_war_still_possible_when_already_winning_decisively(self):
        # The penalty shouldn't make a second war categorically impossible
        # -- a nation that's already crushing its first opponent can still
        # rationally open a second front against a much weaker target.
        a = Nation(id="a", name="A", military=95, stability=80)
        b = Nation(id="b", name="B", military=10)
        c = Nation(id="c", name="C", military=5)  # a is dominating this war
        a.relations["b"] = -90
        a.relations["c"] = -90
        b.relations["a"] = -90
        c.relations["a"] = -90
        a.at_war_with.add("c")
        c.at_war_with.add("a")
        world = World(nations={"a": a, "b": b, "c": c})
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
