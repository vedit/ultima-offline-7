"""Run the same authored arithmetic instructions in DOS Black Gate and generated Lua."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import struct
import subprocess
import tempfile

from u7uo.build import active_release
from u7uo.dialogue import _execute, _extract, compile_dialogue
from u7uo.u7 import STEAM_FORGE_USECODE, usecode_inventory
from u7uo.usecode import analyze_usecode, load_tables


# Each case compares the actual numeric result to a signed Usecode immediate.
# The two false controls distinguish a working comparison from a stuck true flag.
CASES = (
    ("add positive overflow", 9, 32767, 1, -32768),
    ("add negative overflow", 9, -32768, -1, 32767),
    ("subtract negative overflow", 10, -32768, 1, 32767),
    ("subtract positive overflow", 10, 32767, -1, -32768),
    ("multiply low word zero", 12, 256, 256, 0),
    ("multiply low word signed", 12, 300, 300, 24464),
    ("multiply signed overflow", 12, -32768, -1, -32768),
    ("divide negative left", 11, -7, 3, -2),
    ("divide negative right", 11, 7, -3, -2),
    ("remainder negative left", 13, -7, 3, -1),
    ("remainder negative right", 13, 7, -3, 1),
    ("divide by zero", 11, 7, 0, 32767),
    ("remainder by zero", 13, 7, 0, 32767),
    ("array plus scalar", 9, [5, 90], 3, 8),
    ("scalar minus array", 10, 8, [5, 90], 3),
    ("array times array", 12, [3, 90], [5, 70], 15),
    ("array quotient", 11, [-7, 90], [3, 70], -2),
    ("array remainder", 13, [7, 90], [-3, 70], 1),
    ("original 0932 minimum signed argument", 0x24, -32768, None, -32768),
    ("original 0932 ordinary negative argument", 0x24, -145, None, 145),
    ("original 0932 positive argument", 0x24, 145, None, 145),
    ("false arithmetic control", 9, 8, 3, 10),
    ("false operand-order control", 10, 8, 3, -5),
)
START_FLAG = 640
PREFIX = bytes.fromhex("d52bc184a63e")
SUFFIX = bytes.fromhex("b3185ed2649c")


def fixture(raw):
    if hashlib.sha256(raw).hexdigest() != STEAM_FORGE_USECODE:
        raise ValueError("The numeric oracle requires the pinned Forge Usecode")
    record, = (r for r in usecode_inventory(raw)["records"] if r["id"] == 0x401)
    code = bytearray()
    def emit(op, arg=None):
        code.append(op)
        if arg is not None:
            code.extend(struct.pack("<h" if op == 0x1f else "<H", arg))

    def marker(first, data):
        for i in range(8*len(data)):
            emit(0x13 if data[i//8] & (128 >> (i%8)) else 0x14)
            emit(0x43, first+i)

    def operand(value):
        if isinstance(value, list):
            for item in reversed(value):
                emit(0x1f, item)
            emit(0x1e, len(value))
        else:
            emit(0x1f, value)

    marker(START_FLAG, PREFIX)
    result_start = START_FLAG + 8*len(PREFIX)
    for i, (_, op, left, right, expected) in enumerate(CASES):
        operand(left)
        if op == 0x24:
            emit(0x24, 0)  # External link zero is the original Forge function 0932.
        else:
            operand(right)
            emit(op)
        emit(0x1f, expected)
        emit(0x22)
        emit(0x43, result_start+i)
    end_flag = result_start + ((len(CASES)+7)//8)*8
    marker(end_flag, SUFFIX)
    emit(0x25)
    if len(code) > record["code_length"] or end_flag+8*len(SUFFIX) > 837:
        raise ValueError("The diagnostic exceeds the original function or flag table")
    # Keep all other records and file offsets untouched. Each unused trailing
    # byte is a return, so the normal corpus decoder can also read this input.
    code.extend(bytes([0x25]) * (record["code_length"]-len(code)))
    return {"base": record["code_offset"], "code_hex": code.hex(), "source_sha256": STEAM_FORGE_USECODE,
            "extern_offset": record["code_offset"]-2*record["extern_count"], "extern_target": 0x932,
            "prefix": PREFIX.hex(), "suffix": SUFFIX.hex(), "count": len(CASES)}


def function_span(module, function_id):
    match = re.search(rf"(?m)^arity\[{function_id}\]=\d+\n", module)
    if match is None:
        raise ValueError(f"Missing compiled diagnostic function {function_id:04X}")
    next_header = re.search(r"(?m)^(?:arity\[|return \{start=start\})", module[match.end():])
    if next_header is None:
        raise ValueError("Incomplete Lua function table")
    return match.start(), match.end()+next_header.start()


def compare(root, session, campaign=None):
    src = root/"Assets/UltimaVII-Steam/STATIC/USECODE"
    raw = src.read_bytes()
    spec = fixture(raw)
    native = json.loads((session/"receipt.json").read_bytes())
    private = bytearray(raw)
    code = bytes.fromhex(spec["code_hex"])
    private[spec["base"]:spec["base"]+len(code)] = code
    struct.pack_into("<H", private, spec["extern_offset"], spec["extern_target"])
    # Read the two original link tables independently of the capture tool.
    table = (src.parent/"LINKDEP1").read_bytes()
    dependencies = bytearray((src.parent/"LINKDEP2").read_bytes())
    start, _, end = struct.unpack_from("<HHH", table, 4*0x401)
    original, = (r for r in usecode_inventory(raw)["records"] if r["id"] == 0x932)
    callee_start, _, callee_end = struct.unpack_from("<HHH", table, 4*0x932)
    offsets = [struct.unpack_from("<I", dependencies, i*4)[0] for i in range(callee_start, callee_end)]
    target, = (off for off in offsets if struct.unpack_from("<H", raw, off)[0] == 0x932)
    previous = struct.unpack_from("<I", dependencies, (end-1)*4)[0]
    if (start >= end or struct.unpack_from("<H", raw, previous)[0] != 0x937 or
            struct.unpack_from("<H", raw, target+2)[0] > struct.unpack_from("<H", raw, previous+2)[0]):
        raise ValueError("Unexpected Forge Iolo dependency block")
    struct.pack_into("<I", dependencies, (end-1)*4, target)
    required = {"ULTIMA7.COM", "U7.EXE", "INTRO.EXE", "MAINMENU.EXE", "ENDGAME.EXE", "U7.CFG"}
    required.update("STATIC/"+p.name for p in src.parent.iterdir() if p.is_file())
    if set(native["inputs"]) != required:
        raise ValueError("DOS diagnostic input inventory differs from the installed game")
    for field, file in (("wasm_sha256", root/"Tools/js-dos-8.5.3/package/dist/wdosbox.wasm"),
                        ("config_sha256", session/"dosbox.conf")):
        if hashlib.sha256(file.read_bytes()).hexdigest() != native[field]:
            raise ValueError(f"DOS diagnostic {field} differs")
    for name, info in native["inputs"].items():
        data = {"STATIC/USECODE":private, "STATIC/LINKDEP2":dependencies}.get(name)
        if data is None:
            data = (src.parents[1]/name).read_bytes()
        if len(data) != info["bytes"] or hashlib.sha256(data).hexdigest() != info["sha256"]:
            raise ValueError(f"DOS input differs for {name}")
    if (native["numeric_fixture"] != spec or not native.get("finished") or
            native["inputs"]["STATIC/USECODE"]["sha256"] != hashlib.sha256(private).hexdigest() or
            native["inputs"]["U7.EXE"]["sha256"] != hashlib.sha256((src.parents[1]/"U7.EXE").read_bytes()).hexdigest()):
        raise ValueError("Original executable or instrumented script provenance differs")
    obs = native["numeric_result"]
    memory = (session/"numeric-memory.bin").read_bytes()
    if len(memory) != 1048576 or hashlib.sha256(memory).hexdigest() != obs["memory_sha256"]:
        raise ValueError("DOS memory snapshot failed verification")
    off = memory.find(PREFIX)
    if off < 0 or off != obs["address"] or memory.find(PREFIX, off+1) != -1:
        raise ValueError("Diagnostic flag block missing or ambiguous")
    data = off + len(PREFIX)
    if memory[data+(len(CASES)+7)//8:][:len(SUFFIX)] != SUFFIX:
        raise ValueError("DOS did not finish the diagnostic")
    dos = [(memory[data+i//8] >> (7-i%8)) & 1 for i in range(len(CASES))]
    schema,names = load_tables(root/"Tools/ExultTools/data")
    _,ir = analyze_usecode(bytes(private), schema, names, {"probe":0x401})
    program = _extract(bytes(private), ir, {0x401})
    callee, = (f for f in program["functions"] if f["id"] == 0x932)
    begin = original["code_offset"]
    if hashlib.sha256(raw[begin:begin+original["code_length"]]).hexdigest() != callee["code_sha256"]:
        raise ValueError("The diagnostic must call the untouched original routine")
    lua, errors = compile_dialogue(program, 4)
    if errors:
        raise ValueError("Untranslated numeric probe instruction")
    published = None
    if campaign is not None:
        build, directory, _ = active_release(campaign)
        info = json.loads((directory/"campaign-usecode.json").read_bytes())
        full = (directory/"campaign-usecode.lua").read_bytes()
        if (info["generator_version"] != 4 or info["source_sha256"] != spec["source_sha256"]
                or hashlib.sha256(full).hexdigest() != info["lua_sha256"]):
            raise ValueError("Campaign module does not match the qualified compiler and inputs")
        module = full.decode("utf-8")
        first, end = function_span(module, 0x932)
        a, b = function_span(lua, 0x932)
        if lua[a:b] != module[first:end]:
            raise ValueError("Original callee and published campaign function differ")
        first, end = function_span(module, 0x401)
        a, b = function_span(lua, 0x401)
        lua = module[:first] + lua[a:b] + module[end:]
        published = {"build_id":build, "lua_sha256":info["lua_sha256"],
                     "diagnostic_replacement":0x401, "original_callee":0x932}
    runner = """
