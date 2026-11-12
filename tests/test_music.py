import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from u7uo.music import CONFIG, TRACK, stage_music


class OpeningMusicTests(unittest.TestCase):
    def test_private_entry_preserves_stock_and_rejects_slot_collisions(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            proof, assets = root / "proof", root / "assets"
            proof.mkdir()
            config = assets / CONFIG
            config.parent.mkdir(parents=True)
            data = b"synthetic encoded cue"
            cue = {"client_slot": 200, "repeat": False, "path": TRACK, "sha256": hashlib.sha256(data).hexdigest()}
            (proof / "music.json").write_text(json.dumps({"tracks": {"35": cue}}))
            (proof / Path(TRACK).name).write_bytes(data)
            config.write_bytes(b"1 original.mp3\n200 occupied,loop")
            with self.assertRaisesRegex(ValueError, "occupied"):
                stage_music(proof, assets)
            self.assertFalse((assets / TRACK).exists())
            stock = b"1 original.mp3\n\n"
            config.write_bytes(stock)
            stage_music(proof, assets)
            self.assertEqual(config.read_bytes(), stock + b"200 u7bg035.mp3\r\n")
            self.assertEqual((assets / TRACK).read_bytes(), data)
