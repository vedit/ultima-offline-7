import hashlib
import json
import struct
import tempfile
import unittest
from pathlib import Path

from u7uo.swamp import field_contacts,verify_swamp


class SwampTests(unittest.TestCase):
    def test_field_positions_use_original_shape_before_underlay_substitution(self):
        world=bytearray(73728)
        struct.pack_into("<H",world,2*(13*256+2*16+1),1)
        words=[0]*256
        words[0],words[1],words[16]=22|(17<<10),334,67
        chunks=bytes(512)+struct.pack("<256H",*words)
        tfa=bytearray(3072)
        for s in (22,67):
            tfa[3*s+1]=16
        contacts,counts=field_contacts(world,chunks,tfa)
        self.assertEqual(list(struct.iter_unpack("<3H",contacts)),[(272,288,22),(272,289,67)])
        with tempfile.TemporaryDirectory() as tmp:
            out=Path(tmp)
            (out/"world-statics").mkdir()
            (out/"world-statics/tfa.dat").write_bytes(tfa)
            (out/"world-land.source").write_bytes(world+chunks)
            def write(data):
                (out/"swamp-fields.bin").write_bytes(data)
                (out/"swamp.json").write_text(json.dumps({"contacts_sha256":hashlib.sha256(data).hexdigest(),
                                                         "source_counts":counts}))
            write(contacts)
            self.assertEqual(verify_swamp(out)["raw_field_cells"],2)
            write(contacts[:6])
            with self.assertRaisesRegex(ValueError,"every original"):
                verify_swamp(out)
            write(contacts[:6]*2)
            with self.assertRaisesRegex(ValueError,"disagrees with source"):
                verify_swamp(out)
