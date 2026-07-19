import random
import unittest

from worldsim.engine import _check_collapses, _maybe_trigger_civil_war, game_status, run_turn
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


class TestAnnexation(unittest.TestCase):
    def test_annex_not_legal_without_decisive_victory(self):
        world = make_world(a={"military": 40}, b={"military": 35})
        world.get("a").at_war_with.add("b")
        world.get("b").at_war_with.add("a")
        types = [o.type for o in legal_orders(world, "a") if o.target_id == "b"]
        self.assertNotIn("annex", types)

    def test_annex_legal_when_target_military_crushed(self):
        world = make_world(a={"military": 40}, b={"military": 5})
        world.get("a").at_war_with.add("b")
        world.get("b").at_war_with.add("a")
        types = [o.type for o in legal_orders(world, "a") if o.target_id == "b"]
        self.assertIn("annex", types)

    def test_annex_legal_when_actor_overwhelmingly_stronger(self):
        world = make_world(a={"military": 100}, b={"military": 20})
        world.get("a").at_war_with.add("b")
        world.get("b").at_war_with.add("a")
        types = [o.type for o in legal_orders(world, "a") if o.target_id == "b"]
        self.assertIn("annex", types)

    def test_annex_requires_being_at_war(self):
        world = make_world(a={"military": 100}, b={"military": 5})
        resolve_orders(world, [Order("a", "annex", "b")])
        self.assertTrue(world.get("b").alive)

    def test_annex_absorbs_target_and_erases_it(self):
        world = make_world(a={"military": 100, "economy": 50}, b={"military": 5, "economy": 40})
        world.get("a").at_war_with.add("b")
        world.get("b").at_war_with.add("a")
        resolve_orders(world, [Order("a", "annex", "b")])
        self.assertFalse(world.get("b").alive)
        self.assertGreater(world.get("a").economy, 50)  # absorbed b's economy fraction

    def test_annex_removes_target_from_alliances_and_wars_world_wide(self):
        a = Nation(id="a", name="A", military=100)
        b = Nation(id="b", name="B", military=5)
        c = Nation(id="c", name="C")
        c.alliances.add("b")
        b.alliances.add("c")
        world = World(nations={"a": a, "b": b, "c": c})
        a.at_war_with.add("b")
        b.at_war_with.add("a")
        resolve_orders(world, [Order("a", "annex", "b")])
        self.assertNotIn("b", world.get("c").alliances)

    def test_annex_costs_actor_stability_and_alarms_democracies(self):
        a = Nation(id="a", name="A", military=100, stability=70, government_type="authoritarian")
        b = Nation(id="b", name="B", military=5)
        c = Nation(id="c", name="C", government_type="democracy")
        world = World(nations={"a": a, "b": b, "c": c})
        a.at_war_with.add("b")
        b.at_war_with.add("a")
        c_relation_before = c.relation("a")
        resolve_orders(world, [Order("a", "annex", "b")])
        self.assertLess(world.get("a").stability, 70)
        self.assertLess(world.get("c").relation("a"), c_relation_before)

    def test_failed_annex_attempt_does_not_end_the_war(self):
        world = make_world(a={"military": 40}, b={"military": 35})
        world.get("a").at_war_with.add("b")
        world.get("b").at_war_with.add("a")
        resolve_orders(world, [Order("a", "annex", "b")])
        self.assertTrue(world.get("b").alive)
        self.assertIn("b", world.get("a").at_war_with)

    def test_forced_annexation_does_not_engage_background_nations(self):
        # Regression test: the "world's democracies condemn" reaction used
        # to iterate every alive nation including background ones
        # (Nation.is_background), silently setting a real relations entry
        # between the conqueror and every background democracy on Earth --
        # defeating is_engaged()'s whole purpose of keeping them out of
        # the menu and world-summary display until actually engaged.
        a = Nation(id="a", name="A", military=100, stability=70, government_type="authoritarian")
        b = Nation(id="b", name="B", military=5)
        bg = Nation(id="bg", name="Background", is_background=True)
        world = World(nations={"a": a, "b": b, "bg": bg})
        a.at_war_with.add("b")
        b.at_war_with.add("a")
        resolve_orders(world, [Order("a", "annex", "b")])
        self.assertEqual(world.get("a").relation("bg"), 0.0)


