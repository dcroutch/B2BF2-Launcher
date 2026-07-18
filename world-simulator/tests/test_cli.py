import unittest
from unittest.mock import patch

from worldsim.cli import main


class TestVoluntaryQuit(unittest.TestCase):
    def test_quit_command_ends_the_session_without_a_win_or_loss_verdict(self):
        inputs = iter(["usa", "pass", "pass", "quit"])
        with patch("builtins.input", lambda *a: next(inputs)):
            with patch("builtins.print") as mock_print:
                main()  # should return cleanly, not raise or hang
        printed = "\n".join(str(c.args[0]) if c.args else "" for c in mock_print.call_args_list)
        self.assertIn("GAME ENDED", printed)
        self.assertNotIn("GAME OVER", printed)

    def test_quit_is_case_insensitive_and_trims_whitespace(self):
        inputs = iter(["usa", "  QUIT  "])
        with patch("builtins.input", lambda *a: next(inputs)):
            with patch("builtins.print") as mock_print:
                main()
        printed = "\n".join(str(c.args[0]) if c.args else "" for c in mock_print.call_args_list)
        self.assertIn("GAME ENDED", printed)

    def test_game_can_advance_past_the_old_turn_cap_without_a_forced_outcome(self):
        # Regression guard for "eliminate turn caps": the simulation used
        # to force a win/loss the instant world.turn hit a fixed 100-turn
        # cap, regardless of actual game state. Feed it enough 'pass'
        # turns to run well past that old cap and confirm the transcript
        # shows turn counters beyond 100 -- whatever eventually ends the
        # session (a real loss/win condition, or running out of scripted
        # input), it isn't an artificial cap kicking in at exactly turn 100.
        inputs = iter(["usa"] + ["pass"] * 150)
        with patch("builtins.input", lambda *a: next(inputs)):
            with patch("builtins.print") as mock_print:
                try:
                    main()
                except StopIteration:
                    pass  # ran out of scripted 'pass' input -- fine, not a cap
        printed = "\n".join(str(c.args[0]) if c.args else "" for c in mock_print.call_args_list)
        self.assertTrue(
            any(f"Turn {t} " in printed for t in range(100, 151)),
            "expected the game to have advanced past the old 100-turn cap",
        )


if __name__ == "__main__":
    unittest.main()
