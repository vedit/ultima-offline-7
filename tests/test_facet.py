import struct
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from u7uo.facet import EMPTY_INDEX, SHADOW, VOID, _combined_sample, stamp_blocks, verify_facet


class FacetTest(unittest.TestCase):
    def test_global_block_order_stride_padding_and_static_offsets(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            sample, output = root / "input", root / "output"
            sample.mkdir()
            output.mkdir()
            block = lambda n: bytes(4) + struct.pack("<Hb", n, -5) * 64
            (sample / "map0.mul").write_bytes(block(300) + block(301))
            (sample / "staidx0.mul").write_bytes(EMPTY_INDEX + struct.pack("<III", 0, 7, 0))
            (sample / "statics0.mul").write_bytes(struct.pack("<HBBbH", 112, 3, 5, 9, 3))
            stamp_blocks(sample, output, {"width":16,"height":8,"source_origin":[8,8]}, width=32, height=24)
            data = (output / "map0.mul").read_bytes()
            self.assertEqual(len(data), 12 * 196)
            for index in range(12):
                expected = {4:(300,-5),7:(301,-5)}.get(index,(VOID,0))
                self.assertEqual(struct.unpack_from("<Hb", data, 196 * index + 4), expected)
            self.assertEqual(struct.unpack_from("<III",(output / "staidx0.mul").read_bytes(),7*12),(0,7,0))
            self.assertEqual((output / "statics0.mul").read_bytes(), (sample / "statics0.mul").read_bytes())

    def test_precedence_and_source_offsets(self):
        for leaf in ("Map0LegacyMUL.UOP","map0xLegacyMUL.uop","staidx0x.mul","mapdifl0.mul","stadifi0.mul","verdata.mul"):
            self.assertIsNotNone(SHADOW.fullmatch(leaf))
        for leaf in ("MainMisc.uop", "tiledata.mul", "map1LegacyMUL.uop", "gumpartLegacyMUL.uop"):
            self.assertIsNone(SHADOW.fullmatch(leaf))
        base = {"source_origin":[8,16],"cells":[{"x":0,"y":1}]}
        extra = {"source_origin":[40,8],"cells":[{"x":2,"y":4}]}
        self.assertEqual(_combined_sample(base,extra)["cells"], [{"x":0,"y":1},{"x":34,"y":-4}])


class ActiveFacetVerification(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.out = self.root / "Builds/Test"
        self.out.mkdir(parents=True)
        self.pointer = self.out / "current.json"
        self.pointer.write_text(json.dumps({"build_id":"a"*64}))
        self.report = {"build_id":"a"*64, "inputs":{"dialogue":None}, "slot":0, "start":[1,2,0]}
        self.release = self.out / "releases" / ("a"*64)
        active = patch("u7uo.facet._active", return_value=(self.release,self.report))
        active.start()
        self.addCleanup(active.stop)

    def test_structural_only_and_legacy_do_not_launch_player(self):
        with patch("tools.facet.session.run") as run, patch("u7uo.facet.probe_facet") as probe:
            self.report["inputs"]["dialogue"] = True
            self.assertEqual(verify_facet(self.root,self.out,structural_only=True)["player_replay"],"not_run")
            probe.assert_not_called()
            self.report["inputs"]["dialogue"] = None
            probe.return_value = {"build_id":self.report["build_id"], "server_boot":"passed"}
            self.assertEqual(verify_facet(self.root,self.out)["server_boot"],"passed")
            run.assert_not_called()

    def test_pointer_replaced_with_identical_contents_during_probe(self):
        def republish(*args):
            alternate = self.out / "republish"
            alternate.write_bytes(self.pointer.read_bytes())
            alternate.replace(self.pointer)
            return {"build_id":self.report["build_id"]}
        with patch("u7uo.facet.probe_facet", side_effect=republish):
            with self.assertRaisesRegex(ValueError,"selection changed"):
                verify_facet(self.root,self.out)

    def test_player_replay_must_match_selected_release(self):
        self.report["inputs"]["dialogue"] = True
        with patch("u7uo.facet._readback",return_value={"status":"passed"}), \
                patch("tools.facet.session.run",return_value={"status":"passed","build_id":"b"*64}):
            with self.assertRaisesRegex(ValueError,"selected private facet"):
                verify_facet(self.root,self.out)

    def test_opening_reports_its_own_runtime_failure_with_evidence(self):
        self.report["inputs"].update(dialogue=True, opening_egg=True)
        log = self.root/"runtime.log"
        log.write_text("Loading regions done (0 regions)\nListening 127.0.0.1:2222\nShutting down\n")
        observed = {"checks":{"source_steps":True,"completed":False},
                    "diagnostic":"source function 0x0401 paused","saved_opening":{"Error":"paused"}}
        replay = {"status":"incomplete","build_id":self.report["build_id"],"scratch":str(self.root),
                  "port":2222,"log":str(log),"opening":observed}
        with patch("u7uo.facet._readback",return_value={"status":"passed"}), \
                patch("tools.facet.session.run",return_value=replay) as run:
            receipt = verify_facet(self.root,self.out)
        run.assert_called_once_with(self.root,self.out,False,opening=True)
        self.assertEqual(receipt["status"],"failed")
        self.assertEqual(receipt["player_replay"]["opening"],observed)

    def test_explicit_journey_retains_partial_evidence_and_structural_only_never_runs_it(self):
        self.report["inputs"].update(dialogue=True,opening_egg=True)
        log=self.root/"journey.log"
        log.write_text("Loading regions done (0 regions)\nListening 127.0.0.1:1234\nShutting down")
        observed={"checks":{"automatic_mayor":True,"legitimate_gate_journey":False},
                  "journey":{"current":"interview Gilberto"},"diagnostic":"witness not reached","saved_opening":{"Error":None}}
        replay={"status":"incomplete","build_id":self.report["build_id"],"scratch":str(self.root),
                "port":1234,"log":str(log),"opening":observed}
        with patch("u7uo.facet._readback",return_value={"status":"passed"}), patch("tools.facet.session.run",return_value=replay) as run:
            structural=verify_facet(self.root,self.out,scenario="journey",structural_only=True)
            self.assertEqual(structural["player_replay"],"not_run")
            run.assert_not_called()
            checked=verify_facet(self.root,self.out,scenario="journey")
        run.assert_called_once_with(self.root,self.out,False,journey=True)
        self.assertEqual(checked["status"],"failed")
        self.assertEqual(checked["player_replay"]["opening"]["journey"]["current"],"interview Gilberto")

    def test_estate_cannot_silently_run_on_an_opening_only_profile(self):
        self.report["inputs"].update(dialogue=True,opening_egg=True)
        with patch("tools.facet.session.run") as run:
            with self.assertRaisesRegex(ValueError,"direct-start"):
                verify_facet(self.root,self.out,scenario="estate")
            run.assert_not_called()
