import hashlib
import struct
import unittest

from test_actor import make_records
from test_u7 import flex
from u7uo.story_seed import area_eggs, decode_story_seed, forge_clock, ready_slot


def archive(**members):
    return flex([key.encode().ljust(13, b"\0") + data for key, data in members.items()])


class StorySeedTests(unittest.TestCase):
    def test_forge_world_clock_selects_the_saved_timer(self):
        unrelated = struct.pack("<3H", 64500, 0, 1)
        saved = struct.pack("<3H", 15761, 1, 1)
        source = archive(**{"gametima.dat": unrelated, "gametimm.dat": saved})
        clock = forge_clock(source, require_saved=True)
        self.assertEqual((clock["source"], clock["ticks"], clock["days"], clock["rate"]),
                         ("gametimm.dat", 15761, 1, 1))
        initial = archive(**{"gametima.dat": unrelated})
        self.assertEqual(forge_clock(initial)["ticks"], 9000)
        with self.assertRaises(ValueError):
            forge_clock(initial, require_saved=True)
        for invalid in (saved[:-1], unrelated, struct.pack("<3H", 120, 0, 0)):
            with self.assertRaises(ValueError):
                forge_clock(archive(**{"gametimm.dat": invalid}))

    def test_ready_record_and_zero_filled_default(self):
        row = struct.pack("<HB6x", 594, (20 << 3) | 1)
        table = b"\x01" + row
        hand = ready_slot(table, 594)
        self.assertEqual((hand["slot"], hand["offset"]), (20, 1))
        self.assertEqual(ready_slot(table, 644), {"slot": 0, "offset": None, "sha256": hand["sha256"]})
        for bad in (table[:-1], b"\x02" + row + row):
            with self.assertRaises(ValueError):
                ready_slot(bad, 594)

    def test_flags_actor_state_and_file_offsets(self):
        npcs, tfa, _ = make_records()
        npcs = bytearray(npcs)
        npcs[4 + 10] = 0xFF
        npcs[4 + 11] = 1
        struct.pack_into("<H", npcs, 4 + 16, 0x2880)
        data = archive(**{"npc.dat": npcs, "flaginit": bytes([0, 2, 255])})
        seed = decode_story_seed(data, tfa)
        actor = seed["actors"]["0"]
        self.assertEqual(seed["flags"], [0, 1, 1])
        self.assertEqual(actor["file_offset"], seed["members"]["npc.dat"]["offset"] + 4)
        self.assertEqual((actor["function_id"], actor["hit_points"], actor["can_act"]), (0x400, -1, False))
        self.assertEqual({k for k, v in actor["item_flags"].items() if v}, {"0", "1", "6", "8"})
        self.assertTrue(actor["id"].startswith("npc:" + hashlib.sha256(data).hexdigest()))
        bag, inside, sibling = actor["inventory"]
        self.assertEqual((bag["parent"], inside["parent"], sibling["parent"]), (actor["id"], bag["id"], actor["id"]))
        self.assertEqual([i["ordinal"] for i in actor["inventory"]], [0, 0, 1])
        self.assertNotEqual(inside["id"], sibling["id"])
        for item in actor["inventory"]:
            offset = item["file_offset"]
            self.assertEqual(data[offset], item["length"])
            self.assertEqual(data[offset+1:offset+1+item["length"]].hex(), item["payload_hex"])

    def test_cross_region_area_preserves_trigger_type_bits_and_caller(self):
        tfa = bytearray(3072)
        tfa[3 * 9 + 1] = 7
        def record(x, flags):
            return bytes([12]) + struct.pack("<BBHHBHBH", x, 2, 9, flags, 87, 0xABCD, 0x30, 0x0401)
        data = archive(u7ireg00=record(254, 0x0105) + record(11, 0x0105),
                       u7ireg01=record(0, 0xBFA2))
        digest = hashlib.sha256(data).hexdigest()
        usecode, music = area_eggs(data, tfa, digest, (254, 0), 3, 8)
        self.assertEqual((usecode["id"], usecode["position"], usecode["event"], usecode["function_id"]),
                         (f"ireg:{digest}:u7ireg00:0", [254, 2, 3], 3, 0x0401))
        self.assertEqual(data[usecode["archive_offset"]:][:13], record(254, 0x0105))
        self.assertEqual((music["kind_id"], music["criteria"], music["distance"], music["probability"],
                          music["data1"], music["data2"]), (2, 2, 15, 87, 0xABCD, 0x0401))
        self.assertTrue(all(music[k] for k in ("repeat", "hatched", "nocturnal", "once")))
        self.assertNotIn("event", music)
