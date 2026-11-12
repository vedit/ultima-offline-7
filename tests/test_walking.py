import struct
import unittest

from u7uo.walking import (HEIGHT, _components, _find_route, _flat_neighbor, encode_statics,
                          to_local, to_world)


class WalkingTests(unittest.TestCase):
    def test_original_axes_endpoints_and_inverse(self):
        self.assertEqual(to_local(1079, 2214), (135, 102))
        self.assertEqual(to_local(1048, 2215), (104, 103))
        self.assertEqual(to_local(1068, 2197), (124, 85))
        self.assertEqual(to_local(980, 2196), (36, 84))
        self.assertEqual(to_local(968, 2134), (24, 22))
        self.assertEqual(to_local(949, 2257), (5, 145))
        for xy in [(1032, 2208), (1048, 2215), (1079, 2214), (1087, 2223)]:
            self.assertEqual(to_world(*to_local(*xy)), xy)

    def test_path_uses_only_adjacent_unblocked_tiles(self):
        blocked = {(5, y) for y in range(HEIGHT) if y != 11}
        route = _find_route((7, 5), (2, 5), blocked)
        self.assertIn([5, 11], route)
        self.assertFalse(set(map(tuple, route)) & blocked)
        self.assertTrue(all(abs(a[0] - b[0]) + abs(a[1] - b[1]) == 1 for a, b in zip(route, route[1:])))
        with self.assertRaisesRegex(ValueError, "No cardinal path"):
            _find_route((7, 5), (2, 5), blocked | {(5, 11)})

    def test_neighbor_underlay_uses_source_coordinates_and_chunk_bounds(self):
        class World:
            def tile(self, x, y):
                # Chunk (1,1). The closer tile at (15,17) is in a different chunk.
                return {"shape": 147 if (x, y) in ((15, 17), (18, 27)) else 453}
        tile, donor = _flat_neighbor(World(), 16, 17)
        self.assertEqual((tile["shape"], donor), (147, [18, 27]))

    def test_height_calibration_and_source_footprint(self):
        table = bytearray(3072)
        table[920 * 3:920 * 3 + 3] = bytes.fromhex("a80e01")
        pillar = {"x": 1035, "y": 2209, "id": "source-object", "family": "IFIX",
                  "shape": 920, "frame": 2, "lift": 3}
        material = {"id": 219, "height": 20}
        parts = _components(pillar, table, material)
        self.assertEqual([(p["x"], p["y"], p["z"]) for p in parts], [(91, 97, 12), (90, 97, 12)])
        self.assertEqual({p["source_id"] for p in parts}, {"source-object"})
        rotated = _components({**pillar, "frame": 34}, table, material)
        self.assertEqual([(p["x"], p["y"]) for p in rotated], [(91, 97), (91, 96)])
        with self.assertRaisesRegex(ValueError, "calibrates"):
            _components(pillar, table, {"id": 219, "height": 21})

    def test_static_mul_multiset_coordinates_and_bounds(self):
        a = {"x": 13, "y": 18, "z": -3, "id": 1234, "hue": 49}
        idx, data = encode_statics(16, 24, [a, a])
        self.assertEqual(len(idx), 6 * 12)
        self.assertEqual(struct.unpack_from("<iii", idx, 5 * 12), (0, 14, 0))
        self.assertEqual(struct.unpack_from("<HBBbH", data), (1234, 5, 2, -3, 49))
        self.assertEqual(data[:7], data[7:])
        with self.assertRaises(ValueError):
            encode_statics(16, 24, [a] * 1025)
        with self.assertRaises(ValueError):
            encode_statics(16, 24, [{**a, "z": 128}])

    def test_source_stair_and_upper_floor_have_matching_standing_heights(self):
        table = bytearray(3072)
        table[973*3:973*3+3] = bytes((136,4,16))
        table[367*3:367*3+3] = bytes((40,14,27))
        obj = {"x":967,"y":2140,"shape":973,"frame":0,"lift":0,"family":"IREG","id":"step"}
        parts = _components(obj,table,{"id":0x7b7,"height":8})
        self.assertEqual([(p["x"],p["y"],p["z"]+4) for p in parts],
                         [(23,28,16),(23,27,16),(23,26,16)])
        floor = _components({**obj,"shape":367,"family":"IFIX","lift":5},table,{"id":0x51a,"height":0})
        self.assertEqual({p["z"] for p in floor},{24})


if __name__ == "__main__":
    unittest.main()
