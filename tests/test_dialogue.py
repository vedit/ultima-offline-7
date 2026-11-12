import hashlib
import json
import os
from pathlib import Path
import shutil
import struct
import tempfile
import unittest

from u7uo.dialogue import _execute, _extract, _source_pages, compile_dialogue
from u7uo.campaign_usecode import bind_world_functions, compile_corpus, produce_corpus, verify_corpus
from u7uo.usecode import Opcode, analyze_usecode


SPECS = {
    0x04: ("offset",), 0x05: ("offset",), 0x06: ("offset",), 0x07: ("short","offset"),
    0x1C: ("dataoffset",), 0x1D: ("dataoffset",), 0x1E: ("short",),
    0x24: ("extoffset",), 0x25: (), 0x31: ("short","offset"), 0x33: (),
    0x38: ("short","byte"), 0x39: ("short","byte"), 0x3F: (), 0x42: ("flag",),
}
SCHEMA={k:Opcode(str(k),v,0,0) for k,v in SPECS.items()}


def record(fid,code,data=b"",links=()):
    body=(struct.pack("<H",len(data))+data+struct.pack("<HHH",int(fid<0x800),0,len(links))
          +b"".join(struct.pack("<H",v) for v in links)+code)
    return struct.pack("<HH",fid,len(body))+body


def corpus():
    # Data-free test text includes a delimiter and quotes to exercise Lua literal escaping.
    data=b'a~*b\0one\0two]=]"\0'
    conversation=(bytes([0x1C,0,0,0x33,0x1D,5,0,0x1D,9,0,0x1E,2,0,0x39,5,0,1,
                         0x04,11,0,0x1D,5,0,0x07,1,0,1,0,0x3F,0x25,0x25,0x25]))
    root=record(0x40C, bytes([0x42,7,0,0x05,3,0,0x24,0,0,0x25]), links=[0x900])
    return root+record(0x900,conversation,data)


def program(raw):
    _,ir=analyze_usecode(raw,SCHEMA,{},{"test":0x40C})
    return _extract(raw,ir,{0x40C})


