import random
import unittest

from worldsim.engine import advance_turns, game_status, run_turn
from worldsim.orders import Order
from worldsim.scenarios import default_world


class TestRunTurn(unittest.TestCase):
    def test_run_turn_advances_counter(self):
        world = default_world()
        rng = random.Random(1)
        run_turn(world, [Order("usa", "pass")], rng)
        self.assertEqual(world.turn, 1)

    def test_stats_stay_in_bounds_over_many_turns(self):
        world = default_world()
        rng = random.Random(1)
        for _ in range(50):
            run_turn(world, [Order("usa", "invest_economy")], rng)
            for n in world.nations.values():
                self.assertGreaterEqual(n.stability, 0)
                self.assertLessEqual(n.stability, 100)
                self.assertGreaterEqual(n.military, 0)
                self.assertLessEqual(n.military, 100)
                self.assertGreaterEqual(n.economy, 0)
                # Economy's ceiling is potential-relative (potential + 15
                # headroom), not a flat 100 -- see models.Nation.clamp_stats.
                self.assertLessEqual(n.economy, n.economic_potential + 15)
                self.assertGreaterEqual(n.economic_potential, 0)
                self.assertLessEqual(n.economic_potential, 100)

    def test_economies_stay_differentiated_instead_of_converging(self):
        # Regression test for the old bug where every nation's economy
        # monotonically climbed to the same flat global cap regardless of
        # starting strength or events, wiping out all differentiation.
        world = default_world(seed=5)
        rng = random.Random(5)
        for _ in range(80):
            run_turn(world, [Order("usa", "pass")], rng)
        economies = [n.economy for n in world.alive_nations()]
        self.assertGreater(max(economies) - min(economies), 20)
        # A nation ground down by war/sanctions should end up well below
        # its own long-run potential, not clamped to a shared global cap.
        russia = world.get("russia")
        self.assertLess(russia.economy, russia.economic_potential - 20)

    def test_relations_heal_toward_neutral_over_time_when_at_peace(self):
        world = default_world(seed=2)
        world.get("usa").relations["china"] = -90
        world.get("china").relations["usa"] = -90
        rng = random.Random(2)
        for _ in range(30):
            run_turn(world, [Order("usa", "pass")], rng)
        self.assertGreater(world.get("usa").relation("china"), -90)

    def test_simulation_is_deterministic_given_seed(self):
        w1 = default_world(seed=99)
        w2 = default_world(seed=99)
        r1, r2 = random.Random(99), random.Random(99)
        for _ in range(20):
            run_turn(w1, [Order("usa", "pass")], r1)
            run_turn(w2, [Order("usa", "pass")], r2)
        for nid in w1.nations:
            self.assertEqual(w1.get(nid).stability, w2.get(nid).stability)
            self.assertEqual(w1.get(nid).military, w2.get(nid).military)
            self.assertEqual(w1.get(nid).economy, w2.get(nid).economy)


class TestGameStatus(unittest.TestCase):
    def test_continues_by_default(self):
        world = default_world()
        self.assertIsNone(game_status(world, "usa"))

    def test_loss_when_player_collapses(self):
        world = default_world()
        world.get("usa").alive = False
        self.assertEqual(game_status(world, "usa"), "loss")

    def test_win_when_sole_survivor(self):
        world = default_world()
        for nid, n in world.nations.items():
            if nid != "usa":
                n.alive = False
        self.assertEqual(game_status(world, "usa"), "win")

    def test_win_does_not_require_eliminating_background_nations(self):
        # Regression: background nations (Taiwan, North Korea, etc.) are
        # part of world.nations but were never meant to count toward "the
        # last nation standing" -- counting all ~190 of them would make
        # domination effectively unreachable.
        world = default_world()
        for nid, n in world.nations.items():
            if nid != "usa" and not n.is_background:
                n.alive = False
        self.assertTrue(any(n.is_background and n.alive for n in world.nations.values()))
        self.assertEqual(game_status(world, "usa"), "win")

    def test_loss_when_player_ousted_from_power(self):
        world = default_world()
        world.get("usa").in_power = False
        self.assertEqual(game_status(world, "usa"), "loss")

    def test_there_is_no_turn_cap_game_continues_regardless_of_how_high_the_turn_counter_is(self):
        # Regression test: the game used to force a win/loss the moment
        # world.turn hit a fixed cap, purely based on who was strongest at
        # that instant. There is no such cap anymore -- the game keeps
        # running indefinitely until an actual loss/win/voluntary-quit
        # condition is met, no matter how many turns have passed.
        world = default_world()
        world.turn = 100_000
        self.assertIsNone(game_status(world, "usa"))


class TestAdvanceTurns(unittest.TestCase):
    """advance_turns lets a player submit several orders for the current
    turn and then skip ahead N turns (months) at once, with no further
    input, collecting every event across the whole skip into one digest."""

    def test_advances_the_requested_number_of_turns(self):
        world = default_world()
        rng = random.Random(1)
        advance_turns(world, "usa", [Order("usa", "pass")], num_turns=3, rng=rng)
        self.assertEqual(world.turn, 3)

    def test_all_submitted_orders_resolve_on_the_first_turn(self):
        world = default_world()
        rng = random.Random(1)
        before_energy = world.get("usa").sectors["energy_sector"]
        orders = [
            Order("usa", "invest_sector", detail="energy_sector"),
            Order("usa", "impose_embargo", "russia"),
        ]
        advance_turns(world, "usa", orders, num_turns=1, rng=rng)
        self.assertGreater(world.get("usa").sectors["energy_sector"], before_energy)
        self.assertIn("russia", world.get("usa").embargoes_against)

    def test_returns_the_combined_log_across_every_turn_advanced(self):
        world = default_world()
        rng = random.Random(1)
        start = len(world.event_log)
        log = advance_turns(world, "usa", [Order("usa", "pass")], num_turns=3, rng=rng)
        self.assertEqual(log, world.event_log[start:])
        self.assertGreater(len(log), 0)

    def test_stops_early_if_the_game_ends_partway_through_the_skip(self):
        world = default_world()
        world.get("usa").in_power = False
        rng = random.Random(1)
        turn_before = world.turn
        advance_turns(world, "usa", [Order("usa", "pass")], num_turns=6, rng=rng)
        # Only the first turn (which already carried the losing state) ran;
        # game_status was already non-None before any further turn, so the
        # loop broke immediately instead of simulating 5 more turns.
        self.assertEqual(world.turn, turn_before + 1)


if __name__ == "__main__":
    unittest.main()
