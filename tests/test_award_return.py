import unittest

from tools.oracle.award_return import read_element


class AwardReturnTests(unittest.TestCase):
    def test_read_actual_handle_with_multiple_formatter_copies(self):
        self.assertEqual(read_element(b"3|3|88\0?3|3|88\0", 2, 3), (88, {0, 8}))

    def test_reject_stale_page_partial_or_conflicting_handle(self):
        for memory in (b"3|3|88\0", b"3|2|88", b"13|2|88\0", b"3|2|88\x003|2|96\0",
                       b"2|2|88\0", b"3|2|89\0"):
            with self.subTest(memory=memory), self.assertRaises(ValueError):
                read_element(memory, 1, 3)
