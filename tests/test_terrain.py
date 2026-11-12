import hashlib
import json
import struct
import tempfile
import unittest
from pathlib import Path

from u7uo.terrain import (CHUNK_BYTES, MAP_BYTES, TerrainSource, encode_land_mul,
                          fixed_inventory, produce_terrain)


def make_flex(entries):
    count = len(entries)
    data = bytearray(128 + 8 * count)
    struct.pack_into("<III", data, 80, 0xFFFF1A00, count, 0xCC)
    for i, entry in enumerate(entries):
        if entry:
            struct.pack_into("<II", data, 128 + i * 8, len(data), len(entry))
            data.extend(entry)
    return bytes(data)


def seed_member(name, payload):
    return name.encode("ascii").ljust(13, b"\0") + payload


def synthetic_inputs(folder):
    source = folder / "u7"
    static = source / "STATIC"
    static.mkdir(parents=True)
    target = folder / "uo"
    target.mkdir()
    (static / "U7MAP").write_bytes(bytes(MAP_BYTES))
    terrain = bytearray(CHUNK_BYTES)
    for y in range(16):
        for x in range(16):
            shape = 24 if x > 2 * y else 147
            frame = (x + 2 * y) % 64
            struct.pack_into("<H", terrain, 2 * (y * 16 + x), shape | (frame << 10))
    (static / "U7CHUNKS").write_bytes(terrain)
    labels = [b""] * 149
    labels[24], labels[147] = b"cobblestone\0", b"grass\0"
    (static / "TEXT.FLX").write_bytes(make_flex(labels))
    npc_data = bytearray(4 + 117)
    struct.pack_into("<HHBB", npc_data, 0, 1, 0, 55, 166)
    npc_data[10] = 100
    (static / "INITGAME.DAT").write_bytes(make_flex([
        seed_member("identity", b"FORGE\0"), seed_member("npc.dat", npc_data)
    ]))
    ifix = [b""] * 256
    ifix[163] = struct.pack("<BBH", 0xA5, 3, 170 | (2 << 10))
    (static / "U7IFIX64").write_bytes(make_flex(ifix))
    tiles = bytearray(3188736)
    for start, name in ((3, b"grass"), (1001, b"cobblestones")):
        for i in range(start, start + 4):
            offset = i // 32 * 964 + 4 + i % 32 * 30
            struct.pack_into("<QH20s", tiles, offset, 0, i, name)
    (target / "tiledata.mul").write_bytes(tiles)
    return source, target


