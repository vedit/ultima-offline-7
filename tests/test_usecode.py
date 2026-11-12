import struct
import unittest

from u7uo.usecode import Opcode, analyze_usecode, _ucxt_agreement


def record(fid, code, data=b"", externs=(), args=0, locals_count=0):
    header = struct.pack("<H", len(data)) + data + struct.pack("<HHH", args, locals_count, len(externs))
    body = header + b"".join(struct.pack("<H", f) for f in externs) + code
    return struct.pack("<HH", fid, len(body)) + body


SPECS = {
    0x05: Opcode("jne", ("offset",), 1, 0), 0x06: Opcode("jmp", ("offset",), 0, 0),
    0x13: Opcode("true", (), 0, 1), 0x1D: Opcode("string", ("dataoffset",), 0, 1),
    0x21: Opcode("push", ("varoffset",), 0, 1), 0x24: Opcode("extern", ("extoffset",), 0, 0),
    0x25: Opcode("ret", (), 0, 0), 0x38: Opcode("callis", ("short", "byte"), 254, 1),
    0x39: Opcode("calli", ("short", "byte"), 254, 0), 0x47: Opcode("calle", ("short",), 1, 0),
}


class UsecodeTests(unittest.TestCase):
    def test_different_dispatch_namespaces_recursive_closure_and_dead_site(self):
        a = record(7, b"\x24\0\0\x39\x08\0\0\x06\x03\0\x47\x63\0\x25", externs=[8])
        b = record(8, b"\x24\0\0\x38\x02\0\x03\x25", externs=[7])
        result, ir = analyze_usecode(a+b, SPECS, {8: "named", 2: "delayed"}, {"Test": 7})
        root = result["callgraph"]["Test"]
        self.assertEqual(root["functions"], [7, 8])
        self.assertEqual(root["script_call_sites"], 2)
        self.assertEqual(root["intrinsic_ids"], [2, 8])
        self.assertEqual(result["script_call_sites"], 3)
        self.assertEqual(result["diagnostics"][0]["reason"], "absent_function")
        self.assertFalse(result["diagnostics"][0]["entry_reachable"])
        self.assertEqual(result["action_dispatch"]["site_counts"], {"delayed": 1})
        self.assertEqual(result["execution"], "not_run")
        self.assertIsNone(result["observed_runtime_invocations"])
        self.assertEqual(ir["functions"][1]["instructions"][1][3:5], [3, 1])

    def test_string_offset_provenance_preserves_duplicate_values_at_different_addresses(self):
        result, ir = analyze_usecode(record(1, b"\x1d\0\0\x1d\x02\0\x25", b"a\0a\0"),
                                     SPECS, {}, {"Test": 1})
        strings = ir["functions"][0]["strings_referenced"]
        self.assertEqual(strings[0]["sha256"], strings[2]["sha256"])
        self.assertEqual(strings[2]["offset"] - strings[0]["offset"], 2)
        self.assertEqual(result["instructions"], 3)

    def test_rejects_malformed_corpus(self):
        for code, reason in [(b"\xff", "unsupported"), (b"\x05\0", "truncated"),
                             (b"\x24\0\0\x25", "extern index"), (b"\x21\0\0\x25", "invalid local"),
                             (b"\x06\xff\xff\x25", "branch target"),
                             (b"\x1d\0\0\x25", "unterminated"), (b"\x13", "fallthrough")]:
            with self.subTest(code=code), self.assertRaisesRegex(ValueError, reason):
                analyze_usecode(record(1, code), SPECS, {}, {"x": 1})

    def test_oracle_bytes_checked_even_when_instruction_count_agrees(self):
        raw = record(5, b"\x13\x25")
        _, ir = analyze_usecode(raw, SPECS, {}, {"test": 5})
        text = b"\t.funcnumber  0005H\n0000: 13\t\tpush true\n0001: 25\t\tret\n"
        self.assertEqual(_ucxt_agreement(text, raw, ir), 2)
        with self.assertRaisesRegex(ValueError, "disagrees"):
            _ucxt_agreement(text.replace(b"0000: 13", b"0000: 14"), raw, ir)
