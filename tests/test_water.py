import json
import struct
import tempfile
import unittest
from pathlib import Path

from u7uo.terrain import CHUNK_BYTES, MAP_BYTES
from u7uo.water import produce_water


class WaterTests(unittest.TestCase):
    def test_wet_chunk_is_generated_at_its_original_origin(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            static, uo = root / "u7/STATIC", root / "uo"
            static.mkdir(parents=True)
            uo.mkdir()
            (static / "U7MAP").write_bytes(bytes(MAP_BYTES))
            (static / "U7CHUNKS").write_bytes(b"".join(
                struct.pack("<H", 8 + ((i % 4) << 10)) for i in range(CHUNK_BYTES // 2)))
            tfa = bytearray(3072)
            tfa[8 * 3] = 0x10
            (static / "TFA.DAT").write_bytes(tfa)
            tiledata = bytearray(3188736)
            for i in range(168, 172):
                struct.pack_into("<QH20s", tiledata, i // 32 * 964 + 4 + i % 32 * 30, 0xC0, i, b"water")
            (uo / "tiledata.mul").write_bytes(tiledata)
            out = root / "water"
            r = produce_water(static.parent, uo, out)
            self.assertEqual(json.loads((out / "terrain.json").read_bytes()), r)
            self.assertEqual(r["source_origin"], [1136, 2208])
            self.assertEqual(r["cell_count"], 256)
            self.assertEqual({x["land_id"] for x in r["cells"]}, {168,169,170,171})
            tfa[8 * 3] = 0
            (static / "TFA.DAT").write_bytes(tfa)
            with self.assertRaisesRegex(ValueError, "non-water"):
                produce_water(static.parent, uo, root / "dry")
            self.assertFalse((root / "dry").exists())


if __name__ == "__main__":
    unittest.main()
