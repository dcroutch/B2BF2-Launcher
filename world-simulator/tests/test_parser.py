import unittest

from worldsim.orders import Order
from worldsim.parser import parse_command, parse_commands
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


class TestVerbConjugation(unittest.TestCase):
    """Regression tests: the keyword lists were originally written as bare
    infinitives ("embargo", "invade") and matched only that exact word, so
    a player typing ordinary conjugated English ("China embargoes Russia")
    silently fell through to a vague wildcard instead of the intended
    order -- a huge, largely invisible gap in what the parser understood."""

    def test_third_person_present_tense_is_recognized(self):
        world = default_world(player_id="china")
        order = parse_command(world, "china", "China embargoes Russia")
        self.assertEqual(order.type, "impose_embargo")
        self.assertEqual(order.target_id, "russia")

    def test_past_tense_is_recognized(self):
        world = default_world(player_id="china")
        order = parse_command(world, "china", "China embargoed Russia")
        self.assertEqual(order.type, "impose_embargo")
        self.assertEqual(order.target_id, "russia")

    def test_alternate_verb_conjugation_is_recognized(self):
        world = default_world(player_id="china")
        order = parse_command(world, "china", "China sanctions Russia")
        self.assertEqual(order.type, "impose_embargo")
        self.assertEqual(order.target_id, "russia")

    def test_earliest_matching_keyword_wins_not_first_listed(self):
        # Regression: within one order type's keyword list, the matcher
        # used to stop at whichever keyword was listed first, even if a
        # different keyword for that same order type occurred earlier in
        # the text -- e.g. "blockade" (listed before "surround") would win
        # even when "surround" sat right next to the actual target and
        # "blockade" only appeared much later, wrongly making the verb
        # look like it came *after* the nation mention and tripping the
        # actor-lock guard into downgrading a legitimate order to a
        # wildcard.
        world = default_world(player_id="china")
        order = parse_command(
            world, "china", "Surround Russia and institute a blockade"
        )
        self.assertEqual(order.type, "impose_embargo")
        self.assertEqual(order.target_id, "russia")


class TestPassRecognizesTheLiteralWord(unittest.TestCase):
    def test_literal_pass_is_recognized(self):
        # Regression: only "do nothing"/"wait"/"hold position"/"stand
        # down" were recognized -- typing the literal word "pass" (an
        # extremely natural way to skip a turn) fell through to a vague
        # wildcard instead.
        world = default_world(player_id="usa")
        order = parse_command(world, "usa", "pass")
        self.assertEqual(order.type, "pass")


class TestParseCommands(unittest.TestCase):
    """parse_commands splits one submission into several distinct orders
    for the same turn, so a player can queue up multiple actions at once
    instead of being limited to exactly one order per turn."""

    def test_semicolon_separated_instructions_become_separate_orders(self):
        world = default_world(player_id="china")
        orders = parse_commands(world, "china", "invest in energy; embargo Russia")
        self.assertEqual(len(orders), 2)
        self.assertEqual(orders[0].type, "invest_sector")
        self.assertEqual(orders[1].type, "impose_embargo")
        self.assertEqual(orders[1].target_id, "russia")

    def test_and_then_separated_instructions_become_separate_orders(self):
        world = default_world(player_id="china")
        orders = parse_commands(
            world, "china", "invest in energy and then embargo Russia"
        )
        self.assertEqual(len(orders), 2)

    def test_plain_and_within_one_instruction_is_not_split(self):
        # "and" alone is ordinary English inside a single action -- only
        # newlines/semicolons/"and then" separate distinct instructions.
        world = default_world(player_id="china")
        orders = parse_commands(
            world, "china", "Surround Russia and institute a blockade"
        )
        self.assertEqual(len(orders), 1)

    def test_every_order_is_locked_to_the_player(self):
        world = default_world(player_id="usa")
        orders = parse_commands(
            world, "usa", "invest in energy; China declares war on Russia"
        )
        self.assertTrue(all(o.actor_id == "usa" for o in orders))

    def test_single_instruction_still_returns_a_one_element_list(self):
        world = default_world(player_id="usa")
        orders = parse_commands(world, "usa", "invest in energy")
        self.assertEqual(len(orders), 1)

    def test_empty_input_falls_back_to_pass(self):
        world = default_world(player_id="usa")
        orders = parse_commands(world, "usa", "   ")
        self.assertEqual(orders, [Order("usa", "pass")])

    def test_excess_instructions_are_capped(self):
        world = default_world(player_id="usa")
        text = "; ".join(["invest in energy"] * 20)
        orders = parse_commands(world, "usa", text)
        self.assertLessEqual(len(orders), 6)


if __name__ == "__main__":
    unittest.main()