class DialogueTests(unittest.TestCase):
    def run_lua(self,lua,cases):
        exe=os.environ.get("U7UO_LUA") or shutil.which("lua5.4")
        if not exe:
            self.skipTest("Set U7UO_LUA to run the Lua 5.4 dialogue cases")
        self.assertEqual(_execute(lua,cases,Path(exe)),["ok"])

    def test_source_closed_functions_and_markers(self):
        p=program(corpus())
        self.assertEqual([f["id"] for f in p["functions"]],[0x40C,0x900])
        self.assertEqual(p["source_sha256"],hashlib.sha256(corpus()).hexdigest())
        self.assertEqual(list(_source_pages("*A~~B~*C")),["","A","B","","C"])
        self.assertEqual(list(_source_pages("")),[])
        _,d=compile_dialogue(p)
        self.assertEqual(d,[])

    def test_pause_resume_choice_order_call_stack_and_independent_sessions(self):
        p=program(corpus())
        lua,_=compile_dialogue(p)
        cases="""
local s=mod.start(0x40C,1,-12)
local other=mod.start(0x40C,1,-12)
local e=s:resume()
assert(e.kind=="flag_read" and e.args[1]==7 and e.pc==0 and e.sequence==1)
assert(not pcall(function() s:resume(2) end))
assert(other:resume().kind=="flag_read" and other:resume(0).status=="completed")
e=s:resume(1)
for _,page in ipairs({"a","","b"}) do
  assert(e.status=="effect" and e.kind=="say" and e.args[1]==page)
  assert(#e.call_stack==2 and e.call_stack[1].function_id==0x40C and e.call_stack[1].pc==6)
  assert(e.call_stack[2].function_id==0x900 and e.call_stack[2].pc==3)
  assert(e.source_offset==BASE+3)
  e=s:resume()
end
assert(e.kind=="choice" and e.args[2]=="one" and e.args[1]==[[two]=]"]])
e.args[1]="invalid"
assert(not pcall(function() s:resume("invalid") end))
local done=s:resume("one")
assert(done.status=="completed" and done.termination=="abort" and done.pc==28)
assert(s:resume().termination=="abort")
print("ok")
"""
        self.run_lua(lua,cases.replace("BASE",str(p["functions"][1]["base"])))

    def test_campaign_module_compiles_disconnected_roots_and_checks_actual_effects(self):
        exe = os.environ.get("U7UO_LUA") or shutil.which("lua5.4")
        if not exe:
            self.skipTest("Set U7UO_LUA to run the full corpus fixture")
        raw = corpus()+record(0x411,bytes([0x38,0x23,0,0,0x25]))
        _,ir = analyze_usecode(raw,SCHEMA,{},{"test":0x40C})
        with self.assertRaisesRegex(ValueError,"every original function"):
            compile_corpus(raw,{**ir,"functions":[f for f in ir["functions"] if f["id"]!=0x411]})
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            (d/"STATIC").mkdir()
            (d/"STATIC/USECODE").write_bytes(raw)
            (d/"usecode-ir.json").write_text(json.dumps(ir))
            info = produce_corpus(d,d)
            self.assertEqual(set(info["functions"]),{str(n) for n in (0x40C,0x411,0x900)})
            report = verify_corpus(d,exe)
            self.assertEqual(report["function_ids_observed"],[0x40C,0x411])
            self.assertEqual(report["campaign_gameplay"],"not_run")
            subset = program(raw)
            (d/"dialogue.json").write_text(json.dumps({"program":subset}))
            world = d/"world"
            world.mkdir()
            bind_world_functions(d,world)
            linked = (world/"dialogue.lua").read_bytes()
            self.assertEqual(info["generator_version"],4)
            self.assertEqual(linked,compile_dialogue(subset,4)[0].encode())
            binding = json.loads((world/"dialogue.json").read_bytes())["campaign_binding"]
            self.assertEqual((binding["available_functions"],binding["bound_functions"]),(3,2))
            self.assertEqual(binding["registered_roots"],[0x40C])
            with (d/"campaign-usecode.lua").open("ab") as out:
                out.write(b"--different")
            with self.assertRaisesRegex(ValueError,"differs from source"):
                verify_corpus(d,exe)
            with self.assertRaisesRegex(ValueError,"different inputs"):
                bind_world_functions(d,world)

    def test_campaign_arithmetic_default_and_explicit_item_call(self):
        schema = dict(SCHEMA)
        for op,operands in [(0x0B,()),(0x0D,()),(0x3E,()),(0x2D,()),(0x1F,("short",)),
                            (0x21,("varoffset",)),(0x47,("short",))]:
            schema[op] = Opcode(str(op),operands,0,0)
        def literal(n):
            return bytes([0x1F])+struct.pack("<h",n)
        # Explicitly bind local 0 and the item of a second object function.
        root = literal(123) + bytes([0x47,1,4,0x3E,0x39,0x50,0,2])
        child = bytes([0x21,0,0,0x3E,0x39,0x51,0,2])+literal(42)+bytes([0x2D])
        ops = [(a,b,op) for a,b in [(-7,3),(7,-3),(-7,-3),(7,0)] for op in (0x0B,0x0D)]
        for a,b,op in ops:
            root += literal(a)+literal(b)+bytes([op,0x39,0x52,0,1])
        # Take the first default, then skip the second one after a match.
        root += bytes([0x31,0,0,3,0])+literal(5)+bytes([0x31,0,0,3,0])+literal(6)+bytes([0x39,0x53,0,1,0x25])
        raw = record(0x40C,root)+record(0x401,child)
        _,ir = analyze_usecode(raw,schema,{},{"test":0x40C})
        p = _extract(raw,ir,{0x40C})
        lua,issues = compile_dialogue(p,3)
        self.assertEqual(issues,[])
        self.run_lua(lua,"""local s=mod.start(0x40C,1,-12)
local e=s:resume()
assert(e.function_id==0x401 and e.intrinsic==0x51 and e.args[1]==123 and e.args[2]==123)
e=s:resume()
assert(e.function_id==0x40C and e.intrinsic==0x50 and e.args[1]==-12 and e.args[2]==42)
for _,v in ipairs({-2,-1,-2,1,2,-1,32767,32767}) do
  e=s:resume(); assert(e.intrinsic==0x52 and e.args[1]==v)
end
e=s:resume(); assert(e.intrinsic==0x53 and e.args[1]==5)
assert(s:resume().status=="completed")
print("ok")""")

    def test_campaign_word_overflow_and_array_heads(self):
        schema = {**SCHEMA, **{op:Opcode(str(op), (), 0, 0) for op in (9, 10, 12)},
                  0x1F:Opcode("integer", ("short",), 0, 0)}
        def word(n):
            return bytes([0x1F])+struct.pack("<h", n)
        def observe(op):
            return bytes([op, 0x39, 0x52, 0, 1])
        code = (word(32767)+word(1)+observe(9) + word(-32768)+word(1)+observe(10)
                + word(90)+word(-32768)+bytes([0x1E,2,0])+word(-1)+observe(12) + bytes([0x25]))
        raw = record(0x40C, code)
        _, ir = analyze_usecode(raw, schema, {}, {"fixture":0x40C})
        lua, info = compile_corpus(raw, ir)
        self.assertEqual(info["unsupported_instruction_sites"], 0)
        self.run_lua(lua, """local s=mod.start(0x40C,1,-12)
for _,expected in ipairs({-32768,32767,-32768}) do
  local e=s:resume()
  assert(e.kind=="intrinsic" and e.intrinsic==0x52 and e.args[1]==expected)
end
assert(s:resume().status=="completed")
print("ok")""")

    def test_unsupported_instruction_and_unresolved_host_query_expose_source_offset(self):
        code=bytes([0x38,0x90,0,0,0x31,0,0,0,0,0x25])
        p=program(record(0x40C,code))
        lua,issues=compile_dialogue(p)
        self.assertEqual(len(issues),1)
        self.assertEqual(issues[0]["pc"],4)
        self.run_lua(lua,"""local s=mod.start(0x40C,1,-12)
local e=s:resume()
assert(e.status=="effect" and e.intrinsic==0x90 and e.expects_value and e.pc==0)
assert(not pcall(function() s:resume() end))
local blocked=s:resume(0)
assert(blocked.status=="blocked" and blocked.function_id==0x40C and blocked.pc==4)
assert(blocked.source_offset==e.source_offset+4 and blocked.reason:find("unsupported opcode"))
print("ok")""")

    def test_source_string_metadata_mismatch_rejected(self):
        raw=corpus()
        _,ir=analyze_usecode(raw,SCHEMA,{},{"test":0x40C})
        ir["functions"][1]["strings_referenced"][5]["sha256"]="0"*64
        with self.assertRaisesRegex(ValueError,"string differs"):
            _extract(raw,ir,{0x40C})
