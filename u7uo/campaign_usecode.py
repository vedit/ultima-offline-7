"""Build and exercise the complete private Usecode module from the selected corpus."""

import json
import re
from collections import Counter, defaultdict

from .dialogue import CURRENT_GENERATOR, _bytes, _execute, _extract, _sha, compile_dialogue
from .u7 import STEAM_FORGE_USECODE, usecode_inventory


def compile_corpus(raw, ir, version=CURRENT_GENERATOR):
    roots = {f["id"] for f in ir["functions"]}
    records = usecode_inventory(raw)["records"]
    if len(roots)!=len(ir["functions"]) or len(roots)!=len(records) or roots!={r["id"] for r in records}:
        raise ValueError("Complete campaign IR must account for every original function exactly once")
    program = _extract(raw, ir, roots)
    lua, diagnostics = compile_dialogue(program,version)
    issues = defaultdict(list)
    for diagnostic in diagnostics:
        issues[diagnostic["function_id"]].append(diagnostic)
    index = {}
    for f in program["functions"]:
        index[str(f["id"])] = {"code_offset":f["base"], "code_sha256":f["code_sha256"],
                               "reachable_instructions":len(f["rows"]), "diagnostics":issues[f["id"]]}
    info = {"schema":1, "source_sha256":program["source_sha256"], "lua_sha256":_sha(lua.encode()),
            "functions":index, "generated_functions":len(index),
            "decoded_instructions":sum(len(f["instructions"]) for f in ir["functions"]),
            "reachable_instructions":sum(len(f["rows"]) for f in program["functions"]),
            "functions_without_local_opcode_diagnostics":sum(not f["diagnostics"] for f in index.values()),
            "unsupported_instruction_sites":len(diagnostics)}
    if version >= 3:
        info["generator_version"] = version
        info["numeric_division_profile"] = "signed 16-bit integer heads; unqualified types and signed overflow stop at the source instruction"
    if version >= 4:
        info["numeric_arithmetic_profile"] = "signed 16-bit addition, subtraction and multiplication of integer heads with low-word wrap"
    return lua, info


def produce_corpus(u7, directory):
    raw = (u7/"STATIC/USECODE").read_bytes()
    lua, info = compile_corpus(raw,json.loads((directory/"usecode-ir.json").read_bytes()))
    (directory/"campaign-usecode.source").write_bytes(raw)
    (directory/"campaign-usecode.lua").write_bytes(lua.encode())
    (directory/"campaign-usecode.json").write_bytes(_bytes(info))
    return info


def bind_world_functions(directory, target):
    """Link the world's registered events and their callees out of the compiled corpus."""
    manifest = json.loads((directory/"campaign-usecode.json").read_bytes())
    source = (directory/"campaign-usecode.lua").read_bytes()
    profile = json.loads((directory/"dialogue.json").read_bytes())
    program = profile["program"]
    if _sha(source)!=manifest["lua_sha256"] or program["source_sha256"]!=manifest["source_sha256"]:
        raise ValueError("Campaign Lua and playable event bindings belong to different inputs")
    version = manifest.get("generator_version",2)
    canonical, issues = compile_dialogue(program,version)
    headers = list(re.finditer(rb"(?m)^arity\[(\d+)\]=\d+\n",source))
    trailer = b"return {start=start}\n"
    if not source.endswith(trailer) or len(headers)!=manifest["generated_functions"]:
        raise ValueError("Incomplete campaign Lua function table")
    end = len(source)-len(trailer)
    starts = [m.start() for m in headers]+[end]
    spans = {int(m[1]):(starts[i],starts[i+1]) for i,m in enumerate(headers)}
    runtime = source[:source.index(b"\nroots[")+1]
    roots = b"".join(f"roots[{fid}]=true\n".encode() for fid in program["roots"])
    fragments = []
    for f in program["functions"]:
        fid = f["id"]
        if manifest["functions"][str(fid)]["code_sha256"]!=f["code_sha256"]:
            raise ValueError(f"Playable function {fid:04X} differs from the corpus")
        begin, stop = spans[fid]
        fragments.append(source[begin:stop])
    linked = b"".join([runtime,roots,*fragments,trailer])
    if linked!=canonical.encode():
        raise ValueError("Linked campaign functions differ from source recompilation")
    profile.update(lua_sha256=_sha(linked),generator_version=version,diagnostics=issues,
                   campaign_binding={"corpus_lua_sha256":manifest["lua_sha256"],
                                     "available_functions":len(headers),"bound_functions":len(fragments),
                                     "registered_roots":program["roots"]})
    (target/"dialogue.lua").write_bytes(linked)
    (target/"dialogue.json").write_bytes(_bytes(profile))


def entry_effect(function):
    """Read a straight-line prefix of source IR independently of the Lua lowering."""
    stack = []
    for pc, op, operands, *_ in function["instructions"]:
        if op in (0x1F,0x44):
            stack.append(operands[0])
        elif op in (0x13,0x14,0x3E,0x48):
            stack.append({0x13:1,0x14:0,0x3E:-356,0x48:1}[op])
        elif op == 0x42:
            return pc,"flag_read",True,0,[operands[0]]
        elif op == 0x43 and stack:
            return pc,"flag_write",False,0,[operands[0],int(stack[-1]!=0)]
        elif op in (0x38,0x39):
            intrinsic, argc = operands
            if 5 <= intrinsic <= 11 or len(stack) < argc:
                return None
            return pc,"intrinsic",op==0x38,intrinsic,list(reversed(stack))[:argc]
        else:
            return None
    return None


