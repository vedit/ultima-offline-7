import struct
import tempfile
import unittest
from pathlib import Path

from u7uo.regional_items import compile_placements, disposition, write


class RegionalItemsTests(unittest.TestCase):
    def test_compile_keeps_complete_trees_in_their_original_coordinate_spaces(self):
        rules = {"2":{"tfa":"000600","art":[{"id":20}]},
                 "3":{"tfa":"000200","art":[{"id":30},{"id":31}]}}
        frames = [0,0,-1,-2]
        root = {"id":"container","root":None,"offset":0,"parent":None,"kind":"container",
                "shape":2,"frame":0,"edge":"world","world_xy":[9,2],"lift":2,"ordinal":5,
                "payload_hex":"000000000000000000000000"}
        child = {"id":"spoon","root":"container","offset":13,"parent":"container","kind":"simple",
                 "shape":3,"frame":33,"edge":"inventory","gump_xy":[42,45],"lift":0,"ordinal":0,
                 "payload_hex":"000000000000"}
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            for folder in ("walking","water","world-ireg"):
                (d/folder).mkdir()
            write(d/"story-seed.json",{"seed_sha256":"synthetic"})
            write(d/"container.json",{"objects":[]})
            write(d/"world-land.json",{"graphic_frame_counts":frames})
            (d/"world-land.idx").write_bytes(struct.pack("<i",-1)*(384*384))
            (d/"world-land.mul").write_bytes(b"")
            for folder in ("walking","water"):
                cells = [{"x":1,"y":2,"land_id":100}] if folder=="walking" else []
                write(d/folder/"terrain.json",{"source_origin":[8,0],"cells":cells,"statics":[]})
            for region in range(144):
                write(d/"world-ireg"/f"u7ireg{region:02x}.json",{"objects":[root,child] if region==0 else []})
            live, coverage = compile_placements(d,rules)
            self.assertEqual([(r["id"],r["parent"],r["xy"],r["land"],r["art"]) for r in live["objects"]],
                             [("container",None,[9,2],100,20),("spoon","container",[42,45],None,31)])
            self.assertEqual(coverage["dispositions"],{"live":2})
            # A missing child rule defers the container and its contents together.
            live, coverage = compile_placements(d,{"2":rules["2"]})
            self.assertEqual(live["objects"],[])
            self.assertEqual(coverage["dispositions"],{"unmapped-shape:3":2})
        for reason,rows,land,reserved in (
            ("existing-import",[root,child],1,{"container","spoon"}),
            ("unsupported-object-kind",[root,{**child,"edge":"barge_member"}],1,set()),
            ("missing-source-frame",[root,{**child,"frame":2}],1,set()),
            ("unresolved-land",[root,child],None,set()),
            ("unresolved-land",[root,child],0x1fa,set()),
        ):
            with self.subTest(reason=reason,land=land):
                self.assertEqual(disposition(rows,rules,frames,reserved,land),reason)
