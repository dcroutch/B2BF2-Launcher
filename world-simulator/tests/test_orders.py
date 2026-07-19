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


def make_world_with_bystander(**overrides):
    """Three-nation world (a, b, c) for third-party reaction tests."""
    a = Nation(id="a", name="A")
    b = Nation(id="b", name="B")
    c = Nation(id="c", name="C")
    for attr, value in overrides.get("a", {}).items():
        setattr(a, attr, value)
    for attr, value in overrides.get("b", {}).items():
        setattr(b, attr, value)
    for attr, value in overrides.get("c", {}).items():
        setattr(c, attr, value)
    return World(nations={"a": a, "b": b, "c": c})


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


class TestBackgroundNationLegality(unittest.TestCase):
    """Background nations (Nation.is_background) are real order targets,
    but must never clutter an AI nation's decision space or the player's
    menu until the player has actually engaged them -- otherwise every
    menu would balloon with ~190 mostly-irrelevant entries."""

    def make_world_with_background(self):
        a = Nation(id="a", name="A", is_player=True)
        bg = Nation(id="bg", name="Background", is_background=True)
        return World(nations={"a": a, "bg": bg})

    def test_background_nation_absent_from_fresh_player_menu(self):
        world = self.make_world_with_background()
        targets = {o.target_id for o in legal_orders(world, "a")}
        self.assertNotIn("bg", targets)

    def test_background_nation_appears_once_player_has_engaged_it(self):
        world = self.make_world_with_background()
        world.get("a").embargoes_against.add("bg")
        targets = {o.target_id for o in legal_orders(world, "a")}
        self.assertIn("bg", targets)

    def test_background_nation_never_offered_to_a_non_player_actor(self):
        # An AI-controlled nation (is_player=False) must never see a
        # background nation as a target, even if "engaged" by the same
        # criteria that would surface it for the player.
        a = Nation(id="a", name="A", is_player=False)
        bg = Nation(id="bg", name="Background", is_background=True)
        world = World(nations={"a": a, "bg": bg})
        world.get("a").embargoes_against.add("bg")
        targets = {o.target_id for o in legal_orders(world, "a")}
        self.assertNotIn("bg", targets)


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

    def test_declare_war_breaks_existing_trade_pact(self):
        # Regression: entering a war used to sever the alliance but leave
        # any trade pact intact, letting two nations at war keep collecting
        # the mutual trade-pact economy boost every turn.
        world = make_world()
        world.get("a").trade_pacts.add("b")
        world.get("b").trade_pacts.add("a")
        resolve_orders(world, [Order("a", "declare_war", "b")])
        self.assertNotIn("b", world.get("a").trade_pacts)
        self.assertNotIn("a", world.get("b").trade_pacts)

    def test_invest_sector_raises_economic_potential(self):
        # Regression / rebalance: invest_sector used to cost economy every
        # turn with only a very weak, diluted passive feedback into it,
        # so repeated investment read as a pure drain with no visible
        # payoff. It should also raise the nation's long-run economic
        # ceiling (like invest_economy does) so the passive drift pulls
        # economy back up afterward.
        world = make_world()
        before = world.get("a").economic_potential
        resolve_orders(world, [Order("a", "invest_sector", detail="technology")])
        self.assertGreater(world.get("a").economic_potential, before)

    def test_sue_for_peace_rejected_when_target_is_dominant(self):
        # The realistic case: the losing side (a, weak) asks the dominant
        # side (b, strong) for peace. b has the actual say and, being
        # dominant, presses its advantage instead of accepting -- this is
        # what makes conquest/annexation reachable at all; previously this
        # checked the *asker's* dominance instead of the *target's*, so a
        # losing side could always talk its way out of a war no matter how
        # thoroughly it was being crushed.
        world = make_world(a={"military": 10}, b={"military": 90})
        world.get("a").at_war_with.add("b")
        world.get("b").at_war_with.add("a")
        resolve_orders(world, [Order("a", "sue_for_peace", "b")])
        self.assertIn("b", world.get("a").at_war_with)

    def test_sue_for_peace_accepted_when_dominant_side_offers_it(self):
        # The dominant side (a) offering peace to the weaker side (b) is
        # always accepted -- b, not being dominant, has no reason to
        # refuse a ceasefire being offered to it.
        world = make_world(a={"military": 90}, b={"military": 10})
        world.get("a").at_war_with.add("b")
        world.get("b").at_war_with.add("a")
        resolve_orders(world, [Order("a", "sue_for_peace", "b")])
        self.assertNotIn("b", world.get("a").at_war_with)

    def test_sue_for_peace_accepted_when_neither_side_is_dominant(self):
        world = make_world(a={"military": 40}, b={"military": 40})
        world.get("a").at_war_with.add("b")
        world.get("b").at_war_with.add("a")
        resolve_orders(world, [Order("a", "sue_for_peace", "b")])
        self.assertNotIn("b", world.get("a").at_war_with)

    def test_sue_for_peace_accepted_on_mutual_exhaustion(self):
        # Both militaries ground down to zero: neither is "losing" relative
        # to the other, but the stalemate should still resolve to peace
        # instead of persisting forever.
        world = make_world(a={"military": 0}, b={"military": 0})
        world.get("a").at_war_with.add("b")
        world.get("b").at_war_with.add("a")
        resolve_orders(world, [Order("a", "sue_for_peace", "b")])
        self.assertNotIn("b", world.get("a").at_war_with)

    def test_peace_sets_a_truce_blocking_immediate_re_declaration(self):
        world = make_world(a={"military": 40}, b={"military": 40})
        world.get("a").at_war_with.add("b")
        world.get("b").at_war_with.add("a")
        world.turn = 10
        resolve_orders(world, [Order("a", "sue_for_peace", "b")])
        types = [o.type for o in legal_orders(world, "a") if o.target_id == "b"]
        self.assertNotIn("declare_war", types)

    def test_truce_expires_after_its_duration(self):
        world = make_world(a={"military": 40}, b={"military": 40})
        world.get("a").at_war_with.add("b")
        world.get("b").at_war_with.add("a")
        world.turn = 10
        resolve_orders(world, [Order("a", "sue_for_peace", "b")])
        world.turn = world.get("a").truce_until["b"]
        types = [o.type for o in legal_orders(world, "a") if o.target_id == "b"]
        self.assertIn("declare_war", types)

    def test_build_military_converts_economy(self):
        world = make_world(a={"economy": 50, "military": 10})
        resolve_orders(world, [Order("a", "build_military", None)])
        self.assertLess(world.get("a").economy, 50)
        self.assertGreater(world.get("a").military, 10)

    def test_build_military_at_full_strength_does_not_waste_economy(self):
        # Regression test: military is capped at 100, but the resolver
        # used to spend economy unconditionally regardless of how much
        # military the nation could actually still gain -- clamp_stats
        # silently discarded the overflow afterward, so a nation already
        # at (or essentially at) the cap paid real economic cost for zero
        # military benefit, turn after turn.
        world = make_world(a={"economy": 60, "economic_potential": 60, "military": 100})
        resolve_orders(world, [Order("a", "build_military", None)])
        self.assertEqual(world.get("a").economy, 60)
        self.assertEqual(world.get("a").military, 100)

    def test_build_military_near_the_cap_only_charges_for_the_remaining_room(self):
        world = make_world(a={"economy": 60, "economic_potential": 60, "military": 98})
        resolve_orders(world, [Order("a", "build_military", None)])
        self.assertEqual(world.get("a").military, 100)
        # Only ~2 military worth of spend (2/1.2) should have been
        # charged, not the full min(15, economy*0.2) it would take if
        # there were no cap.
        self.assertGreater(world.get("a").economy, 58)

    def test_invest_economy_raises_economic_potential(self):
        world = make_world()
        before = world.get("a").economic_potential
        resolve_orders(world, [Order("a", "invest_economy", None)])
        self.assertGreater(world.get("a").economic_potential, before)

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