class TerrainTests(unittest.TestCase):
    def test_source_placement_and_seams(self):
        world = bytearray(MAP_BYTES)
        # (552,815) = superchunk (2,3), chunk (2,2), tile (8,15).
        placement = 2 * (38 * 256 + 34)
        struct.pack_into("<H", world, placement, 1)
        chunks = bytearray(2 * CHUNK_BYTES)
        at = CHUNK_BYTES + 2 * (15 * 16 + 8)
        struct.pack_into("<H", chunks, at, 0x377 | (53 << 10))
        source = TerrainSource(world, chunks)
        self.assertEqual(source.tile(552, 815), {
            "chunk_id": 1, "map_offset": placement, "chunks_offset": at,
            "shape": 0x377, "frame": 53})
        self.assertEqual(source.tile(552, 816)["chunk_id"], 0)
        self.assertEqual(source.tile(3071, 3071)["map_offset"], MAP_BYTES - 2)
        with self.assertRaises(ValueError):
            source.tile(-1, 0)

    def test_bad_geometry_and_dangling_references(self):
        with self.assertRaisesRegex(ValueError, "U7MAP"):
            TerrainSource(b"\0" * 4, bytes(CHUNK_BYTES))
        with self.assertRaisesRegex(ValueError, "whole"):
            TerrainSource(bytes(MAP_BYTES), b"\0" * 511)
        with self.assertRaisesRegex(ValueError, "missing chunk"):
            TerrainSource(b"\x01\0" + bytes(MAP_BYTES - 2), bytes(CHUNK_BYTES))

    def test_mul_block_and_cell_order_signed_height(self):
        # Three columns by two rows of blocks catches swapping width and height.
        width, height = 24, 16
        cells = [(x + 32 * y, x - 2 * y) for y in range(height) for x in range(width)]
        encoded = encode_land_mul(width, height, cells)
        self.assertEqual(len(encoded), 6 * 196)
        for n, (x, y) in enumerate(((0, 0), (0, 8), (8, 0), (8, 8), (16, 0), (16, 8))):
            self.assertEqual(encoded[n * 196:n * 196 + 4], bytes(4))
            self.assertEqual(struct.unpack_from("<Hb", encoded, n * 196 + 4),
                             (x + 32 * y, x - 2 * y))
        # The marker lies in block (2,1), row 3, column 5.
        self.assertEqual(struct.unpack_from("<Hb", encoded, 5 * 196 + 4 + 29 * 3),
                         (21 + 32 * 11, -1))
        for dimensions, values in [((7, 8), []), ((8, 8), []), ((8, 8), [(3, 128)] * 64)]:
            with self.assertRaises(ValueError):
                encode_land_mul(*dimensions, values)

    def test_end_to_end_provenance_and_determinism(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source, target = synthetic_inputs(root)
            first, second = root / "proof1", root / "proof2"
            report = produce_terrain(source, target, first)
            produce_terrain(source, target, second)
            self.assertEqual(report, json.loads((first / "terrain.json").read_text()))
            self.assertEqual(report["avatar"]["position"], [1079, 2214, 0])
            self.assertEqual(report["source_origin"], [1072, 2208])
            for item in first.iterdir():
                self.assertEqual(item.read_bytes(), (second / item.name).read_bytes())
            for name, digest in report["output_sha256"].items():
                self.assertEqual(digest, hashlib.sha256((first / name).read_bytes()).hexdigest())
            # Read one independently addressed asymmetric landmark from the generated MUL.
            marker = report["cells"][1 * 16 + 10]
            self.assertEqual((marker["shape"], marker["frame"]), (24, 12))
            self.assertEqual(struct.unpack_from("<Hb", (first / "map0.mul").read_bytes(),
                                                2 * 196 + 4 + 3 * (8 + 2)), (1001, 0))
            self.assertEqual((first / "staidx0.mul").read_bytes(), struct.pack("<iii", -1, 0, 0) * 4)
            self.assertEqual((first / "statics0.mul").read_bytes(), b"")
            self.assertEqual(sum(v["occurrences"] for v in report["rules"].values()), 256)
            self.assertEqual(report["fixed"]["records_in_ground_sample"], 1)
            self.assertEqual(report["fixed"]["emitted_statics"], 0)
            self.assertEqual(json.loads((first / "fixed.json").read_bytes())["record_count"], 1)

    def test_fixed_duplicate_identity_and_byte_provenance(self):
        entries = [b""] * 256
        raw = struct.pack("<BBH", 0xA3, 5, 903 | (33 << 10))
        entries[163] = raw + raw
        entries[164] = raw
        data = make_flex(entries)
        result = fixed_inventory(data, 100, "a" * 64)
        one, duplicate, neighbor = result["objects"]
        self.assertEqual(result["occupied_slots"], 2)
        self.assertEqual((one["x"], one["y"], one["lift"]), (1082, 2211, 5))
        self.assertEqual((one["shape"], one["frame"]), (903, 33))
        self.assertEqual((neighbor["x"], neighbor["y"]), (1098, 2211))
        self.assertEqual(len({obj["id"] for obj in result["objects"]}), 3)
        self.assertEqual((one["ordinal"], duplicate["ordinal"]), (0, 1))
        self.assertEqual((one["x"], one["y"]), (duplicate["x"], duplicate["y"]))
        self.assertEqual(duplicate["offset"], one["offset"] + 4)
        self.assertEqual(data[duplicate["offset"]:duplicate["offset"] + 4], raw)
        self.assertEqual(result, fixed_inventory(data, 100, "a" * 64))
        entries[164] = b"\x08\x00\x53"
        with self.assertRaisesRegex(ValueError, "slot 164"):
            fixed_inventory(make_flex(entries), 100, "a" * 64)

    def test_unmapped_and_changed_inputs_fail_before_output(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source, target = synthetic_inputs(root)
            chunks = source / "STATIC" / "U7CHUNKS"
            original = chunks.read_bytes()
            chunks.write_bytes(struct.pack("<H", 453) + original[2:])
            with self.assertRaisesRegex(ValueError, "Unmapped source shape 453"):
                produce_terrain(source, target, root / "unknown")
            self.assertFalse((root / "unknown").exists())
            chunks.write_bytes(original)
            tiledata = target / "tiledata.mul"
            data = bytearray(tiledata.read_bytes())
            struct.pack_into("<Q", data, 4 + 3 * 30, 0x40)
            tiledata.write_bytes(data)
            with self.assertRaisesRegex(ValueError, "UO land"):
                produce_terrain(source, target, root / "changed")
            self.assertFalse((root / "changed").exists())
            with self.assertRaisesRegex(ValueError, "outside"):
                produce_terrain(source, target, source / "proof")


if __name__ == "__main__":
    unittest.main()
