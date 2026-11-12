import json
import struct
import tempfile
import unittest
from pathlib import Path

from tools.oracle.mayor_schedule import compare_arrival, saved_npc_route


class NativeRouteTests(unittest.TestCase):
    def test_owner_selects_active_slot_and_rejects_stale_route_files(self):
        table = bytearray(45)
        table[3] = 1
        struct.pack_into("<H", table, 15+2*3, 824)
        raw = bytearray(38)
        struct.pack_into("<5Hb3H", raw, 21, 824, 0, 999, 1017, 2248, 0, 1, 0, 2)
        raw.extend(struct.pack("<HHbHHb", 1031, 2262, 0, 1017, 2248, 0))
        files = {"path.dat":table, "path3.dat":raw}
        route = saved_npc_route(files.__getitem__, 824)
        self.assertEqual([[1031,2262,0],[1017,2248,0]], route["waypoints"])
        self.assertEqual(1, route["waypoint_index"])
        table[3] = 0
        self.assertIsNone(saved_npc_route(files.__getitem__, 824))
        table[3] = 1
        raw[21] ^= 1
        with self.assertRaises(ValueError):
            saved_npc_route(files.__getitem__, 824)


class AppointmentComparisonTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.path = Path(directory.name) / "player.json"
        row = {"world_xy": [980, 2196], "activity": 16}
        self.trial = {"receipt_sha256": "original", "source_schedule": row,
                      "arrival_bracket_ticks": [9056, 9066], "source_save": "home", "resident": True}
        self.player = {"status": "passed", "saved_and_restarted": True, "build_id": "facet",
                       "fixture": {"native_receipt_sha256": "original", "source_row": row},
                       "office_xy": row["world_xy"], "walk_steps": 65}

    def compare(self, tick):
        self.path.write_text(json.dumps({**self.player, "arrival_tick": tick}), encoding="utf-8")
        return compare_arrival(self.trial, self.path, "facet")

    def test_last_absent_tick_is_excluded_and_first_present_tick_is_included(self):
        self.assertFalse(self.compare(9056)["target_within_observed_window"])
        self.assertTrue(self.compare(9066)["target_within_observed_window"])
        self.assertEqual(582, self.compare(9648)["minimum_late_ticks"])

    def test_rejects_report_from_another_dos_run(self):
        self.player["fixture"]["native_receipt_sha256"] = "other"
        with self.assertRaises(ValueError):
            self.compare(9060)
