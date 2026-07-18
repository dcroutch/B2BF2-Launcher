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
        #
        # cli.py deliberately picks a fresh random seed per session (so
        # replays aren't predictable/scriptable -- see secrets.randbelow
        # in cli.main), so this test pins that seed to one known to
        # survive 150 turns of doing nothing but 'pass': the point here is
        # proving the *turn-cap removal*, not exercising randomness, which
        # is covered separately by test_engine's determinism/no-cap tests.
        inputs = iter(["usa"] + ["pass"] * 150)
        with patch("worldsim.cli.secrets.randbelow", return_value=0):
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


class TestReplayIsNotPredictable(unittest.TestCase):
    def test_cli_no_longer_hardcodes_a_fixed_seed(self):
        # Regression test: cli.py used to hardcode seed = 42, so every
        # terminal session played the exact same opening moves saw
        # bit-for-bit identical AI behavior and minor events every single
        # time -- a memorizable, forced-optimal script rather than a
        # world that actually varies. It must now draw a fresh seed.
        seen_seeds = []
        original_randbelow = __import__("secrets").randbelow

        def spy(n):
            value = original_randbelow(n)
            seen_seeds.append(value)
            return value

        for _ in range(3):
            inputs = iter(["usa", "quit"])
            with patch("worldsim.cli.secrets.randbelow", side_effect=spy):
                with patch("builtins.input", lambda *a: next(inputs)):
                    with patch("builtins.print"):
                        main()
        # Vanishingly unlikely to collide three times in a row if this is
        # really drawing from secrets.randbelow(1_000_000) each session.
        self.assertEqual(len(set(seen_seeds)), len(seen_seeds))


if __name__ == "__main__":
    unittest.main()
