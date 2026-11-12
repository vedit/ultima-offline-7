import json
import os
import shutil
import struct
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from u7uo.lua import PROOF_FUNCTION, produce_lua, translate, verify_lua


# Original synthetic procedure: compare in the opposite operand order and
# store a non-Boolean nonzero integer to exercise the host flag conversion.
def sample_code(event=3):
    return (b"\x1f" + struct.pack("<h", event) + b"\x48\x22\x05\x06\x00"
            + b"\x1f\xdb\xff\x43\x3c\x00\x25")


def source_for(code, install):
    static = install / "static"
    static.mkdir(exist_ok=True)
    body = struct.pack("<HHHH", 0, 1, 0, 0) + code
    (static / "usecode").write_bytes(struct.pack("<HH", PROOF_FUNCTION, len(body)) + body)


class LuaTests(unittest.TestCase):
    def test_source_offsets_signed_values_and_codegen(self):
        generated, source = translate(sample_code(), 123)
        self.assertEqual([row["source_offset"] for row in source], [123, 126, 127, 128, 131, 134, 137])
        self.assertIn("s1 = -37", generated)
        self.assertIn("if s1 == 0 then goto pc_14 end", generated)
        self.assertEqual(source[-1]["stack_before"], 0)

    def test_unsupported_instructions_invalid_operands_and_stack_fail_closed(self):
        for code, diagnostic in [
            (b"\xae\x25", "unsupported opcode"),
            (b"\x1f\0", "truncated"),
            (b"\x13\x43\0\x80\x25", "host range"),
            (b"\x14\x05\x01\x00\x1f\0\0\x25", "non-instruction"),
            (b"\x22\x25", "underflow"),
            (b"\x13\x25", "nonempty stack"),
            (b"\x06\xfd\xff", "backward branch"),
            (b"\x13\x05\x01\x00\x13\x25", "inconsistent stack depth"),
            (b"\x25\x25", "unreachable"),
        ]:
            with self.subTest(code=code), self.assertRaisesRegex(ValueError, diagnostic):
                translate(code)

    def test_metadata_and_lua_mutation_rejected_before_execution(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            source_for(sample_code(), out)
            metadata = produce_lua(out, out)
            metadata["source_map"].pop()
            (out / "script.json").write_text(json.dumps(metadata))
            with self.assertRaisesRegex(ValueError, "differs from recompilation"):
                verify_lua(out, out / "absent")
            produce_lua(out, out)
            (out / "function.lua").write_text("return os.execute")
            with self.assertRaisesRegex(ValueError, "differs from recompilation"):
                verify_lua(out, out / "absent")
            produce_lua(out, out)
            (out / "inputs.json").write_text(json.dumps({"u7": {"usecode": {"sha256": "0" * 64, "records": []}}}))
            with self.assertRaisesRegex(ValueError, "frozen Usecode inventory"):
                verify_lua(out, out / "absent")

    def test_execution_with_lua_54(self):
        lua = os.environ.get("U7UO_LUA") or shutil.which("lua5.4")
        if not lua:
            self.skipTest("Set U7UO_LUA to a Lua 5.4 executable for execution coverage")
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            source_for(sample_code(), out)
            produce_lua(out, out)
            with patch.dict(os.environ, {"LUA_INIT_5_4": "error('ambient startup script executed')"}):
                result = verify_lua(out, Path(lua))
            self.assertEqual(result["scenarios_passed"], 3)
            self.assertEqual(result["dos_runtime_comparison"], "not_run")
            source_for(sample_code(event=2), out)
            produce_lua(out, out)
            with self.assertRaisesRegex(ValueError, "unexpected flag value"):
                verify_lua(out, Path(lua))


if __name__ == "__main__":
    unittest.main()
