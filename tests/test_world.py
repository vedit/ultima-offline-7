import hashlib
import json
import struct
import tempfile
import unittest
from pathlib import Path

from u7uo.containers import decode_member
from u7uo.terrain import UNRESOLVED_LAND
from u7uo.world import count_terrain_words, schedule_entries
from u7uo.world_land import compile_world_blocks, explain_world_cell, region_map, verify_world_land
from u7uo.world_substrate import chunk_underlays, substrate_chunks


class WorldTests(unittest.TestCase):
    def test_underlay_uses_first_available_graphic_even_when_unmapped(self):
        frames = [0]*1024
        frames[1],frames[2],frames[3],frames[12] = 2,1,-1,1
        words = [3]*256
        words[0],words[18],words[19],words[35] = 1,0x800c,2,1
        words[180] = 1+(2<<10)
        donors = chunk_underlays(words,frames)
        self.assertEqual(donors[34],19)  # Cycling void is skipped in the neighborhood.
        self.assertEqual(donors[200],0)  # Full chunk search includes its first row.
        self.assertEqual(donors[18],18)
        self.assertIsNone(donors[180])  # A missing source frame is diagnosed.
        words = [3]*256
        self.assertEqual(set(chunk_underlays(words,frames)),{None})
        self.assertEqual(substrate_chunks(struct.pack("<256H",*words),frames),bytes([255])*512)

    def test_world_land_uses_native_block_order_and_omits_only_unresolved_quadrants(self):
        # In region 13, place a distinct chunk one column and two rows inward.
        world = bytearray(73728)
        struct.pack_into("<H",world,(13*256+2*16+1)*2,1)
        special = [1 + (((x+2*y)%4)<<10) for y in range(16) for x in range(16)]
        special[8*16] = 9
        for y in range(8,16):
            special[y*16+8:y*16+16] = [9]*8
        chunks = bytes(512) + struct.pack("<256H",*special)
        index, pool, counts, regions = compile_world_blocks(world,chunks,{0:(30,1),1:(50,4)})
        self.assertEqual(regions[13],1023)
        self.assertEqual(sum(regions),384**2-1)
        self.assertEqual(counts[9],65)
        def entry(x,y):
            return struct.unpack_from("<i",index,4*(x*384+y))[0]
        self.assertEqual(entry(35,37),-1)
        for bx,by in ((34,36),(35,36),(34,37)):
            i = entry(bx,by)
            self.assertGreaterEqual(i,0)
            for y in range(8):
                for x in range(8):
                    land = UNRESOLVED_LAND if (bx,by,x,y)==(34,37,0,0) else 50+(x+2*y)%4
                    self.assertEqual(struct.unpack_from("<Hb",pool,196*i+4+3*(8*y+x)),(land,0))
        self.assertNotEqual(entry(383,383),-1)
        with self.assertRaisesRegex(ValueError, "missing or invalid block"):
            region_map(13,index,pool)
        native = region_map(143,index,pool)
        self.assertEqual(len(native),196*1024)
        self.assertEqual(struct.unpack_from("<Hb",native,4),(30,0))

        report = {"schema":3,"unresolved_land_id":UNRESOLVED_LAND,
                  "source_sha256":{"U7MAP":hashlib.sha256(world).hexdigest(),
                                   "U7CHUNKS":hashlib.sha256(chunks).hexdigest()},
                  "materials":[{"shape":0,"first_land_id":30,"variants":1},{"shape":1,"first_land_id":50,"variants":4}],
                  "total_blocks":384**2,"emitted_blocks":sum(regions),"distinct_native_blocks":len(pool)//196,
                  "mixed_blocks":1,"fully_mapped_blocks":sum(regions)-1,"cells_with_land_rule":3072**2-65}
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            (d/"world-land.source").write_bytes(world+chunks)
            (d/"world-land.mul").write_bytes(pool)
            (d/"world-land.idx").write_bytes(index)
            (d/"world-land.json").write_text(json.dumps(report))
            self.assertEqual(explain_world_cell(d,272,296,report)["padding"]["land_id"],UNRESOLVED_LAND)
            self.assertEqual(explain_world_cell(d,273,296,report)["native"]["land_id"],51)
            self.assertEqual(verify_world_land(d)["padding_cells"],65)
            damaged = bytearray(pool)
            struct.pack_into("<H",damaged,196*entry(34,37)+4,50)
            (d/"world-land.mul").write_bytes(damaged)
            with self.assertRaisesRegex(ValueError,"source 272,296"):
                verify_world_land(d)

    def test_world_provenance_and_detecting_wrong_pool_reference(self):
        world = bytes(73728)
        chunks = struct.pack("<256H",0x8001,*([1]*255))
        index,pool,_,_ = compile_world_blocks(world,chunks,{1:(50,4)})
        report = {"source_sha256":{"U7MAP":hashlib.sha256(world).hexdigest(),
                                   "U7CHUNKS":hashlib.sha256(chunks).hexdigest()},
                  "materials":[{"shape":1,"first_land_id":50,"variants":4}],
                  "total_blocks":384**2,"emitted_blocks":384**2,"distinct_native_blocks":1}
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            (d/"world-land.source").write_bytes(world+chunks)
            (d/"world-land.mul").write_bytes(pool)
            (d/"world-land.idx").write_bytes(index)
            (d/"world-land.json").write_text(json.dumps(report))
            cell = explain_world_cell(d,0,0,report)
            self.assertEqual((cell["source"]["high_bit"],cell["source"]["frame"],cell["native"]["land_id"]),(1,0,50))
            self.assertEqual(verify_world_land(d)["matched_cells"],3072**2)
            (d/"world-land.idx").write_bytes(struct.pack("<i",-1)+index[4:])
            with self.assertRaisesRegex(ValueError,"source 0,0"):
                verify_world_land(d)
    def test_explain_distinguishes_a_missing_frame_from_a_missing_material(self):
        chunks = struct.pack("<256H",48+(8<<10),*([1]*255))
        counts = [0]*1024
        counts[1],counts[48] = 1,5
        report = {"schema":3,"graphic_frame_counts":counts,
                  "materials":[{"shape":48,"first_land_id":1,"variants":1}]}
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            (d/"world-land.source").write_bytes(bytes(73728)+chunks)
            (d/"world-land.idx").write_bytes(struct.pack("<i",0))
            (d/"world-land.mul").write_bytes(bytes(4)+struct.pack("<Hb",UNRESOLVED_LAND,0))
            cell = explain_world_cell(d,0,0,report)
            self.assertIn("frame 8",cell["diagnostic"])
            self.assertIn("5 frames",cell["diagnostic"])
            self.assertEqual(cell["padding"]["land_id"],UNRESOLVED_LAND)

    def test_schedule_owner_empty_slots_offsets_and_end(self):
        raw = struct.pack("<5H", 3, 0, 0, 2, 3) + bytes([17, 4, 5, 13, 35, 6, 7, 0, 255, 1, 0, 143])
        rows = schedule_entries(raw)
        self.assertEqual([r["npc_slot"] for r in rows], [1, 1, 2])
        self.assertEqual([r["offset"] for r in rows], [10, 14, 18])
        self.assertEqual((rows[0]["time_slot"], rows[0]["activity"], rows[0]["world_xy"]), (1, 2, [260, 261]))
        for bad in (raw[:-1], raw + bytes(4), raw[:6] + bytes([3, 0, 2, 0]) + raw[10:],
                    raw[:-1] + bytes([144])):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                schedule_entries(bad)

    def test_spellbook_and_same_offset_in_another_region(self):
        shape = 761
        tfa = bytearray(3072)
        tfa[shape * 3 + 1] = 8
        body = struct.pack("<BBH", 7, 9, shape) + bytes(5) + bytes([48]) + bytes(8)
        stream = bytes([18]) + body + bytes([0])
        first, marks = decode_member(stream, tfa, 900, "a" * 64, 1)
        other, _ = decode_member(stream, tfa, 2000, "a" * 64, 13)
        self.assertEqual((first[0]["kind"], first[0]["lift"], marks[0]["offset"]), ("spellbook", 3, 19))
        self.assertNotEqual(first[0]["id"], other[0]["id"])
        self.assertEqual(other[0]["world_xy"], [263, 265])
        self.assertEqual(other[0]["archive_offset"], 2000)

    def test_terrain_frequency_weights_placements_and_excludes_unused_definitions(self):
        world = bytes([1, 0]) + bytes(73726)
        chunks = bytes(512) + struct.pack("<H", 64 + (5 << 10)) * 256 + bytes([255]) * 512
        words = count_terrain_words(world, chunks)
        self.assertEqual(words, {0: 3072 ** 2 - 256, 64 + (5 << 10): 256})
