import math
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from zmala_terminal.linux.auto_framing import FramingPolicy, WIDE, group_frame
from zmala_terminal.common.config_validation import validate
from zmala_terminal.common.tests.test_terminal import config


class FramingTests(unittest.TestCase):
    def test_config_requires_a_real_boolean(self):
        for value in (1, 'true', None, {}):
            with self.assertRaises(ValueError):
                validate(config() | {'auto_framing': value}, 'test')
        for value in (True, False):
            self.assertEqual(validate(config() | {'auto_framing': value}, 'test')['auto_framing'], value)

    def test_small_person_never_exceeds_two_times_zoom(self):
        self.assertEqual(group_frame([(.45, .45, .55, .55)])[2], .5)

    def test_union_keeps_every_person_in_view_at_edges(self):
        boxes = [(0., .1, .2, .8), (.8, .15, 1., .9)]
        self.assertEqual(group_frame(boxes), WIDE)

    def test_crop_is_clamped_to_source(self):
        for box in [(0., 0., .1, .1), (.9, .9, 1., 1.), (.4, .1, .6, .9)]:
            x, y, size = group_frame([box])
            self.assertGreaterEqual(x - size / 2, 0)
            self.assertGreaterEqual(y - size / 2, 0)
            self.assertLessEqual(x + size / 2, 1)
            self.assertLessEqual(y + size / 2, 1)

    def test_bad_boxes_do_not_produce_unsafe_coordinates(self):
        self.assertIsNone(group_frame([(0, 0, math.nan, 1), (1, 1, 0, 0), (-1, 0, .2, .3)]))

    def test_zoom_in_requires_two_consistent_observations(self):
        policy = FramingPolicy()
        person = [(.4, .3, .6, .6)]
        self.assertEqual(policy.update(person, 0), WIDE)
        target = policy.update(person, 2)
        self.assertEqual(target[2], .5)
        self.assertEqual(policy.update([(.41, .3, .61, .6)], 4), target)

    def test_newcomer_expands_view_without_waiting(self):
        policy = FramingPolicy()
        person = [(.4, .3, .6, .6)]
        policy.update(person, 0)
        policy.update(person, 2)
        x, y, size = policy.update(person + [(.8, .2, 1., .8)], 4)
        self.assertGreater(size, .8)
        self.assertAlmostEqual(x + size / 2, 1.)
        self.assertLessEqual(y - size / 2, .2)

    def test_brief_miss_holds_crop_then_returns_wide(self):
        policy = FramingPolicy()
        person = [(.4, .3, .6, .6)]
        policy.update(person, 0)
        target = policy.update(person, 2)
        self.assertEqual(policy.update([], 4), target)
        self.assertEqual(policy.update([], 8), WIDE)

    def test_briefly_missed_group_member_does_not_get_cropped_out(self):
        policy = FramingPolicy()
        left, right = (.1, .3, .3, .6), (.7, .3, .9, .6)
        policy.update([left, right], 0)
        policy.update([left, right], 2)
        self.assertEqual(policy.update([left], 4), WIDE)
        self.assertEqual(policy.update([left], 6), WIDE)
        policy.update([left], 8)
        self.assertLess(policy.update([left], 10)[2], 1.)


if __name__ == '__main__':
    unittest.main()