local state=mod.start(0x401,3,-1)
local e=state:resume()
while e.status=="effect" do
  assert(e.kind=="flag_write")
  print(e.args[1].." "..e.args[2])
  e=state:resume()
end
assert(e.status=="completed" and e.termination=="return",tostring(e.reason))
"""
    writes = dict(tuple(map(int,line.split())) for line in _execute(lua,runner,root/"Tools/Lua-5.4.7/lua.exe"))
    first = START_FLAG + 8*len(PREFIX)
    converted = [writes[first+i] for i in range(len(CASES))]
    if dos != [1]*(len(CASES)-2)+[0,0] or converted != dos:
        raise ValueError(f"DOS and generated arithmetic: DOS={dos}, Lua={converted}")
    return {"status":"passed", "edition":"Forge diagnostic script", "session":str(session),
            "source_sha256":spec["source_sha256"], "inputs":{k:native["inputs"][k] for k in ("U7.EXE","STATIC/USECODE","STATIC/LINKDEP2")},
            "wasm_sha256":native["wasm_sha256"], "lua_sha256":hashlib.sha256(lua.encode()).hexdigest(),
            "published_campaign":published, "source_offset":spec["base"], "original_callee":{"function":0x932,"code_offset":begin,
            "sha256":callee["code_sha256"]}, "memory":obs, "cases":[
                {"name":c[0], "opcode":c[1], "left":c[2], "right":c[3], "compared_to":c[4],
                 "dos_equal":bool(dos[i]), "lua_equal":bool(converted[i])} for i,c in enumerate(CASES)]}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("installation", type=Path)
    parser.add_argument("--session", type=Path, help="recheck a completed native diagnostic")
    parser.add_argument("--campaign", type=Path, help="execute the diagnostic caller in a private copy of the published Lua module")
    args = parser.parse_args()
    root = args.installation.resolve()
    session = args.session
    if session is None:
        spec = fixture((root/"Assets/UltimaVII-Steam/STATIC/USECODE").read_bytes())
        with tempfile.TemporaryDirectory(dir=root/"Cache/Temp") as temporary:
            path = Path(temporary)/"numeric.json"
            path.write_text(json.dumps(spec), encoding="ascii")
            cli = Path(__file__).with_name("capture.cjs")
            result = subprocess.run(["node", cli, root, "--numeric-probe", path], capture_output=True, text=True, timeout=150)
            if result.returncode:
                raise RuntimeError(result.stdout[-800:] + result.stderr[-1200:])
            session = Path(next(line for line in result.stdout.splitlines() if line.startswith(str(root))))
    print(json.dumps(compare(root, session, args.campaign), indent=2))