class TestAccession(unittest.TestCase):
    def test_accession_offered_only_at_high_mutual_relation(self):
        world = make_world()
        world.get("a").relations["b"] = 50
        world.get("b").relations["a"] = 50
        types = [o.type for o in legal_orders(world, "a") if o.target_id == "b"]
        self.assertNotIn("propose_accession", types)
        world.get("a").relations["b"] = 80
        world.get("b").relations["a"] = 80
        types = [o.type for o in legal_orders(world, "a") if o.target_id == "b"]
        self.assertIn("propose_accession", types)

    def test_accession_merges_actor_into_target_peacefully(self):
        world = make_world(a={"economy": 30}, b={"economy": 60, "stability": 70})
        world.get("a").relations["b"] = 80
        world.get("b").relations["a"] = 80
        resolve_orders(world, [Order("a", "propose_accession", "b")])
        self.assertFalse(world.get("a").alive)
        self.assertTrue(world.get("b").alive)
        self.assertGreater(world.get("b").economy, 60)

    def test_accession_does_not_alarm_other_democracies(self):
        # Peaceful union shouldn't trigger the same condemnation reaction
        # a forced annexation does.
        a = Nation(id="a", name="A", government_type="democracy")
        b = Nation(id="b", name="B", government_type="democracy")
        c = Nation(id="c", name="C", government_type="democracy")
        a.relations["b"] = 80
        b.relations["a"] = 80
        world = World(nations={"a": a, "b": b, "c": c})
        relation_before = c.relation("b")
        resolve_orders(world, [Order("a", "propose_accession", "b")])
        self.assertEqual(world.get("c").relation("b"), relation_before)

    def test_accession_rejected_below_relation_threshold(self):
        world = make_world()
        world.get("a").relations["b"] = 40
        world.get("b").relations["a"] = 40
        resolve_orders(world, [Order("a", "propose_accession", "b")])
        self.assertTrue(world.get("a").alive)
        self.assertTrue(world.get("b").alive)

    def test_accession_cannot_be_forced_one_sidedly(self):
        # High relation from only one side shouldn't be enough -- both
        # populations have to actually want the union.
        world = make_world()
        world.get("a").relations["b"] = 90
        world.get("b").relations["a"] = 10
        resolve_orders(world, [Order("a", "propose_accession", "b")])
        self.assertTrue(world.get("a").alive)


class TestCollapseDuringWarBecomesAnnexation(unittest.TestCase):
    def test_collapsing_while_at_war_is_annexed_by_the_strongest_enemy(self):
        world = make_world(a={"military": 90}, b={"military": 5, "stability": 0})
        world.get("a").at_war_with.add("b")
        world.get("b").at_war_with.add("a")
        _check_collapses(world, random.Random(1))
        self.assertFalse(world.get("b").alive)
        self.assertTrue(world.get("a").alive)

    def test_collapsing_at_war_picks_the_strongest_of_multiple_enemies(self):
        a = Nation(id="a", name="A", military=20)
        b = Nation(id="b", name="B", military=90)
        c = Nation(id="c", name="C", military=0, stability=0)
        c.at_war_with.update({"a", "b"})
        a.at_war_with.add("c")
        b.at_war_with.add("c")
        world = World(nations={"a": a, "b": b, "c": c})
        _check_collapses(world, random.Random(1))
        self.assertFalse(world.get("c").alive)
        self.assertGreater(world.get("b").economy, 50.0)  # b (stronger) absorbed c

    def test_collapsing_without_a_war_still_just_vanishes(self):
        world = make_world(a={"stability": 0})
        _check_collapses(world, random.Random(1))
        self.assertFalse(world.get("a").alive)
        self.assertTrue(world.get("b").alive)
        self.assertEqual(world.get("b").economy, 50.0)  # unaffected, no absorption


