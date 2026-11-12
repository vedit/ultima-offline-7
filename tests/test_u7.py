import struct
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from u7uo import u7


def flex(payloads):
    header = bytearray(128)
    struct.pack_into("<III", header, 80, 0xFFFF1A00, len(payloads), 0xCC)
    directory = bytearray()
    body = bytearray()
    for payload in payloads:
        offset = 128 + 8 * len(payloads) + len(body) if payload else 0
        directory.extend(struct.pack("<II", offset, len(payload)))
        body.extend(payload)
    return bytes(header + directory + body)


def seed(identity):
    entries = [("npc.dat", b"synthetic NPC")]
    entries.extend((f"u7ireg{i:02x}", bytes(512)) for i in range(144))
    # The marker intentionally sits outside the position seen on Steam.
    entries.insert(3, ("identity", identity + b"\r\n\x1a"))
    return flex([name.encode().ljust(13, b"\0") + payload for name, payload in entries])


def function(function_id):
    body = struct.pack("<HHHH", 0, 0, 0, 0) + b"\x25"
    return struct.pack("<HH", function_id, len(body)) + body


def make_fixture(root):
    static = root / "static"
    static.mkdir()
    for name in u7.FIXED_REGIONS:
        (static / name.lower()).write_bytes(flex([b""] * 256))
    for name in u7.ART_ARCHIVES:
        (static / name.lower()).write_bytes(flex([b"fixture"]))
    for name, data in {
        "initgame.dat": seed(b"ULTIMA7"), "mainshp.flx": flex([b"synthetic menu"]),
        "usecode": function(42), "u7map": bytes(73728), "u7chunks": bytes(512),
        "tfa.dat": bytes(3072), "schedule.dat": b"synthetic schedule",
    }.items():
        (static / name).write_bytes(data)
    return static


class FlexTests(unittest.TestCase):
    def test_exult_crc_convention(self):
        self.assertEqual(u7.exult_crc32(b"123456789"), 0x2DFD2D88)

    def test_slot_order_and_bad_offsets(self):
        self.assertEqual(u7.flex_directory(flex([b"A", b"", b"BC"])), [(152, 1), (0, 0), (153, 2)])
        good = flex([b"AB", b"CD"])
        for damaged in [good[:120], good[:135], good[:146],
                        good[:136] + struct.pack("<II", 145, 2) + good[144:]]:
            with self.subTest(damaged=damaged), self.assertRaises(ValueError):
                u7.flex_directory(damaged)

    def test_duplicate_and_invalid_seed_entries(self):
        token = b"identity".ljust(13, b"\0")
        for payloads in [[token + b"FORGE", token + b"ULTIMA7"], [b"two"], [b"../foo".ljust(13, b"\0") + b"x"]]:
            with self.subTest(payloads=payloads), self.assertRaises(ValueError):
                u7.seed_directory(flex(payloads))

    def test_function_provenance_and_malformed_tables(self):
        raw = function(5) + function(7)
        records = u7.usecode_inventory(raw)["records"]
        self.assertEqual([(r["id"], r["offset"], r["code_offset"]) for r in records], [(5, 0, 12), (7, 13, 25)])
        for damaged in [raw[:-1], raw + b"x", function(5) * 2,
                        struct.pack("<HHHHHH", 5, 8, 5, 0, 0, 0),
                        struct.pack("<HHHHHH", 5, 8, 0, 0, 0, 1)]:
            with self.subTest(damaged=damaged), self.assertRaises(ValueError):
                u7.usecode_inventory(damaged)


class EditionTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.static = make_fixture(self.root)
        self.crc = u7.exult_crc32((self.static / "mainshp.flx").read_bytes())

    def inspect_as(self, menu_edition, language="en"):
        # The synthetic archives are never registered as retail fingerprints.
        with patch.dict(u7.MENU_VARIANTS, {self.crc: (menu_edition, language)}):
            return u7.inspect_u7(self.root)

    def test_marker_agreement_and_mutable_save_isolation(self):
        report = self.inspect_as("ULTIMA7")
        self.assertEqual((report["status"], report["ready"]), ("vanilla", True))
        self.assertIsNone(report["matched_profile"])
        self.assertEqual(report["vanilla_gameplay_qualification"], "not_run")
        self.assertEqual(report["usecode"]["count"], 1)
        identity = next(m for m in report["seed_members"] if m["name"] == "identity")
        self.assertEqual(identity["slot"], 3)
        gamedat = self.root / "GAMEDAT"
        gamedat.mkdir()
        (gamedat / "IDENTITY").write_bytes(b"FORGE")
        (gamedat / "USECODE.DAT").write_bytes(function(500))
        self.assertEqual(report, self.inspect_as("ULTIMA7"))
        (self.static / "initgame.dat").write_bytes(seed(b"FORGE"))
        self.assertEqual(self.inspect_as("FORGE")["status"], "expanded")
        mixed = self.inspect_as("ULTIMA7")
        self.assertEqual((mixed["status"], mixed["ready"]), ("mixed", False))

    def test_missing_unknown_and_localizations(self):
        unknown = u7.inspect_u7(self.root)
        self.assertEqual((unknown["status"], unknown["ready"]), ("unknown", False))
        localized = self.inspect_as("ULTIMA7", "de")
        self.assertEqual((localized["language"], localized["ready"]), ("de", False))
        (self.static / "u7ifix3a").unlink()
        missing = self.inspect_as("ULTIMA7")
        self.assertEqual((missing["status"], missing["ready"]), ("missing", False))
        self.assertIn("U7IFIX3A", missing["diagnostics"][0])
        self.assertEqual(u7.inspect_u7(self.root / "absent")["status"], "missing")

    def test_out_of_range_chunk_reference_fails(self):
        placements = bytearray(73728)
        struct.pack_into("<H", placements, 73726, 1)
        (self.static / "u7map").write_bytes(placements)
        report = self.inspect_as("ULTIMA7")
        self.assertFalse(report["ready"])
        self.assertIn("missing U7CHUNKS", report["diagnostics"][0])

    def test_missing_or_corrupt_seed_cannot_fall_back_to_gamedat(self):
        (self.root / "GAMEDAT").mkdir()
        (self.root / "GAMEDAT" / "identity").write_text("ULTIMA7")
        (self.static / "initgame.dat").write_bytes(flex([b"identity".ljust(13, b"\0") + b"ULTIMA7"]))
        incomplete = self.inspect_as("ULTIMA7")
        self.assertFalse(incomplete["ready"])
        self.assertIn("npc.dat", incomplete["diagnostics"][0])
        (self.static / "initgame.dat").unlink()
        self.assertEqual(self.inspect_as("ULTIMA7")["status"], "missing")


if __name__ == "__main__":
    unittest.main()
