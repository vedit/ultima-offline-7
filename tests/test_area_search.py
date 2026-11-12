import hashlib
import struct
import unittest

from test_u7 import flex
from u7uo.area_search import compare, extent, insert_item, opening_search


class AreaSearchTests(unittest.TestCase):
    def test_footprint_flip_and_original_overlap_order(self):
        tfa = bytearray(3072)
        tfa[3:6] = bytes([0xA0, 0, 2])
        self.assertEqual(extent((15, 15, 0), 1, 0, tfa), (7, 1, 0x7C00))
        self.assertEqual(extent((15, 15, 1), 1, 32, tfa), (1, 7, 0x3E00))
        self.assertEqual(compare((1, 2, 1), (2, 1, 1)), 0)
        boxes = {"first": (4, 4, 2), "second": (2, 2, 2), "new": (3, 3, 2)}
        items = ["first", "second"]
        insert_item(items, "new", boxes)
        self.assertEqual(items, ["second", "new", "first"])

    def test_wildcard_living_npc_scan_order_and_filters(self):
        data = flex([b"u7ireg00".ljust(13,b"\0") + b"\0"])
        tfa = bytearray(3072)
        tfa[3:9] = bytes([0x80,13,0, 0x80,13|128,0])
        def actor(slot, x, y, *, dead=False, hidden=False, shape=1):
            return {"npc_slot":slot, "id":str(slot), "source_position":[x,y,0],
                    "shape":shape, "frame":0, "item_flags":{"0":hidden, "4":dead}}
        rows = [actor(0,32,32), actor(1,49,48), actor(2,32,48), actor(3,50,48,dead=True),
                actor(4,49,49,hidden=True), actor(5,48,49,shape=2), actor(6,80,80)]
        seed = {"seed_sha256":hashlib.sha256(data).hexdigest(), "actors":{a["id"]:a for a in rows}}
        self.assertEqual(opening_search(data,tfa,seed,(32,32),18)["slots"], [1,2,0])
        # A regional NPC outside npc.dat must never silently disappear from the result.
        item = struct.pack("<BBBH",12,32,32,1) + bytes(8)
        data = flex([b"u7ireg00".ljust(13,b"\0") + item])
        with self.assertRaises(ValueError):
            opening_search(data,tfa,seed,(32,32),18)
