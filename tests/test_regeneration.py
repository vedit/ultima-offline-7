import unittest

from tools.oracle.regeneration import compare_graph


class RegenerationTests(unittest.TestCase):
    def test_relocated_text_and_inserted_jump_preserve_both_ordered_paths(self):
        original = {"instructions":[(0,5,[4]),(3,0x1c,[4]),(6,0x25,[]),(7,0x3f,[])],
                    "strings_referenced":{4:{"sha256":"first"}}, "branches":{0:7},"code_length":8}
        regenerated = {"instructions":[(0,5,[7]),(3,6,[0]),(6,0x1c,[18]),(9,0x25,[]),(10,0x3f,[])],
                       "strings_referenced":{18:{"sha256":"first"}},"branches":{0:10,3:6},"code_length":11}
        self.assertEqual(compare_graph(original,regenerated)["status"],"matched")
        regenerated["strings_referenced"][18]["sha256"]="second"
        self.assertEqual(compare_graph(original,regenerated)["source_pc"],3)
        regenerated["branches"][0]=9
        self.assertEqual(compare_graph(original,regenerated)["source_pc"],7)
