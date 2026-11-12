import hashlib
import json
import os
import struct
import tempfile
import unittest
import zlib
from pathlib import Path

from u7uo.gump_overlay import ARCHIVE, BLOCK, ENTRY, GUMP_HASH, HEADER, _directory, overlay_bytes, stage_gump_overlay


def stock_uop(key=17):
    data = b"sample stock data"
    block = HEADER.size
    offset = block + BLOCK.size + ENTRY.size * 3
    return (HEADER.pack(0x50594D, 4, 0, block, 3, 1) + BLOCK.pack(1, 0)
            + ENTRY.pack(offset, 0, len(data), len(data), key, 0, 0) + bytes(ENTRY.size * 2) + data)


def sample(folder):
    stock, stage, proof = [folder / f for f in ["stock","stage","proof"]]
    for path in [stock,stage,proof]:
        path.mkdir()
    (stock / ARCHIVE).write_bytes(stock_uop())
    os.link(stock / ARCHIVE, stage / ARCHIVE)
    (stage / "MainMisc.uop").write_bytes(b"profile marker")
    art = struct.pack("<IHHHH", 1, 0x8000, 1, 0, 1)
    (proof / "gumpart.mul").write_bytes(art)
    (proof / "gumpidx.mul").write_bytes(struct.pack("<III", 0, len(art), 2 << 16 | 1))
    spec = {"character":"Finnigan", "binding":{"function":0x40C, "npc_ref":-12}, "shape":12, "frame":0,
            "width":2, "height":1, "opaque_pixels":1, "gump_id":0,
            "expected_rgba_sha256":hashlib.sha256(bytes([0,0,0,255,0,0,0,0])).hexdigest()}
    (proof / "portrait.json").write_text(json.dumps(spec))
    return stock,stage,proof


class GumpTests(unittest.TestCase):
    def test_preserves_stock_hardlink_and_native_style_header(self):
        with tempfile.TemporaryDirectory() as tmp:
            stock, stage, proof = sample(Path(tmp))
            original = (stock / ARCHIVE).read_bytes()
            result = stage_gump_overlay(stock, stage, proof)
            self.assertEqual(result["stock_entries"], 1)
            self.assertEqual(result["overlay_entries"], 2)
            self.assertEqual((stock / ARCHIVE).read_bytes(), original)
            data = (stage / ARCHIVE).read_bytes()
            old_end, entries = _directory(data)[1:]
            self.assertEqual(old_end, len(original))
            self.assertEqual(entries[17], _directory(original)[2][17])
            start,size,stored,full,_,checksum,flag = entries[GUMP_HASH]
            self.assertEqual((size,stored,full,flag), (12,20,20,0))
            self.assertEqual(zlib.adler32(data[start:start+size]), checksum)
            self.assertEqual(data[start+size:], struct.pack("<II",2,1) + (proof/"gumpart.mul").read_bytes())

    def test_collisions_cycles_truncation_and_invalid_directory_counts(self):
        raw = stock_uop()
        cycle = bytearray(raw)
        struct.pack_into("<Q",cycle,HEADER.size+4,HEADER.size)
        wrong_count = bytearray(raw)
        struct.pack_into("<I",wrong_count,24,10)
        overlap = bytearray(raw)
        struct.pack_into("<Q",overlap,HEADER.size+BLOCK.size,HEADER.size)
        for malformed, error in [(stock_uop(GUMP_HASH),"occupied"), (cycle,"Cyclic"), (wrong_count,"count"),
                                 (raw[:-2],"beyond"),(overlap,"Overlapping")]:
            with self.subTest(error=error), self.assertRaisesRegex(ValueError,error):
                overlay_bytes(malformed,b"data")

    def test_alias_shadow_and_malformed_portrait_leave_private_file_intact(self):
        with tempfile.TemporaryDirectory() as tmp:
            stock, stage, proof = sample(Path(tmp))
            for line in ["64012 {12} 0", "8100 {64012} 0"]:
                (stage / "gump.def").write_text(line)
                with self.assertRaisesRegex(ValueError,"gump.def"):
                    stage_gump_overlay(stock,stage,proof)
            (stage / "gump.def").write_text("# 64012 is only a comment")
            (stage / "Gumps").mkdir()
            (stage / "Gumps/00064012.gump").write_bytes(b"shadow")
            with self.assertRaisesRegex(ValueError,"loose-file override"):
                stage_gump_overlay(stock,stage,proof)
            (stage / "Gumps/00064012.gump").unlink()
            (proof / "gumpart.mul").write_bytes(struct.pack("<IHHHH",1,0x8000,2,0,1))
            with self.assertRaisesRegex(ValueError,"pixel run"):
                stage_gump_overlay(stock,stage,proof)
            self.assertEqual((stage / ARCHIVE).read_bytes(),stock_uop())
            with self.assertRaisesRegex(ValueError,"separate"):
                stage_gump_overlay(stock,stock,proof)
