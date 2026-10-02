import unittest

from analysis.builders.observation_text import change_text, discussion_interpretation


class ObservationTextTest(unittest.TestCase):
    def test_change_wording_handles_both_directions_and_zero_baselines(self):
        self.assertEqual(change_text(120, 100), "增加 20.0%")
        self.assertEqual(change_text(80, 100), "减少 20.0%")
        self.assertEqual(change_text(100, 100), "基本持平")
        self.assertEqual(change_text(0, 0), "仍为零")
        self.assertNotIn("%", change_text(10, 0))

    def test_interpretation_does_not_keep_old_direction_after_reversal(self):
        self.assertIn("帖子数量减少", discussion_interpretation(80, 100, 20, 10))
        self.assertIn("帖子数量增加", discussion_interpretation(120, 100, 10, 20))
        self.assertNotIn("帖子数量减少", discussion_interpretation(120, 100, 20, 10))
