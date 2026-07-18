import unittest

from worldsim.orders import Order
from worldsim.parser import parse_command
from worldsim.scenarios import default_world


class TestActorLockGuarantee(unittest.TestCase):
    """The core safety property: no input text can ever produce an Order
    for a nation other than the player. This is a structural guarantee
    (parse_command only ever constructs Order(player_id, ...)), not a
    heuristic -- these tests are a regression net around that invariant."""

    def _assert_actor_is_always_player(self, text, player_id="usa"):
        world = default_world(player_id=player_id)
        order = parse_command(world, player_id, text)
        self.assertEqual(order.actor_id, player_id)

    def test_plain_command_locks_actor_to_player(self):
        self._assert_actor_is_always_player("declare war on Russia")

    def test_attempted_impersonation_still_locks_actor_to_player(self):
        self._assert_actor_is_always_player("China declares war on Russia")

    def test_imperative_impersonation_still_locks_actor_to_player(self):
        self._assert_actor_is_always_player("Have Germany invade Poland")

    def test_nonsense_text_still_locks_actor_to_player(self):
        self._assert_actor_is_always_player("purple elephants dance on the moon")

    def test_impersonation_does_not_mutate_the_named_nation_directly(self):
        world = default_world(player_id="usa")
        china_military_before = world.get("china").military
        china_at_war_before = set(world.get("china").at_war_with)
        order = parse_command(world, "usa", "China declares war on Russia")
        self.assertEqual(order.actor_id, "usa")
        # Parsing alone must never mutate world state.
        self.assertEqual(world.get("china").military, china_military_before)
        self.assertEqual(world.get("china").at_war_with, china_at_war_before)

    def test_impersonation_is_downgraded_to_wildcard_not_a_real_war_order(self):
        world = default_world(player_id="usa")
        order = parse_command(world, "usa", "China declares war on Russia")
        self.assertEqual(order.type, "wildcard")
        self.assertNotEqual(order.type, "declare_war")


class TestVerbRecognition(unittest.TestCase):
    def test_declare_war_recognized_with_target(self):
        world = default_world(player_id="usa")
        order = parse_command(world, "usa", "We invade Iran immediately")
        self.assertEqual(order, Order("usa", "declare_war", "iran"))

    def test_embargo_recognized_with_target(self):
        world = default_world(player_id="usa")
        order = parse_command(world, "usa", "Impose a total embargo on Russia")
        self.assertEqual(order, Order("usa", "impose_embargo", "russia"))

    def test_alliance_recognized_with_target(self):
        world = default_world(player_id="usa")
        order = parse_command(world, "usa", "Propose an alliance with Japan")
        self.assertEqual(order, Order("usa", "propose_alliance", "japan"))

    def test_sector_investment_recognized(self):
        world = default_world(player_id="usa")
        order = parse_command(world, "usa", "Invest in our technology sector")
        self.assertEqual(order.type, "invest_sector")
        self.assertEqual(order.detail, "technology")

    def test_annex_recognized_with_target(self):
        # Regression test: annex/propose_accession had no VERB_RULES entry
        # at all, so free text could never reach them -- only the menu
        # (numbered CLI list / web app menu index) could.
        world = default_world(player_id="usa")
        order = parse_command(world, "usa", "Annex Ukraine")
        self.assertEqual(order, Order("usa", "annex", "ukraine"))

    def test_propose_accession_recognized_with_target(self):
        world = default_world(player_id="canada")
        order = parse_command(world, "canada", "We vote to join the United States")
        self.assertEqual(order, Order("canada", "propose_accession", "usa"))

    def test_generic_investment_without_sector_falls_back(self):
        world = default_world(player_id="usa")
        order = parse_command(world, "usa", "Stimulate the economy")
        self.assertEqual(order.type, "invest_economy")

    def test_targeted_verb_without_target_falls_back_to_wildcard(self):
        world = default_world(player_id="usa")
        order = parse_command(world, "usa", "Declare war on nobody in particular")
        self.assertEqual(order.type, "wildcard")

    def test_empty_input_handled_by_caller_not_parser_crash(self):
        world = default_world(player_id="usa")
        order = parse_command(world, "usa", "")
        self.assertEqual(order.actor_id, "usa")  # doesn't crash


class TestWildcardFallback(unittest.TestCase):
    def test_erratic_input_resolves_to_wildcard(self):
        world = default_world(player_id="usa")
        order = parse_command(
            world, "usa", "USA demands France refund the Louisiana Purchase"
        )
        self.assertEqual(order.type, "wildcard")
        self.assertEqual(order.target_id, "france")
        self.assertIn("Louisiana Purchase", order.detail)

    def test_nonsense_with_no_nation_mention_has_no_target(self):
        world = default_world(player_id="usa")
        order = parse_command(world, "usa", "The president juggles flaming torches")
        self.assertEqual(order.type, "wildcard")
        self.assertIsNone(order.target_id)


class TestPossessiveMentionIsNotTreatedAsSubject(unittest.TestCase):
    """Regression tests: the impersonation guard used to treat *any*
    earliest nation mention as the sentence's subject, including a purely
    possessive one ("Germany's surrender"), silently downgrading a
    legitimate self-directed order into a wildcard."""

    def test_possessive_mention_does_not_block_a_real_order(self):
        world = default_world(player_id="usa")
        order = parse_command(world, "usa", "Following Germany's collapse, we annex Poland")
        self.assertEqual(order.actor_id, "usa")
        self.assertEqual(order.type, "annex")
        self.assertEqual(order.target_id, "poland")

    def test_non_possessive_mention_still_triggers_the_guard(self):
        # Make sure the fix didn't just disable the guard outright.
        world = default_world(player_id="usa")
        order = parse_command(world, "usa", "Germany declares war on Poland")
        self.assertEqual(order.actor_id, "usa")
        self.assertEqual(order.type, "wildcard")

    def test_later_non_possessive_mention_of_the_same_nation_is_still_found(self):
        # Regression: the same nation named twice, first possessively then
        # as the real subject, used to be missed entirely -- a plain
        # first-match search stopped at the possessive occurrence and never
        # looked further, so the later, legitimate mention was invisible.
        world = default_world(player_id="usa")
        order = parse_command(
            world, "usa", "Following France's defeat, France surrenders"
        )
        self.assertEqual(order.actor_id, "usa")
        self.assertEqual(order.target_id, "france")


if __name__ == "__main__":
    unittest.main()
