import unittest

from u7uo.qualification import REQUIRED, gate_decisions


class QualificationTests(unittest.TestCase):
    def test_skipped_execution_and_reachable_unknown_cannot_pass(self):
        results = dict.fromkeys(REQUIRED[4], "passed")
        self.assertEqual(gate_decisions(results)[4]["decision"], "passed")
        results["reachable_operations"] = "failed"
        self.assertEqual(gate_decisions(results)[4]["decision"], "failed")
        del results["reachable_operations"]
        self.assertEqual(gate_decisions(results)[4]["decision"], "incomplete")
        results["main_route"] = "unknown"
        with self.assertRaises(ValueError):
            gate_decisions(results)
