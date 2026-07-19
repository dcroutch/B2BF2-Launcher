import unittest

from worldsim.scenarios import (
    MAJOR_POWERS,
    MODERATE_POWERS,
    NATO_BLOC,
    default_world,
    list_nation_ids,
)


class TestRoster(unittest.TestCase):
    def test_covers_all_major_and_moderate_powers(self):
        self.assertEqual(len(MAJOR_POWERS), 8)
        self.assertGreaterEqual(len(MODERATE_POWERS), 20)
        self.assertGreaterEqual(len(list_nation_ids()), 28)

    def test_ids_are_unique(self):
        ids = list_nation_ids()
        self.assertEqual(len(ids), len(set(ids)))


class TestDefaultWorld(unittest.TestCase):
    def test_rejects_unknown_player(self):
        with self.assertRaises(ValueError):
            default_world(player_id="atlantis")

    def test_nato_bloc_is_a_mutual_alliance(self):
        world = default_world()
        for nid in NATO_BLOC:
            others = set(NATO_BLOC) - {nid}
            self.assertTrue(others.issubset(world.get(nid).alliances))

    def test_seeded_rivalries_are_symmetric_and_negative(self):
        world = default_world()
        self.assertLess(world.get("usa").relation("russia"), 0)
        self.assertEqual(world.get("usa").relation("russia"), world.get("russia").relation("usa"))

    def test_seeded_embargoes_present(self):
        world = default_world()
        self.assertIn("russia", world.get("usa").embargoes_against)

    def test_player_flag_set_on_chosen_nation_only(self):
        world = default_world(player_id="india")
        self.assertTrue(world.get("india").is_player)
        self.assertFalse(world.get("usa").is_player)


class TestBackgroundNations(unittest.TestCase):
    """Background nations (e.g. Taiwan, North Korea) are real, addressable
    targets but never playable and never autonomous AI actors."""

    def test_background_nations_are_not_selectable_as_player(self):
        self.assertNotIn("taiwan", list_nation_ids())
        with self.assertRaises(ValueError):
            default_world(player_id="taiwan")

    def test_background_nations_exist_in_the_world(self):
        world = default_world()
        self.assertIn("taiwan", world.nations)
        self.assertTrue(world.get("taiwan").is_background)
        self.assertFalse(world.get("taiwan").is_player)

    def test_main_roster_nations_are_not_background(self):
        world = default_world()
        for nid, *_ in MAJOR_POWERS + MODERATE_POWERS:
            self.assertFalse(world.get(nid).is_background)


if __name__ == "__main__":
    unittest.main()