def verify_corpus(directory, interpreter):
    ir = json.loads((directory/"usecode-ir.json").read_bytes())
    manifest = json.loads((directory/"campaign-usecode.json").read_bytes())
    version = manifest.get("generator_version",2)
    if version not in (2,3,4):
        raise ValueError("Unsupported campaign Usecode generator revision")
    lua, info = compile_corpus((directory/"campaign-usecode.source").read_bytes(),ir,version)
    if ((directory/"campaign-usecode.lua").read_bytes()!=lua.encode() or
            (directory/"campaign-usecode.json").read_bytes()!=_bytes(info)):
        raise ValueError("Private campaign Lua or function index differs from source recompilation")
    # Each row is a function-specific test of a real host boundary. The host
    # returns no fabricated answer and the program stops at that first effect.
    vectors = []
    expected = []
    encountered = Counter()
    reachable = Counter()
    for f in ir["functions"]:
        for _, opcode, operands, _, _, in_cfg in f["instructions"]:
            if opcode in (0x38,0x39):
                encountered[operands[0]] += 1
                if in_cfg:
                    reachable[operands[0]] += 1
    first_calls = Counter()
    for f in ir["functions"]:
        effect = entry_effect(f)
        if effect is None:
            continue
        pc,kind,keep,intrinsic,args = effect
        expected.append((f["id"],pc,kind,intrinsic))
        numbers = ",".join(map(str,args))
        vectors.append(f'{{{f["id"]},{pc},{f["code_offset"]+pc},"{kind}",'
                       f'{str(keep).lower()},{intrinsic},{{{numbers}}}}}')
    if not vectors:
        raise ValueError("No source-derived entry effects to qualify")
    driver = "local vectors={\n"+",\n".join(vectors)+"\n}\n"+"""
for _,v in ipairs(vectors) do
  local e=mod.start(v[1],1,-356):resume()
  assert(e.status=="effect" and e.sequence==1 and e.function_id==v[1] and e.pc==v[2]
    and e.source_offset==v[3] and e.kind==v[4] and e.expects_value==v[5]
    and (e.intrinsic or 0)==v[6] and #e.args==#v[7],"unexpected effect in "..v[1])
  for i,n in ipairs(v[7]) do assert(e.args[i]==n,"unexpected operand in "..v[1]) end
  print(e.function_id,e.pc,e.kind,e.intrinsic or 0)
end
"""
    actual = []
    for line in _execute(lua,driver,interpreter):
        fid,pc,kind,intrinsic = line.split("\t")
        actual.append((int(fid),int(pc),kind,int(intrinsic)))
        if kind=="intrinsic":
            first_calls[int(intrinsic)] += 1
    if actual != expected:
        raise ValueError("Incomplete Lua entry-effect execution")
    observed = [fid for fid,_,_,_ in actual]
    retail = "not_run"
    all_observed = set(observed)
    if version >= 3 and info["source_sha256"] == STEAM_FORGE_USECODE:
        # Retail 0501:0001 calls the object function 0326 with PUSH ITEM.
        # Event zero aborts there. Event one gets the NPC from that same item.
        # Helper 081C reads a frame, takes its remainder modulo four, then
        # requests SET_FRAME with the original four-frame group base.
        vectors = """
local s=mod.start(0x501,0,-27)
local e=s:resume()
assert(e.termination=="abort" and e.function_id==0x326 and e.pc==8)
for _,item in ipairs({-27,-12}) do
  e=mod.start(0x501,1,item):resume()
  assert(e.kind=="intrinsic" and e.intrinsic==0x1b and e.function_id==0x326 and e.pc==10
    and e.args[1]==item and #e.call_stack==2 and e.call_stack[1].function_id==0x501
    and e.call_stack[1].pc==1 and e.call_stack[2].source_offset==e.source_offset)
end
for _,frame in ipairs({0,7,8,9,31}) do
  s=mod.start(0x81c,1,-27)
  e=s:resume()
  assert(e.intrinsic==0x12 and e.pc==3)
  e=s:resume(frame)
  assert(e.intrinsic==0x13 and e.pc==34 and e.args[2]==frame-frame%4)
  assert(s:resume().status=="completed")
end
print("passed")
"""
        if _execute(lua,vectors,interpreter)!=["passed"]:
            raise ValueError("Real campaign item dispatch and frame requests did not match")
        retail = {"status":"passed","caller":0x501,"callee":0x326,"events":[0,1],
                  "item_handles":[-27,-12],"frame_function":0x81C,"input_frames":[0,7,8,9,31]}
        all_observed.update((0x501,0x326,0x81C))
    return {**{k:v for k,v in info.items() if k!="functions"}, "status":"passed",
            "fixture_event":1, "fixture_item":-356, "entry_effects_observed":len(observed),
            "entry_function_ids":observed, "function_ids_observed":sorted(all_observed),
            "entry_fixture_host_responses":"not_run",
            "intrinsic_coverage":{str(i):{"source_sites":n,"reachable_source_sites":reachable[i],
                                          "entry_fixture_requests":first_calls[i]}
                                  for i,n in sorted(encountered.items())},
            "retail_call_and_frame_fixtures":retail, "campaign_gameplay":"not_run"}
