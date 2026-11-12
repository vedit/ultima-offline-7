import struct
import tempfile
import unittest
from pathlib import Path

from u7uo.walking import world_component_positions
from u7uo.world_statics import BOULDER_BASE, BOULDER_CAP, mountain_material, read_native_blocks, static_layers


class WorldStaticTests(unittest.TestCase):
    def test_mountain_layers_fill_only_the_southeast_anchored_footprint(self):
        shape = 395
        tfa = bytearray(3072)
        tfa[3*shape:3*shape+3] = bytes((0xa8,0,0x1b))
        tiles = bytearray(512*964+(max(BOULDER_CAP+BOULDER_BASE)//32+1)*1316)
        for ids,height in ((BOULDER_BASE,15),(BOULDER_CAP,5)):
            for art in ids:
                at = 512*964+art//32*1316+4+art%32*41
                struct.pack_into("<Q",tiles,at,0x4040)
                tiles[at+20] = height
                tiles[at+21:at+28] = b"boulder"
        material = mountain_material(shape,-8,tfa,b"mountain",{shape:(0,8)},tiles)
        obj = {"family":"U7CHUNKS","shape":shape,"frame":2,"x":499,"y":2319,"lift":0}
        ground = set(world_component_positions(obj,tfa,material))
        self.assertEqual(ground,{(x,y,0) for x in range(496,500) for y in range(2316,2320)})
        base,cap = static_layers(material,2)
        self.assertEqual((base[1],cap[1]),(0,15))
        self.assertEqual([l["height"] for l in material["frame_layers"][2]],[15,5])
        tfa[3*shape] &= ~8
        with self.assertRaisesRegex(ValueError,"collision"):
            mountain_material(shape,-8,tfa,b"mountain",{shape:(0,8)},tiles)

    def test_reflected_source_footprint_crosses_block_boundary(self):
        tfa = bytearray(3072)
        tfa[3*369:3*369+3] = bytes([0x20,14,2])
        obj = {"shape":369,"family":"IFIX","frame":32,"x":256,"y":256,"lift":5}
        self.assertEqual(list(world_component_positions(obj,tfa,{"height":0})),
                         [(256,256,24),(256,255,24),(256,254,24)])
        obj["frame"] = 0
        self.assertEqual(list(world_component_positions(obj,tfa,{"height":0})),
                         [(256,256,24),(255,256,24),(254,256,24)])

    def test_world_static_index_rejects_overlaps_and_unclaimed_bytes(self):
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            index = bytearray(struct.pack("<iii",-1,0,0)*384**2)
            struct.pack_into("<iii",index,0,0,7,0)
            (d/"staidx0.mul").write_bytes(index)
            (d/"statics0.mul").write_bytes(bytes(7))
            self.assertEqual(read_native_blocks(d)[1],{0:(0,1)})
            (d/"statics0.mul").write_bytes(bytes(14))
            with self.assertRaisesRegex(ValueError,"unaccounted"):
                read_native_blocks(d)
            struct.pack_into("<iii",index,12,0,7,0)
            (d/"staidx0.mul").write_bytes(index)
            with self.assertRaisesRegex(ValueError,"Invalid static index"):
                read_native_blocks(d)
