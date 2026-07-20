import random
import unittest

from worldsim.engine import run_turn
from worldsim.models import Nation, World
from worldsim.orders import Order, resolve_orders
from worldsim.parser import parse_command
from worldsim.statuses import (
    STATUS_CATALOG,
    _apply_reaction,
    apply_declared_status,
    react_to_declared_statuses,
)


def make_world(**overrides):
    a = Nation(id="a", name="A")
    b = Nation(id="b", name="B")
    for attr, value in overrides.get("a", {}).items():
        setattr(a, attr, value)
    for attr, value in overrides.get("b", {}).items():
        setattr(b, attr, value)
    return World(nations={"a": a, "b": b})


class TestDeclareStatus(unittest.TestCase):
    def test_declaring_applies_one_time_stat_effect(self):
        world = make_world()
        actor = world.get("a")
        before = actor.economy
        resolve_orders(world, [Order("a", "declare_status", detail="post_scarcity_economy")])
        self.assertGreater(actor.economy, before)
        self.assertIn("post_scarcity_economy", actor.declared_statuses)

    def test_redeclaring_the_same_status_is_a_no_op(self):
        world = make_world()
        actor = world.get("a")
        resolve_orders(world, [Order("a", "declare_status", detail="post_scarcity_economy")])
        after_first = actor.economy
        resolve_orders(world, [Order("a", "declare_status", detail="post_scarcity_economy")])
        self.assertEqual(actor.economy, after_first)

    def test_unknown_status_id_is_silently_ignored(self):
        world = make_world()
        actor = world.get("a")
        before = actor.economy
        resolve_orders(world, [Order("a", "declare_status", detail="not_a_real_status")])
        self.assertEqual(actor.economy, before)
        self.assertEqual(actor.declared_statuses, set())


class TestStatusParsing(unittest.TestCase):
    def test_recognizes_a_status_announcement(self):
        world = make_world()
        order = parse_command(world, "a", "Our scientists unveil matter synthesis technology")
        self.assertEqual(order.type, "declare_status")
        self.assertEqual(order.detail, "matter_synthesis")

    def test_recognizes_post_scarcity_phrasing(self):
        world = make_world()
        order = parse_command(world, "a", "We have achieved a post-scarcity economy")
        self.assertEqual(order.type, "declare_status")
        self.assertEqual(order.detail, "post_scarcity_economy")

    def test_every_catalog_entry_has_at_least_one_matchable_keyword(self):
        world = make_world()
        for status_id, status in STATUS_CATALOG.items():
            keyword = status["keywords"][0]
            order = parse_command(world, "a", f"We just achieved {keyword}")
            self.assertEqual(order.type, "declare_status", f"{status_id} keyword {keyword!r} didn't parse")
            self.assertEqual(order.detail, status_id)


