import random
import unittest

from worldsim.engine import game_status, run_turn
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
                self.assertLessEqual(n.economy, 100)

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

    def test_max_turns_reached_declares_strongest_winner(self):
        world = default_world()
        world.turn = 100
        world.get("usa").economy = 100
        world.get("usa").military = 100
        self.assertEqual(game_status(world, "usa", max_turns=100), "win")


if __name__ == "__main__":
    unittest.main()
