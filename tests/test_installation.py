"""Fresh runs must not depend on maintainer saves or mutate original data."""
import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch


path = Path(__file__).resolve().parents[1] / 'game/qualification/reference.py'
spec = importlib.util.spec_from_file_location('installation_reference', path)
reference = importlib.util.module_from_spec(spec)
spec.loader.exec_module(reference)


class FreshRunTests(unittest.TestCase):
    def test_fresh_run_uses_local_data_without_private_fixture(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            game = root / 'original'
            (game / 'STATIC').mkdir(parents=True)
            (game / 'STATIC/INITGAME.DAT').write_bytes(b'local test data')
            (game / 'U7.CFG').write_bytes(b'local configuration')
            runtime = root / 'runtime'
            with patch.object(reference, 'ROOT', runtime), patch.object(reference, 'GAME', game):
                reference.stage('new-player', fresh=True)
                run = runtime / 'runs/new-player'
                self.assertEqual(list((run / 'GAMEDAT').iterdir()), [])
                self.assertEqual((run / 'STATIC/INITGAME.DAT').read_bytes(), b'local test data')
                self.assertEqual((run / 'U7.CFG').read_bytes(), b'local configuration')
                (run / 'STATIC/INITGAME.DAT').write_bytes(b'changed copy')
                self.assertEqual((game / 'STATIC/INITGAME.DAT').read_bytes(), b'local test data')
                with self.assertRaises(FileExistsError):
                    reference.stage('new-player', fresh=True)
                self.assertEqual((run / 'STATIC/INITGAME.DAT').read_bytes(), b'changed copy')
                with self.assertRaises(ValueError):
                    reference.stage('../outside', fresh=True)


if __name__ == '__main__':
    unittest.main()
