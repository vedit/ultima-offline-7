"""Save-copy boundaries using actual native archive parsing and temporary runs."""
import json
import struct
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import play


def archive():
    members={'U7IBUF.DAT':b'items','U7NBUF.DAT':b'actors','PARTY':b'party','RANDSEED.DAT':b'rng'}
    data=bytearray(128+8*len(members));struct.pack_into('<I',data,0x54,len(members))
    for index,(name,value) in enumerate(members.items()):
        body=name.encode().ljust(13,b'\0')+value
        struct.pack_into('<II',data,128+index*8,len(data),len(body));data.extend(body)
    return bytes(data)


class TestCopy(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);self.runs=self.root/'runs';self.runs.mkdir()
        self.source=self.runs/'player-investigation';self.source.mkdir()
        self.save=self.source/'GAME00.U7';self.save.write_bytes(archive())
        def stage(name, *, fresh=False):
            self.assertTrue(fresh, 'Copies must not require a maintainer fixture')
            folder=self.runs/name;folder.mkdir(exist_ok=False);(folder/'GAMEDAT').mkdir()
        self.root_patch=patch.object(play,'ROOT',self.root);self.root_patch.start();self.addCleanup(self.root_patch.stop)
        self.stage_patch=patch.object(play,'stage',stage);self.stage_patch.start();self.addCleanup(self.stage_patch.stop)

    def test_copy_is_independent_and_resumable(self):
        before=self.save.read_bytes()
        dest=play.copy_test_save('player-investigation','wand-test')
        self.assertEqual((dest/'GAME00.U7').read_bytes(),before)
        self.assertEqual(len(play.members(dest/'GAME00.U7')),4)
        self.assertEqual(json.loads((dest/'test-copy.json').read_text())['source_run'],'player-investigation')
        (dest/'GAME00.U7').write_bytes(b'later test save')
        self.assertEqual(self.save.read_bytes(),before)
        with self.assertRaises(FileExistsError):play.copy_test_save('player-investigation','wand-test')
        self.assertEqual((dest/'GAME00.U7').read_bytes(),b'later test save')

    def test_existing_empty_run_is_not_reused(self):
        (self.runs/'existing').mkdir()
        with self.assertRaises(FileExistsError):play.copy_test_save('player-investigation','existing')
        self.assertEqual(list((self.runs/'existing').iterdir()),[])

    def test_missing_corrupt_or_changing_source_is_not_staged(self):
        with self.assertRaises(FileNotFoundError):play.copy_test_save('missing','test-missing')
        self.save.write_bytes(archive()[:128])
        with self.assertRaises((ValueError,struct.error)):play.copy_test_save('player-investigation','test-corrupt')
        self.save.write_bytes(archive())
        original=play.members
        def changed(path):
            result=original(path);self.save.write_bytes(archive()+b'changed');return result
        with patch.object(play,'members',changed):
            with self.assertRaises(RuntimeError):play.copy_test_save('player-investigation','test-changing')
        self.assertFalse(any(p.name.startswith('test-') for p in self.runs.iterdir()))

    def test_path_traversal_and_same_run_are_rejected(self):
        for source,dest in (('../outside','test'),('player-investigation','../outside'),('player-investigation','bad/name')):
            with self.assertRaises(ValueError):play.copy_test_save(source,dest)
        with self.assertRaises(FileExistsError):play.copy_test_save('player-investigation','player-investigation')


if __name__=='__main__':unittest.main()
