import unittest

from tools.oracle.exult_refusal import opening


TRACE = """Running usecode 0401 () with event 3, depth 0
Running usecode 0908 () with event 3, depth 1
    [0x22]: get_avatar_ref() = abcd
...back into usecode 0401
      000A: callis _get_party_list@0 ; 0023
    [0x23]: get_party_list() = [ abcd ]
      004D: calli _play_music@2 ; 002E
    [0x2e]: play_music(0023, 0000) = Music request in usecode
Audio subsystem request: Music track # 35
"""


class ExultCalibrationTests(unittest.TestCase):
    def test_addresses_are_compared_within_the_same_run(self):
        opening(TRACE.replace("abcd", "133bf077"))
        with self.assertRaisesRegex(ValueError, "Avatar"):
            opening(TRACE.replace("[ abcd ]", "[ 1234 ]"))

    def test_music_from_a_later_activation_cannot_calibrate_the_opening(self):
        different = TRACE.replace("      004D:", "Running usecode 0401 () with event 2, depth 0\n      004D:")
        with self.assertRaisesRegex(ValueError, "Missing trace evidence"):
            opening(different)

    def test_wrong_intrinsic_site_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "Missing trace evidence"):
            opening(TRACE.replace("000A: callis", "000B: callis"))
