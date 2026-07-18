import unittest

from worldsim.models import Nation, World
from worldsim.orders import Order, resolve_orders


def make_world(**overrides):
    a = Nation(id="a", name="A")
    b = Nation(id="b", name="B")
    for attr, value in overrides.get("a", {}).items():
        setattr(a, attr, value)
    for attr, value in overrides.get("b", {}).items():
        setattr(b, attr, value)
    return World(nations={"a": a, "b": b})


class TestWildcardOrder(unittest.TestCase):
    def test_hostile_text_toward_target_cools_relations(self):
        world = make_world()
        resolve_orders(world, [Order("a", "wildcard", "b", detail="We demand tribute and threaten war")])
        self.assertLess(world.get("a").relation("b"), 0)

    def test_friendly_text_toward_target_warms_relations(self):
        world = make_world()
        resolve_orders(world, [Order("a", "wildcard", "b", detail="We send a gift and praise their friendship")])
        self.assertGreater(world.get("a").relation("b"), 0)

    def test_neutral_gibberish_toward_target_leaves_relations_unchanged(self):
        world = make_world()
        resolve_orders(world, [Order("a", "wildcard", "b", detail="purple elephants dance on the moon")])
        self.assertEqual(world.get("a").relation("b"), 0)

    def test_hostile_wildcard_with_no_target_dents_domestic_opinion(self):
        world = make_world()
        before = world.get("a").public_opinion
        resolve_orders(world, [Order("a", "wildcard", None, detail="threaten to destroy everything")])
        self.assertNotEqual(world.get("a").public_opinion, before)

    def test_strongly_hostile_wildcard_triggers_ally_solidarity_reaction(self):
        a = Nation(id="a", name="A")
        b = Nation(id="b", name="B")
        c = Nation(id="c", name="C")
        b.alliances.add("c")
        c.alliances.add("b")
        world = World(nations={"a": a, "b": b, "c": c})
        resolve_orders(world, [Order("a", "wildcard", "b", detail="attack invade destroy annex")])
        self.assertLess(world.get("c").relation("a"), 0)

    def test_wildcard_never_crashes_on_empty_text(self):
        world = make_world()
        resolve_orders(world, [Order("a", "wildcard", "b", detail="")])  # should not raise

    def test_wildcard_actor_is_never_the_named_target(self):
        # Structural sanity check on the Order itself.
        order = Order("a", "wildcard", "b", detail="anything")
        self.assertNotEqual(order.actor_id, order.target_id)


class TestPublicOpinion(unittest.TestCase):
    def test_unprovoked_war_costs_more_opinion_than_justified_war(self):
        justified = make_world(a={"stability": 60})
        justified.get("a").relations["b"] = -60
        justified.get("b").relations["a"] = -60
        resolve_orders(justified, [Order("a", "declare_war", "b")])

        unprovoked = make_world(a={"stability": 60})
        resolve_orders(unprovoked, [Order("a", "declare_war", "b")])

        self.assertLess(
            unprovoked.get("a").public_opinion,
            justified.get("a").public_opinion,
        )

    def test_attacked_nation_gets_rally_around_flag_boost(self):
        world = make_world()
        before = world.get("b").public_opinion
        resolve_orders(world, [Order("a", "declare_war", "b")])
        self.assertGreater(world.get("b").public_opinion, before)

    def test_embargoed_nation_loses_public_opinion(self):
        world = make_world()
        before = world.get("b").public_opinion
        resolve_orders(world, [Order("a", "impose_embargo", "b")])
        self.assertLess(world.get("b").public_opinion, before)

    def test_losing_side_suing_for_peace_is_a_humiliation_hit(self):
        # target (b) must not be dominant enough to reject the offer
        # outright (target.military <= actor.military * 1.3) but actor (a)
        # must still be behind enough to count as "losing" for the opinion
        # hit (actor.military < target.military * 0.8).
        world = make_world(a={"military": 100}, b={"military": 127})
        world.get("a").at_war_with.add("b")
        world.get("b").at_war_with.add("a")
        before = world.get("a").public_opinion
        resolve_orders(world, [Order("a", "sue_for_peace", "b")])
        self.assertNotIn("b", world.get("a").at_war_with)  # sanity: peace did succeed
        self.assertLess(world.get("a").public_opinion, before)


class TestSectorInvestment(unittest.TestCase):
    def test_invest_sector_raises_that_sector_and_its_commodity(self):
        world = make_world()
        world.get("a").economy = 60
        before_sector = world.get("a").sectors["technology"]
        before_resource = world.get("a").resources["tech_components"]
        resolve_orders(world, [Order("a", "invest_sector", None, detail="technology")])
        self.assertGreater(world.get("a").sectors["technology"], before_sector)
        self.assertGreater(world.get("a").resources["tech_components"], before_resource)

    def test_invest_sector_costs_economy(self):
        world = make_world()
        world.get("a").economy = 60
        resolve_orders(world, [Order("a", "invest_sector", None, detail="industry")])
        self.assertLess(world.get("a").economy, 60)

    def test_invest_sector_rejects_unknown_sector(self):
        with self.assertRaises(ValueError):
            Order("a", "invest_sector", None, detail="not_a_real_sector")

    def test_energy_sector_log_message_does_not_double_the_word_sector(self):
        world = make_world()
        world.get("a").economy = 60
        resolve_orders(world, [Order("a", "invest_sector", None, detail="energy_sector")])
        self.assertIn("invests in its energy sector.", world.event_log[-1])
        self.assertNotIn("sector sector", world.event_log[-1])


if __name__ == "__main__":
    unittest.main()
