import json
import struct
import tempfile
import unittest
from pathlib import Path

from u7uo.containers import decode_member, produce_container
from u7uo.world import explain_movable


def record(shape, frame, payload, xy=(1, 3)):
    body = struct.pack("<BBH", *xy, shape + (frame << 10)) + payload
    return bytes([len(body)]) + body


def example():
    tfa = bytearray(3072)
    for shape, category in ((11, 5), (20, 6), (21, 6), (50, 7), (60, 9), (61, 11)):
        tfa[3 * shape + 1] = category
    contents = bytes.fromhex("F401000000200000")
    part = record(11, 4, b"\x30\x12", (93, 31))
    # A nonzero egg trigger and virtue stone coordinates cannot own the following record.
    stream = (record(50, 7, contents) + record(61, 0, contents) +
              record(60, 0, contents) + record(20, 2, contents) + record(21, 0, contents) +
              b"\x02\x04\x00" + part + part + b"\x01\x00\x01\x00")
    return tfa, stream


class ContainerTests(unittest.TestCase):
    def test_explain_uses_attached_holds_position_and_keeps_duplicate_children(self):
        tfa,data=example()
        rows,_=decode_member(data,tfa,300,"b"*64,13)
        boat,hold,crate,first,second=rows[2:]
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            (root/"world-ireg").mkdir()
            (root/"world-ireg/u7ireg0d.json").write_text(json.dumps({"objects":rows}),encoding="utf-8")
            item=explain_movable(root,first["id"])
            self.assertEqual(item["position_source_id"],hold["id"])
            self.assertEqual(item["initial_world_position"],[*hold["world_xy"],hold["lift"]])
            self.assertEqual(item["owner_chain"],[crate["id"],hold["id"],boat["id"]])
            self.assertEqual(explain_movable(root,crate["id"])["children"],[first["id"],second["id"]])
            with self.assertRaisesRegex(ValueError,"No such movable"):
                explain_movable(root,first["id"].replace("b"*64,"c"*64))

    def test_nested_order_control_tags_and_duplicate_identity(self):
        tfa, data = example()
        objects, markers = decode_member(data, tfa, 300, "b" * 64)
        egg, stone, boat, hold, crate, item, duplicate = objects
        self.assertEqual([o["parent"] for o in (egg, stone, boat)], [None, None, None])
        self.assertEqual((boat["kind"], hold["edge"]), ("barge", "barge_member"))
        self.assertEqual(boat["world_xy"], [1025, 2051])
        self.assertNotIn("gump_xy", hold)
        self.assertEqual(crate["parent"], hold["id"])
        self.assertEqual((item["parent"], duplicate["parent"]), (crate["id"], crate["id"]))
        self.assertEqual((item["gump_xy"], item["lift"]), ([93, 31], 3))
        self.assertEqual(item["inventory_depth"], 2)
        self.assertEqual((item["ordinal"], duplicate["ordinal"]), (0, 1))
        self.assertNotEqual(item["id"], duplicate["id"])
        self.assertEqual(item["payload_hex"], duplicate["payload_hex"])
        self.assertEqual(duplicate["archive_offset"], 300 + duplicate["offset"])
        self.assertEqual([m["tag"] for m in markers], [2, 1, 0, 1, 0])
        self.assertEqual(markers[0]["index_word"], 4)
        self.assertEqual(markers[0]["parent"], crate["id"])
        loaded = json.loads(json.dumps(objects))
        self.assertEqual([o["id"] for o in loaded if o["parent"] == crate["id"]],
                         [item["id"], duplicate["id"]])

    def test_bad_and_extended_inputs_are_reported(self):
        tfa, data = example()
        for wrong in (data[:-3], b"\x02\x01", b"\x0c\x01\x00", data + b"\xff\x01",
                      record(500, 0, bytes(8))):
            with self.subTest(wrong=wrong):
                with self.assertRaises(ValueError):
                    decode_member(wrong, tfa, 300, "b" * 64)

    def test_initial_flex_not_save_and_no_evidence_for_empty_inventory(self):
        tfa, data = example()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            static = root / "u7" / "STATIC"
            static.mkdir(parents=True)
            (static / "TFA.DAT").write_bytes(tfa)
            def seed(payload):
                header = bytearray(136)
                struct.pack_into("<III", header, 80, 0xFFFF1A00, 1, 0xCC)
                member = b"u7ireg64".ljust(13, b"\0") + payload
                struct.pack_into("<II", header, 128, len(header), len(member))
                (static / "INITGAME.DAT").write_bytes(header + member)
            seed(data)
            out = root / "build"
            result = produce_container(static.parent, out)
            self.assertEqual(result, json.loads((out / "container.json").read_bytes()))
            self.assertEqual((result["witness_objects"], result["max_inventory_depth"]), (5, 2))
            self.assertEqual(result["emitted_uo_objects"], 0)
            seed(b"\0")
            with self.assertRaisesRegex(ValueError, "No positive inventory"):
                produce_container(static.parent, root / "empty")
            self.assertFalse((root / "empty" / "container.json").exists())


if __name__ == "__main__":
    unittest.main()
