import hashlib
import io
import json
import tempfile
import unittest
from contextlib import ExitStack, redirect_stdout
from pathlib import Path
from unittest.mock import patch

from u7uo.__main__ import main
from u7uo.build import active_release, build_proof, check_release, json_bytes, release_files, validate_output
from u7uo.uo import PROFILES, inspect_tools, inspect_uo


class ProofTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)

    def test_base_map_precedence_and_missing_assets(self):
        self.assertEqual(inspect_uo(self.root)["status"], "missing")
        for name in ("map0.mul", "MainMisc.uop", "map0LegacyMUL.uop"):
            (self.root / name).write_bytes(b"fixture")
        check = inspect_uo(self.root)
        self.assertEqual(check["base_map"], {"ClassicUO": "map0LegacyMUL.uop", "ModernUO": "map0.mul"})
        self.assertFalse(check["ready"])
        self.assertIn("tiledata.mul", check["missing"])
        self.assertTrue(any("Conflicting base map" in item for item in check["diagnostics"]))

    def test_resource_fingerprints_and_optional_tool_checks(self):
        fake = b"authored fixture"
        digest = hashlib.sha256(fake).hexdigest()
        with patch.dict(PROFILES, {"uo_files": {"client.exe": digest}}):
            (self.root / "client.exe").write_bytes(fake)
            self.assertTrue(inspect_uo(self.root)["ready"])
            (self.root / "client.exe").write_bytes(b"other")
            self.assertEqual(inspect_uo(self.root)["different"], ["client.exe"])
        self.assertEqual(inspect_tools(None)["status"], "not_run")
        self.assertEqual(inspect_tools(self.root)["status"], "failed")

    def test_manifest_tamper_and_resource_shadow(self):
        release = self.root / "fixture"
        release.mkdir()
        for file in ("map0.mul", "statics0.mul", "staidx0.mul", "terrain.json", "fixed.json", "inputs.json",
                     "function.lua", "script.json", "portrait/gumpidx.mul", "portrait/gumpart.mul", "portrait/portrait.json",
                     "container.json", "actor.json", "coverage.json"):
            target = release / file
            target.parent.mkdir(exist_ok=True)
            target.write_bytes(b"test")
        manifest = json_bytes({"kind": "trinsic-compiler-proof", "schema": 1, "files": release_files(release)})
        identifier = hashlib.sha256(manifest).hexdigest()
        (release / "manifest.json").write_bytes(manifest)
        check_release(release, identifier)
        shadow = release / "map0LegacyMUL.uop"
        shadow.write_bytes(b"shadow")
        with self.assertRaisesRegex(ValueError, "map0LegacyMUL.uop"):
            check_release(release, identifier)
        shadow.unlink()
        (release / "map0.mul").write_bytes(b"bad")
        with self.assertRaisesRegex(ValueError, "map0.mul"):
            check_release(release, identifier)

    def test_active_pointer_and_input_isolation(self):
        (self.root / "current.json").write_text('{"build_id":"../elsewhere"}')
        with self.assertRaises(ValueError):
            active_release(self.root)
        for overlap in (self.root, self.root / "data", self.root.parent):
            with self.assertRaises(ValueError):
                validate_output(overlap, (self.root,))

    def test_campaign_build_cannot_pass_as_a_proof(self):
        output = self.root / "unchanged"
        with redirect_stdout(io.StringIO()) as captured:
            code = main(["build", "--out", str(output), "--uo", str(self.root), "--u7", str(self.root)])
        self.assertEqual(code, 1)
        self.assertFalse(output.exists())
        self.assertIn("Full campaign", json.loads(captured.getvalue())["diagnostic"])

    def test_failed_qualification_keeps_previous_published_build(self):
        # Exercise publication with tiny authored products; each compiler and the
        # actual engine readback also have independent format and execution tests.
        out = self.root / "campaign"
        installation = self.root / "tools"
        inputs = {"u7": {"ready": True, "matched_profile": "fixture", "status": "expanded", "usecode": {"count": 1}},
                  "uo": {"ready": True}, "tool_lock": {"status": "passed"}}

        def terrain(u7, uo, destination):
            destination.mkdir()
            for name in ("terrain.json", "fixed.json", "map0.mul", "statics0.mul", "staidx0.mul"):
                (destination / name).write_bytes(b"fixture")
            return {"cell_count": 64, "blocks": 1, "distinct_source_shape_frames": 1, "fixed": {}}

        def emitter(files, result):
            def generate(u7, destination):
                destination.mkdir(exist_ok=True)
                for name in files:
                    (destination / name).write_bytes(b"fixture")
                return result
            return generate

        with ExitStack() as stack:
            stack.enter_context(patch("u7uo.build.inspect_inputs", return_value=inputs))
            stack.enter_context(patch("u7uo.terrain.produce_terrain", side_effect=terrain))
            products = (
                ("lua.produce_lua", ("script.json", "function.lua"), {"instruction_count": 1}),
                ("containers.produce_container", ("container.json",), {"objects": [], "scanned_objects": 0}),
                ("actor.produce_actor", ("actor.json",), {"npc_slot": 1, "face": 1, "function_id": 42, "table": {"records_indexed": 1}}),
                ("portrait.produce_portrait", ("portrait.json", "gumpart.mul", "gumpidx.mul"),
                 {"gump_id": 1, "shape": 1, "binding": {"function": 42, "npc_ref": -1}}),
            )
            for name, files, result in products:
                stack.enter_context(patch("u7uo." + name, side_effect=emitter(files, result)))
            check = stack.enter_context(patch("u7uo.build.run_checks", return_value={}))
            args = self.root / "u7", self.root / "uo", out, installation
            first = build_proof(*args)
            repeat = build_proof(*args)
            self.assertEqual(first["build_id"], repeat["build_id"])
            pointer = (out / "current.json").read_bytes()
            check.side_effect = ValueError("injected loader failure")
            with self.assertRaisesRegex(ValueError, "injected loader failure"):
                build_proof(*args)
            self.assertEqual((out / "current.json").read_bytes(), pointer)
            self.assertEqual(active_release(out)[0], first["build_id"])
            self.assertFalse(list(out.glob(".stage-*")))


if __name__ == "__main__":
    unittest.main()
