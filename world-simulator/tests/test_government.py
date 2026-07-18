import random
import unittest

from worldsim.engine import _resolve_elections, game_status, run_turn
from worldsim.models import Nation, World
from worldsim.orders import Order, resolve_orders
from worldsim.parser import parse_command
from worldsim.scenarios import default_world


def make_world(**overrides):
    a = Nation(id="a", name="A")
    b = Nation(id="b", name="B")
    for attr, value in overrides.get("a", {}).items():
        setattr(a, attr, value)
    for attr, value in overrides.get("b", {}).items():
        setattr(b, attr, value)
    return World(nations={"a": a, "b": b})


class TestScheduledElections(unittest.TestCase):
    def test_popular_incumbent_is_reelected(self):
        world = make_world(a={"public_opinion": 70, "government_type": "democracy", "election_due_turn": 0})
        _resolve_elections(world)
        self.assertTrue(world.get("a").in_power)
        self.assertGreater(world.get("a").election_due_turn, 0)

    def test_unpopular_player_loses_the_election(self):
        world = make_world(a={"public_opinion": 20, "government_type": "democracy", "election_due_turn": 0, "is_player": True})
        _resolve_elections(world)
        self.assertFalse(world.get("a").in_power)

    def test_unpopular_ai_nation_gets_a_new_administration_not_removed_from_play(self):
        world = make_world(a={"public_opinion": 20, "government_type": "democracy", "election_due_turn": 0, "is_player": False})
        _resolve_elections(world)
        self.assertTrue(world.get("a").in_power)
        self.assertTrue(world.get("a").alive)
        self.assertGreater(world.get("a").public_opinion, 20)

    def test_authoritarian_government_never_holds_a_real_election(self):
        world = make_world(a={"public_opinion": 5, "government_type": "authoritarian", "election_due_turn": 0, "is_player": True})
        _resolve_elections(world)
        self.assertTrue(world.get("a").in_power)  # no election to lose

    def test_election_loss_ends_the_game_for_the_player(self):
        world = make_world(a={"public_opinion": 10, "government_type": "democracy", "election_due_turn": 0, "is_player": True})
        _resolve_elections(world)
        self.assertEqual(game_status(world, "a"), "loss")


class TestNoConfidenceVote(unittest.TestCase):
    def test_parliamentary_government_falls_under_extreme_sustained_displeasure(self):
        world = make_world(a={
            "government_type": "parliamentary", "public_opinion": 5, "stability": 10,
            "election_due_turn": 999, "is_player": True,
        })
        _resolve_elections(world)
        self.assertFalse(world.get("a").in_power)

    def test_presidential_democracy_cannot_be_no_confidence_voted_out(self):
        # Only parliamentary systems have this early-removal mechanism --
        # a fixed-term democracy must wait for its scheduled election.
        world = make_world(a={
            "government_type": "democracy", "public_opinion": 5, "stability": 10,
            "election_due_turn": 999, "is_player": True,
        })
        _resolve_elections(world)
        self.assertTrue(world.get("a").in_power)

    def test_mild_unpopularity_does_not_trigger_no_confidence(self):
        world = make_world(a={
            "government_type": "parliamentary", "public_opinion": 40, "stability": 50,
            "election_due_turn": 999, "is_player": True,
        })
        _resolve_elections(world)
        self.assertTrue(world.get("a").in_power)


class TestConstitutionOrder(unittest.TestCase):
    def test_coup_from_democracy_to_authoritarian_costs_opinion_and_stability(self):
        world = make_world(a={"government_type": "democracy", "public_opinion": 60, "stability": 60})
        resolve_orders(world, [Order("a", "modify_constitution", None, detail="authoritarian")])
        self.assertEqual(world.get("a").government_type, "authoritarian")
        self.assertLess(world.get("a").public_opinion, 60)
        self.assertLess(world.get("a").stability, 60)

    def test_coup_alarms_other_elected_governments(self):
        a = Nation(id="a", name="A", government_type="democracy")
        b = Nation(id="b", name="B", government_type="democracy")
        world = World(nations={"a": a, "b": b})
        before = world.get("b").relation("a")
        resolve_orders(world, [Order("a", "modify_constitution", None, detail="authoritarian")])
        self.assertLess(world.get("b").relation("a"), before)

    def test_democratization_schedules_a_fresh_election(self):
        world = make_world(a={"government_type": "authoritarian"})
        world.turn = 50
        resolve_orders(world, [Order("a", "modify_constitution", None, detail="democracy")])
        self.assertEqual(world.get("a").government_type, "democracy")
        self.assertGreater(world.get("a").election_due_turn, 50)

    def test_modify_constitution_has_no_target_and_cannot_affect_another_nation(self):
        a = Nation(id="a", name="A", government_type="democracy")
        b = Nation(id="b", name="B", government_type="democracy")
        world = World(nations={"a": a, "b": b})
        resolve_orders(world, [Order("a", "modify_constitution", None, detail="authoritarian")])
        self.assertEqual(world.get("a").government_type, "authoritarian")
        self.assertEqual(world.get("b").government_type, "democracy")  # untouched

    def test_reaffirming_the_same_government_type_is_a_no_op(self):
        world = make_world(a={"government_type": "democracy", "public_opinion": 60})
        resolve_orders(world, [Order("a", "modify_constitution", None, detail="democracy")])
        self.assertEqual(world.get("a").public_opinion, 60)


class TestParserCannotDictateOtherNationsGovernment(unittest.TestCase):
    """The exact scenario from the request: a declarative statement about a
    *different* nation's government/election outcome must never be taken as
    fact -- it can only ever become a rhetorical wildcard about that nation,
    never an actual change to it."""

    def test_asserted_vote_result_for_another_nation_does_not_change_its_government(self):
        world = default_world(player_id="usa")
        canada_before = world.get("canada").government_type
        order = parse_command(
            world, "usa",
            "With a vote of 85%, Canada instituted a communist constitution and government.",
        )
        self.assertEqual(order.actor_id, "usa")
        self.assertNotEqual(order.type, "modify_constitution")
        self.assertEqual(order.type, "wildcard")
        run_turn(world, [order], random.Random(1))
        self.assertEqual(world.get("canada").government_type, canada_before)

    def test_self_directed_constitution_change_still_works_normally(self):
        world = default_world(player_id="usa")
        order = parse_command(world, "usa", "We issue a new communist constitution")
        self.assertEqual(order.actor_id, "usa")
        self.assertEqual(order.type, "modify_constitution")
        self.assertEqual(order.detail, "authoritarian")

    def test_reversing_a_coup_via_natural_phrasing_is_recognized(self):
        world = default_world(player_id="uk")
        order = parse_command(world, "uk", "We restore parliamentary democracy and hold elections")
        self.assertEqual(order.actor_id, "uk")
        self.assertEqual(order.type, "modify_constitution")
        self.assertIn(order.detail, ("democracy", "parliamentary"))

    def test_asserted_fascist_constitution_for_uk_does_not_change_uk(self):
        world = default_world(player_id="usa")
        uk_before = world.get("uk").government_type
        order = parse_command(world, "usa", "The UK issues a fascist constitution effective immediately")
        self.assertEqual(order.actor_id, "usa")
        self.assertEqual(order.type, "wildcard")
        run_turn(world, [order], random.Random(1))
        self.assertEqual(world.get("uk").government_type, uk_before)


if __name__ == "__main__":
    unittest.main()