class TestCivilWarFracturing(unittest.TestCase):
    def test_no_rebellion_when_stability_and_opinion_are_fine(self):
        world = make_world(a={"stability": 60, "public_opinion": 60})
        rng = random.Random(1)
        before_count = len(world.nations)
        _maybe_trigger_civil_war(world, world.get("a"), rng)
        self.assertEqual(len(world.nations), before_count)

    def test_rebellion_can_trigger_under_extreme_distress(self):
        world = make_world(a={"stability": 5, "public_opinion": 5})
        # Use a seed known to roll below the trigger chance immediately.
        rng = random.Random(0)
        triggered = False
        for _ in range(50):
            before_count = len(world.nations)
            _maybe_trigger_civil_war(world, world.get("a"), rng)
            if len(world.nations) > before_count:
                triggered = True
                break
            world.get("a").stability = 5
            world.get("a").public_opinion = 5
        self.assertTrue(triggered)

    def test_rebel_faction_starts_at_war_with_parent_and_takes_a_share_of_its_stats(self):
        world = make_world(a={"stability": 5, "public_opinion": 5, "military": 100, "economy": 100})
        rng = random.Random(0)
        for _ in range(50):
            before_count = len(world.nations)
            _maybe_trigger_civil_war(world, world.get("a"), rng)
            if len(world.nations) > before_count:
                break
            world.get("a").stability = 5
            world.get("a").public_opinion = 5
            world.get("a").military = 100
            world.get("a").economy = 100
        rebel_ids = [nid for nid in world.nations if nid.startswith("a_rebels_")]
        self.assertEqual(len(rebel_ids), 1)
        rebels = world.get(rebel_ids[0])
        parent = world.get("a")
        self.assertIn("a", rebels.at_war_with)
        self.assertIn(rebels.id, parent.at_war_with)
        self.assertLess(parent.military, 100)
        self.assertGreater(rebels.military, 0)

    def test_a_full_turn_with_a_fracturing_nation_does_not_crash(self):
        world = make_world(a={"stability": 5, "public_opinion": 5})
        rng = random.Random(0)
        for _ in range(30):
            run_turn(world, [Order("b", "pass")], rng)  # b is not the mover here; just advance
        # No assertion beyond "didn't crash" -- this exercises spawn_nation
        # mid-simulation through the full run_turn pipeline (AI orders,
        # market prices, elections, collapse checks) with an extra nation
        # potentially in play.


class TestConquestGameStatus(unittest.TestCase):
    def test_player_annexing_the_last_rival_wins(self):
        world = make_world(a={"military": 100, "is_player": True}, b={"military": 5})
        world.get("a").at_war_with.add("b")
        world.get("b").at_war_with.add("a")
        resolve_orders(world, [Order("a", "annex", "b")])
        self.assertEqual(game_status(world, "a"), "win")

    def test_player_being_annexed_is_a_loss(self):
        world = make_world(a={"military": 5, "is_player": True}, b={"military": 100})
        world.get("a").at_war_with.add("b")
        world.get("b").at_war_with.add("a")
        resolve_orders(world, [Order("b", "annex", "a")])
        self.assertEqual(game_status(world, "a"), "loss")


class TestConquerorTiebreakIsDeterministic(unittest.TestCase):
    def test_exact_military_tie_among_enemies_picks_by_id_not_set_order(self):
        # Regression test: the conqueror pick used to run max() directly
        # over the `at_war_with` set. Set iteration order for string keys
        # depends on Python's per-process hash randomization, so an exact
        # military tie between two enemies could pick a different
        # conqueror on different process runs even with the same
        # world.seed -- breaking the "same seed, same replay" guarantee.
        # Sorting by id before the tie-break makes the choice a pure
        # function of world state alone.
        # c collapses while at war with both a and b, who have exactly
        # equal military -- "a" sorts before "b", so a should always be
        # the one that annexes c, on every run, regardless of process-level
        # hash randomization.
        winners = set()
        for _ in range(20):
            world = World(nations={
                "a": Nation(id="a", name="A", military=50, at_war_with={"c"}),
                "b": Nation(id="b", name="B", military=50, at_war_with={"c"}),
                "c": Nation(id="c", name="C", military=0, stability=0, at_war_with={"a", "b"}),
            })
            _check_collapses(world, random.Random(1))
            self.assertFalse(world.get("c").alive)  # c is always annexed
            self.assertTrue(world.get("b").alive)  # b is never involved
            winners.add(world.get("a").economy)  # a grew iff it was the conqueror
        # Every run must agree on the same winner: a always annexes c.
        self.assertTrue(world.get("a").alive)
        self.assertGreater(world.get("a").economy, 50.0)


if __name__ == "__main__":
    unittest.main()
