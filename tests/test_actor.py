import struct
import unittest

from u7uo.actor import HEADER_SIZE, read_actor


def header(name, shape, frame, region, x, y, lift, function, has_inventory=False):
    data = bytearray(HEADER_SIZE)
    struct.pack_into("<BBHHB", data, 0, x, y, shape | frame << 10, int(has_inventory), region)
    struct.pack_into("<H", data, 8, function | lift << 12)
    struct.pack_into("<H", data, 14, 1)
    data[101:101 + len(name)] = name
    return data


def make_records():
    tfa = bytearray(3072)
    tfa[3 * 4 + 1] = 13  # NPCs
    tfa[3 * 7 + 1] = 6   # A container capable of holding a child
    # Two six-byte objects have the same source position and shape. The first
    # belongs to the bag, the second to the previous NPC.
    bag = b"\x0c" + struct.pack("<BBHH", 10, 10, 7, 1) + bytes(6)
    obj = b"\x06" + struct.pack("<BBHH", 10, 10, 2, 0)
    inventory = bag + obj + b"\x01" + obj + b"\x00"
    npc0 = header(b"Test A", 4, 1, 12, 55, 2, 8, 0x400, True)
    npc1 = header(b"Test B", 4, 5, 37, 18, 55, 3, 0x42B)
    return struct.pack("<HH", 2, 0) + npc0 + inventory + npc1, tfa, len(inventory)


class ActorTests(unittest.TestCase):
    def test_follows_container_boundaries_and_reads_separate_lift_and_function(self):
        data, tfa, inventory_size = make_records()
        actor = read_actor(data, tfa, 1)
        self.assertEqual(actor["record_offset"], 4 + HEADER_SIZE + inventory_size)
        self.assertEqual(actor["name"], "Test B")
        self.assertEqual(actor["source_position"], [274, 823, 3])
        self.assertEqual((actor["shape"], actor["frame"], actor["function_id"]), (4, 5, 0x42B))
        self.assertEqual(actor["table"]["inventory_records_indexed"], 3)
        self.assertEqual(actor["table"]["bytes_consumed"], len(data))

    def test_mismatched_shape_class_and_truncated_or_extra_bytes_fail(self):
        data, tfa, _ = make_records()
        for broken in [data[:-1], data + b"\x00"]:
            with self.subTest(length=len(broken)), self.assertRaises(ValueError):
                read_actor(broken, tfa, 1)
        tfa[3 * 7 + 1] = 0
        with self.assertRaisesRegex(ValueError, "contradicts TFA"):
            read_actor(data, tfa, 1)


if __name__ == "__main__":
    unittest.main()
