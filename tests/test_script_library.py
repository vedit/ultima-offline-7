import json
import os
import shutil
import struct
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from u7uo.script_library import _run_cases, compile_library, produce_script_library, verify_script_library
from u7uo.usecode import Opcode, analyze_usecode
from u7uo.u7 import STEAM_FORGE_USECODE


TYPES = {6: ("offset",), 0x12: ("varoffset",), 0x1E: ("short",), 0x21: ("varoffset",),
         0x24: ("extoffset",), 0x39: ("short", "byte"), 0x43: ("flag",), 0x44: ("byte",),
         0x46: ("varoffset",)}


def record(fid, code, argc=0, locals_count=0, externs=()):
    header = struct.pack("<HHHH", 0, argc, locals_count, len(externs))
    body = header + b"".join(struct.pack("<H", target) for target in externs) + code
    return struct.pack("<HH", fid, len(body)) + body


def parse(*functions):
    schema = {op: Opcode(str(op), TYPES.get(op, ()), 0, 0) for op in
              {*TYPES, 0x09, 0x0B, 0x0D, 0x13, 0x25, 0x2D, 0x48, 0x4B}}
    return analyze_usecode(b"".join(functions), schema, {}, {})[1]


def interpreter(case):
    path = os.environ.get("U7UO_LUA") or shutil.which("lua5.4")
    if not path:
        case.skipTest("Set U7UO_LUA for the Lua 5.4 runtime checks")
    return Path(path)


class LibraryTests(unittest.TestCase):
    def test_dependency_closure_and_source_diagnostics(self):
        root = record(0x900, b"\x24\x00\x00\x25", externs=[0x901])
        mid = record(0x901, b"\x24\x00\x00\x25", externs=[0x902])
        host = record(0x902, b"\x39\x40\x00\x01\x25")
        dead = record(0x903, b"\x06\x04\x00\x39\x0c\x00\x00\x25")
        ir = parse(root, mid, host, dead)
        lua, meta = compile_library(ir)
        self.assertEqual(meta["function_ids"], [0x903])
        self.assertEqual(meta["instructions_emitted"], 2)
        self.assertEqual(meta["diagnostics"][str(0x900)][0]["target"], 0x901)
        self.assertEqual(meta["diagnostics"][str(0x901)][0]["reason"], "uncompiled_callee")
        detail = meta["diagnostics"][str(0x902)][0]
        self.assertEqual((detail["pc"],detail["operands"],detail["source_offset"]),
                         (0,[0x40,1],ir["functions"][2]["code_offset"]))
        self.assertNotIn("F[2304] =", lua)

    def test_arithmetic_against_truncating_reference(self):
        ir = parse(*(record(0x900+i, bytes([0x21,0,0,0x21,1,0,op,0x2D]), argc=2)
                     for i,op in enumerate([0x0B,0x0D])))
        lua, _ = compile_library(ir)
        vectors = []
        for a in [-99,-1,0,31]:
            for b in [-13,-1,2,17]:
                quotient = abs(a) // abs(b) * (1 if a*b >= 0 else -1)
                for function, value in [(0x900,quotient),(0x901,a-quotient*b)]:
                    vectors.append(f"assert(invoke({function},{{{a},{b}}},0,{{}}) == {value})")
        _run_cases(lua, "\n".join(vectors), interpreter(self))

    def test_frame_local_events_array_copy_implicit_object_argument_and_zero_padding(self):
        child = record(0x400, bytes([0x44,20,0x4B,0x21,0,0,0x48,0x09,0x2D]), argc=2)
        caller = record(0x900, bytes([0x44,7,0x24,0,0,0x48,0x09,0x2D]), externs=[0x400])
        # Construct an array from two stack entries, flattening a caller-provided array.
        # Change an extended slot in the constructed array, leaving the argument intact.
        array = record(0x901, bytes([0x21,0,0,0x44,5,0x1E,2,0,0x12,1,0,
                                     0x44,8,0x44,5,0x46,1,0,0x21,1,0,0x2D]), argc=1, locals_count=1)
        padding = record(0x902, bytes([0x21,1,0,0x2D]), argc=2)
        direct = record(0x903, bytes([0x44,9,0x24,0,0,0x2D]), externs=[0x902])
        lua, _ = compile_library(parse(child, caller, array, padding, direct))
        cases = """local value,t = invoke(0x900,{},3,{})
assert(value == 30 and #t == 2 and t[2] == 0x400)
local a = {11,12}
local r = invoke(0x901,{a},0,{})
assert(#r == 5 and r[1] == 5 and r[2] == 11 and r[3] == 12 and r[4] == 0 and r[5] == 8)
assert(#a == 2 and a[1] == 11 and a[2] == 12)
assert(invoke(0x903,{},0,{}) == 0)
"""
        with patch.dict(os.environ, {"LUA_INIT_5_4": "error('ambient profile loaded')"}):
            _run_cases(lua, cases, interpreter(self))

    def test_runtime_guard_preserves_caller_flags_and_identifies_source_pc(self):
        broken = record(0x900, bytes([0x13,0x43,5,0,0x44,5,0x44,0,0x0B,0x2D]))
        lua, _ = compile_library(parse(broken))
        cases = """local flags = {[17]=1}
local ok,msg = pcall(invoke,0x900,{},0,flags)
assert(not ok and msg:find("function 2304 pc 8:") and msg:find("division by zero"))
assert(flags[5] == nil and flags[17] == 1)
"""
        _run_cases(lua, cases, interpreter(self))

    def test_verify_requires_pinned_source_and_rejects_lua_edits(self):
        ir = parse(record(0x901,b"\x25"))
        ir["sha256"] = STEAM_FORGE_USECODE
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            (directory / "usecode-ir.json").write_text(json.dumps(ir))
            produce_script_library(directory)
            with self.assertRaisesRegex(ValueError, "differ from the pinned source"):
                verify_script_library(directory, directory / "absent")
            (directory / "script-library.lua").write_text("return os.execute")
            with self.assertRaisesRegex(ValueError, "differs from recompilation"):
                verify_script_library(directory, directory / "absent")