class TestReactionMechanics(unittest.TestCase):
    """Each reaction archetype's mechanical effect, called directly so the
    test doesn't depend on the weighted RNG draw picking it."""

    def setUp(self):
        self.rng = random.Random(1)

    def test_petition_to_join_absorbs_the_reactor(self):
        world = make_world(a={"economy": 80, "military": 80}, b={"economy": 30, "military": 30})
        status = STATUS_CATALOG["post_scarcity_economy"]
        _apply_reaction(world, world.get("a"), world.get("b"), "post_scarcity_economy", status, "petition_to_join", self.rng)
        self.assertTrue(world.get("a").alive)
        self.assertFalse(world.get("b").alive)

    def test_attack_for_access_starts_a_war(self):
        world = make_world()
        status = STATUS_CATALOG["military_supremacy"]
        _apply_reaction(world, world.get("a"), world.get("b"), "military_supremacy", status, "attack_for_access", self.rng)
        self.assertIn("b", world.get("a").at_war_with)
        self.assertIn("a", world.get("b").at_war_with)

    def test_pressure_for_access_does_not_touch_economy_directly(self):
        world = make_world()
        status = STATUS_CATALOG["post_scarcity_economy"]
        econ_before = world.get("a").economy
        _apply_reaction(world, world.get("a"), world.get("b"), "post_scarcity_economy", status, "pressure_for_access", self.rng)
        self.assertEqual(world.get("a").economy, econ_before)
        self.assertIn("a", world.get("b").access_pressure_against)

    def test_propose_alliance_makes_them_allies(self):
        world = make_world()
        status = STATUS_CATALOG["cultural_golden_age"]
        _apply_reaction(world, world.get("a"), world.get("b"), "cultural_golden_age", status, "propose_alliance", self.rng)
        self.assertIn("a", world.get("b").alliances)
        self.assertIn("b", world.get("a").alliances)

    def test_imitate_race_boosts_reactors_own_relevant_sector(self):
        world = make_world()
        status = STATUS_CATALOG["matter_synthesis"]  # scientific -> technology sector
        before = world.get("b").sectors["technology"]
        _apply_reaction(world, world.get("a"), world.get("b"), "matter_synthesis", status, "imitate_race", self.rng)
        self.assertGreater(world.get("b").sectors["technology"], before)

    def test_condemn_only_hurts_relations(self):
        world = make_world()
        status = STATUS_CATALOG["military_supremacy"]
        _apply_reaction(world, world.get("a"), world.get("b"), "military_supremacy", status, "condemn", self.rng)
        self.assertLess(world.get("b").relation("a"), 0)

    def test_ignore_changes_nothing(self):
        world = make_world()
        status = STATUS_CATALOG["post_scarcity_economy"]
        snapshot = (world.get("a").economy, world.get("b").economy, world.get("b").relation("a"))
        _apply_reaction(world, world.get("a"), world.get("b"), "post_scarcity_economy", status, "ignore", self.rng)
        self.assertEqual((world.get("a").economy, world.get("b").economy, world.get("b").relation("a")), snapshot)


class TestReactionGating(unittest.TestCase):
    def test_low_relation_reactor_never_petitions_to_join(self):
        # Regression guard: petitioning to join must require the same very
        # high mutual-trust bar as propose_accession/invite_accession
        # elsewhere in the game (relation >= 70), not just a plain
        # alliance (~45) -- otherwise a single status declaration could
        # instantly absorb multiple allies.
        for seed in range(30):
            world = make_world(a={"economy": 80, "military": 80}, b={"economy": 30, "military": 30})
            world.get("a").relations["b"] = 69
            world.get("b").relations["a"] = 69
            apply_declared_status(world, world.get("a"), "post_scarcity_economy")
            rng = random.Random(seed)
            for _ in range(60):
                if not world.get("b").alive:
                    break
                react_to_declared_statuses(world, rng)
            self.assertTrue(world.get("b").alive, f"seed {seed} absorbed reactor below relation threshold")

    def test_stronger_reactor_never_petitions_to_join(self):
        # A reactor that's already stronger than the status holder has
        # nothing to gain from dissolving into them.
        for seed in range(20):
            world = make_world(a={"economy": 50, "military": 50}, b={"economy": 80, "military": 80})
            world.get("a").relations["b"] = 90
            world.get("b").relations["a"] = 90
            apply_declared_status(world, world.get("a"), "post_scarcity_economy")
            rng = random.Random(seed)
            for _ in range(60):
                if not world.get("b").alive:
                    break
                react_to_declared_statuses(world, rng)
            self.assertTrue(world.get("b").alive, f"seed {seed} absorbed a stronger reactor")


class TestReactionsAreNotUniform(unittest.TestCase):
    def test_different_seeds_produce_different_reaction_outcomes(self):
        # The whole point of the feature: the same declared status,
        # against the same starting relation, should not resolve to the
        # exact same world reaction every time.
        outcomes = set()
        for seed in range(25):
            world = make_world(a={"economy": 70, "military": 60}, b={"economy": 40, "military": 40})
            world.get("a").relations["b"] = 50
            world.get("b").relations["a"] = 50
            apply_declared_status(world, world.get("a"), "military_supremacy")
            rng = random.Random(seed)
            for _ in range(20):
                react_to_declared_statuses(world, rng)
            key = "b" not in world.nations or not world.get("b").alive
            outcomes.add((
                world.get("b").alive,
                "b" in world.get("a").alliances if world.get("b").alive else None,
                "b" in world.get("a").trade_pacts if world.get("b").alive else None,
                "b" in world.get("a").at_war_with if world.get("b").alive else None,
            ))
        self.assertGreater(len(outcomes), 1, "every seed produced the identical outcome")


if __name__ == "__main__":
    unittest.main()