class TestThirdPartyReactions(unittest.TestCase):
    def test_ally_of_target_condemns_actor_when_war_declared(self):
        world = make_world_with_bystander()
        world.get("c").alliances.add("b")
        world.get("b").alliances.add("c")
        resolve_orders(world, [Order("a", "declare_war", "b")])
        self.assertLess(world.get("c").relation("a"), 0)
        self.assertLess(world.get("a").relation("c"), 0)

    def test_ally_of_target_invokes_article_5_and_joins_the_war(self):
        # Alliances are mutual-defense pacts: attacking one member is
        # treated as attacking the whole bloc, so the ally doesn't just
        # disapprove -- it actually enters the war against the aggressor.
        world = make_world_with_bystander()
        world.get("c").alliances.add("b")
        world.get("b").alliances.add("c")
        resolve_orders(world, [Order("a", "declare_war", "b")])
        self.assertIn("a", world.get("c").at_war_with)
        self.assertIn("c", world.get("a").at_war_with)

    def test_multiple_allies_all_join_a_war_on_a_shared_member(self):
        a = Nation(id="a", name="A")
        b = Nation(id="b", name="B")
        c = Nation(id="c", name="C")
        d = Nation(id="d", name="D")
        for x, y in ((b, c), (b, d), (c, d)):
            x.alliances.add(y.id)
            y.alliances.add(x.id)
        world = World(nations={"a": a, "b": b, "c": c, "d": d})
        resolve_orders(world, [Order("a", "declare_war", "b")])
        self.assertIn("a", world.get("c").at_war_with)
        self.assertIn("a", world.get("d").at_war_with)

    def test_ally_joining_war_does_not_break_its_own_alliance_with_target(self):
        world = make_world_with_bystander()
        world.get("c").alliances.add("b")
        world.get("b").alliances.add("c")
        resolve_orders(world, [Order("a", "declare_war", "b")])
        self.assertIn("b", world.get("c").alliances)
        self.assertIn("c", world.get("b").alliances)

    def test_ally_of_actor_turns_on_target_when_war_declared(self):
        world = make_world_with_bystander()
        world.get("c").alliances.add("a")
        world.get("a").alliances.add("c")
        resolve_orders(world, [Order("a", "declare_war", "b")])
        self.assertLess(world.get("c").relation("b"), 0)

    def test_unrelated_bystander_unaffected_by_war(self):
        world = make_world_with_bystander()
        resolve_orders(world, [Order("a", "declare_war", "b")])
        self.assertEqual(world.get("c").relation("a"), 0)
        self.assertEqual(world.get("c").relation("b"), 0)

    def test_ally_of_embargo_target_cools_on_embargoer(self):
        world = make_world_with_bystander()
        world.get("c").alliances.add("b")
        world.get("b").alliances.add("c")
        resolve_orders(world, [Order("a", "impose_embargo", "b")])
        self.assertLess(world.get("c").relation("a"), 0)

    def test_rival_of_new_alliance_member_grows_wary(self):
        world = make_world_with_bystander()
        world.get("a").relations["b"] = 50
        world.get("b").relations["a"] = 50
        world.get("c").relations["a"] = -50
        world.get("a").relations["c"] = -50
        resolve_orders(world, [Order("a", "propose_alliance", "b")])
        self.assertLess(world.get("c").relation("b"), 0)


if __name__ == "__main__":
    unittest.main()
