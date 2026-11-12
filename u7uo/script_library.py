"""Translate closed, supported functions from the structural DOS Usecode IR to Lua 5.4."""

from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path

from .lua import SEMANTICS
from .u7 import STEAM_FORGE_USECODE


_BINARY = {
    0x09: "add", 0x0A: "sub", 0x0B: "div", 0x0C: "mul", 0x0D: "mod",
    0x0E: "and", 0x0F: "or", 0x16: "gt", 0x17: "lt", 0x18: "ge", 0x19: "le",
    0x1A: "ne", 0x22: "eq",
}
_SUPPORTED = _BINARY.keys() | {
    0x05, 0x06, 0x10, 0x12, 0x13, 0x14, 0x1E, 0x1F, 0x21, 0x24, 0x25,
    0x26, 0x2C, 0x2D, 0x32, 0x42, 0x43, 0x44, 0x46, 0x48, 0x4B,
}


# U distinguishes an uninitialized local from an explicit integer zero in arithmetic.
# Arrays are immutable within generated code: a write constructs a replacement.
_RUNTIME = """local F, U = {}, {}
local function integer(v)
  assert(math.type(v) == "integer" and v >= -2147483648 and v <= 2147483647, "unsupported integer")
  return v
end
local function array(v) return type(v) == "table" and v ~= U end
local function numeric(v)
  if array(v) then v = v[1] or 0 end
  return v == U and 0 or integer(v)
end
local function truth(v)
  if array(v) then return #v > 0 end
  return numeric(v) ~= 0
end
local function equal(a,b)
  if array(a) and array(b) then
    if #a ~= #b then return false end
    for i=1,#a do if numeric(a[i]) ~= numeric(b[i]) then return false end end
    return true
  end
  return numeric(a) == numeric(b)
end
local function pop(s)
  local n = #s
  assert(n > 0, "operand stack underflow")
  local v = s[n]
  s[n] = nil
  return v
end
local function push(s,v) s[#s+1] = v end
local function binary(s,op)
  local b,a = pop(s),pop(s)
  if op == "eq" then push(s,equal(a,b) and 1 or 0); return end
  if op == "ne" then push(s,equal(a,b) and 0 or 1); return end
  if op == "and" then push(s,(truth(a) and truth(b)) and 1 or 0); return end
  if op == "or" then push(s,(truth(a) or truth(b)) and 1 or 0); return end
  if op == "gt" then push(s,numeric(a) > numeric(b) and 1 or 0); return end
  if op == "lt" then push(s,numeric(a) < numeric(b) and 1 or 0); return end
  if op == "ge" then push(s,numeric(a) >= numeric(b) and 1 or 0); return end
  if op == "le" then push(s,numeric(a) <= numeric(b) and 1 or 0); return end
  if op == "add" and (a == U or b == U) then push(s,a == U and b or a); return end
  assert(not array(a) and not array(b), "unsupported array arithmetic")
  if a ~= U and b == U then push(s,0); return end
  a,b = numeric(a),numeric(b)
  local result
  if op == "add" then result = a + b
  elseif op == "sub" then result = a - b
  elseif op == "mul" then result = a * b
  else
    assert(b ~= 0, "division by zero requires a DOS reference comparison")
    local quotient = math.abs(a) // math.abs(b)
    if (a < 0) ~= (b < 0) then quotient = -quotient end
    result = op == "div" and quotient or a - quotient*b
  end
  push(s,integer(result))
end
local function read_index(v,i)
  if i < 1 then return 0 end
  if array(v) then return v[i] or 0 end
  return i == 1 and v or 0
end
local function write_index(v,i,value)
  assert(i >= -32767 and i <= 4096, "array index outside backend range")
  if i < 1 then return v end
  assert(not array(value), "nested array write requires another value profile")
  local a = {}
  if array(v) then for j=1,#v do a[j] = v[j] end else a[1] = v end
  for j=#a+1,i do a[j] = U end
  a[i] = value
  return a
end
local function construct(s,n)
  local a = {}
  for i=1,n do
    local v = pop(s)
    if array(v) then for j=1,#v do a[#a+1] = v[j] end else a[#a+1] = v end
    assert(#a <= 4096, "array exceeds backend range")
  end
  push(s,a)
end
local function arguments(s,n)
  while #s < n do push(s,0) end
  local a = {}
  for i=n-1,0,-1 do a[i] = pop(s) end
  return a
end
local function enter(h,id)
  assert(h.depth < 64, "call depth exceeded")
  h.depth = h.depth + 1
  h.trace[#h.trace+1] = id
end
local function step(h,id,pc)
  h.id,h.pc = id,pc
  h.fuel = h.fuel - 1
  assert(h.fuel >= 0, "instruction limit at " .. id .. "+" .. pc)
end
local function direct(s,n,id,event,h)
  local r = F[id](arguments(s,n),event,h)
  h.depth = h.depth - 1
  if r ~= nil then push(s,r) end
end
"""

_PUBLIC = """local function external(v)
  if type(v) ~= "table" then return integer(v) end
  assert(#v <= 4096, "array exceeds backend range")
  local a = {}
  for i=1,#v do a[i] = integer(v[i]) end
  for k in pairs(v) do assert(math.type(k) == "integer" and k >= 1 and k <= #v, "non-array key") end
  return a
end
return function(id,args,event,flags)
  assert(F[id], "function outside compiled closure")
  local s = {}
  assert(#args <= 4096, "argument list exceeds backend range")
  for i=1,#args do push(s,external(args[i])) end
  assert(#args <= arity[id], "extra entry arguments")
  local h = {flags = {}, trace = {}, depth = 0, fuel = 100000}
  for k,v in pairs(flags) do
    assert(math.type(k) == "integer" and k >= 0 and k < 32768 and (v == 0 or v == 1), "invalid flag")
    h.flags[k] = v
  end
  local ok,r = pcall(F[id],arguments(s,arity[id]),integer(event),h)
  if not ok then error("function " .. (h.id or id) .. " pc " .. (h.pc or 0) .. ": " .. r) end
  for k,v in pairs(h.flags) do flags[k] = v end
  if r == U then r = 0 elseif array(r) then
    local a = {}
    for i=1,#r do a[i] = numeric(r[i]) end
    r = a
  end
  return r,h.trace
end
"""


def _arity(fn):
    return max(0, _integer(fn["arguments"]) - int(fn["id"] < 0x800))


def _statement(op, arg, target, arities):
    if op in _BINARY:
        return f'binary(s,"{_BINARY[op]}")'
    if op in {0x1F, 0x44}:
        return f"push(s,{arg})"
    if op == 0x24:
        return f"direct(s,{arities[target]},{target},event,h)"
    return {
        0x05: f"if not truth(pop(s)) then goto pc_{target} end", 0x06: f"goto pc_{target}",
        0x10: "push(s,truth(pop(s)) and 0 or 1)", 0x12: f"l[{arg}] = pop(s)",
        0x13: "push(s,1)", 0x14: "push(s,0)", 0x1E: f"construct(s,{arg})",
        0x21: f"push(s,l[{arg}] or U)", 0x25: "do return end", 0x2C: "do return end",
        0x26: f"push(s,read_index(l[{arg}] or U,numeric(pop(s))))", 0x2D: "do return pop(s) end",
        0x32: "do return 0 end", 0x42: f"push(s,h.flags[{arg}] or 0)",
        0x43: f"h.flags[{arg}] = numeric(pop(s)) ~= 0 and 1 or 0",
        0x46: f"do local i = numeric(pop(s)); l[{arg}] = write_index(l[{arg}] or U,i,pop(s)) end",
        0x48: "push(s,event)", 0x4B: "event = numeric(pop(s))",
    }[op]


def _integer(value, minimum=0, maximum=0xFFFF):
    if type(value) is not int or not minimum <= value <= maximum:
        raise ValueError("invalid numeric operand in Usecode IR")
    return value


def compile_library(ir):
    """Emit only functions whose CFG-reachable instructions and callees have a lowering."""
    if ir["schema"] != 1 or ir["format"] != "dos-black-gate-16bit":
        raise ValueError("unsupported Usecode IR")
    by_id = {_integer(f["id"]): f for f in ir["functions"]}
    if len(by_id) != len(ir["functions"]):
        raise ValueError("duplicated function ID")
    arities = {i: _arity(f) for i, f in by_id.items()}
    issues, edges, records = {}, {}, {}
    for fid, fn in by_id.items():
        base = _integer(fn["code_offset"], 0, 2**32-1)
        branches = {int(k): _integer(v) for k,v in fn["branches"].items()}
        rows, calls, problems = [], [], []
        for pc, op, operands, _, _, reachable in fn["instructions"]:
            if not reachable:
                continue
            pc, op = _integer(pc), _integer(op, 0, 255)
            args = [_integer(v, -32768) for v in operands]
            arg = args[0] if args else None
            target = None
            if op == 0x24:
                if not args or not 0 <= arg < len(fn["externs"]):
                    raise ValueError("extern index outside table")
                target = _integer(fn["externs"][arg])
                calls.append((pc,target))
            elif op in {0x05, 0x06}:
                target = branches[pc]
            rows.append((pc,op,arg,target))
            if op not in _SUPPORTED or (op in {0x42,0x43} and not 0 <= arg < 32768):
                problems.append({"pc": pc, "source_offset": base + pc, "opcode": op,
                                 "reason": "unsupported_opcode" if op not in _SUPPORTED else "flag_out_of_range",
                                 "operands": args})
        if problems:
            issues[fid] = problems
        records[fid], edges[fid] = rows, calls
    selected = set(by_id) - issues.keys()
    while True:
        removed = {f for f in selected if any(target not in selected for _,target in edges[f])}
        if not removed:
            break
        selected -= removed
    for fid in sorted(set(by_id) - selected):
        for pc, target in edges[fid]:
            if target not in selected:
                issues.setdefault(fid, []).append({"pc": pc, "source_offset": by_id[fid]["code_offset"] + pc,
                                                   "opcode": 0x24, "target": target, "reason": "uncompiled_callee"})
        issues[fid].sort(key=lambda r: (r["pc"], r["reason"]))
    lines = [_RUNTIME, "local arity = {}"]
    for fid in sorted(selected):
        lines += [f"arity[{fid}] = {arities[fid]}", f"F[{fid}] = function(l,event,h)",
                  f"  enter(h,{fid})", "  local s = {}"]
        for pc,op,arg,target in records[fid]:
            lines += [f"  ::pc_{pc}:: step(h,{fid},{pc})", "  " + _statement(op,arg,target,arities)]
        lines += ["end"]
    lua = "\n".join(lines + [_PUBLIC])
    info = {"schema": 1, "source_sha256": ir["sha256"], "lua_sha256": hashlib.sha256(lua.encode()).hexdigest(),
            "semantics": [SEMANTICS, SEMANTICS.replace("ucinternal.cc", "useval.cc")],
            "profile": "signed-32-bit integers, flat integer arrays, frame-local events, global flag values without engine/UI hooks",
            "runtime_guards": ["overflow", "zero divisor", "nested array writes", "array arithmetic",
                               "stack underflow", "array length >4096", "call depth >64", "instructions >100000"],
            "functions_compiled": len(selected), "function_ids": sorted(selected),
            "functions_with_diagnostics": len(issues), "diagnostics": {str(k):v for k,v in sorted(issues.items())},
            "instructions_emitted": sum(len(records[f]) for f in selected),
            "dos_runtime_comparison": "not_run"}
    return lua, info


def produce_script_library(release_dir: Path) -> dict:
    release_dir = Path(release_dir)
    lua, info = compile_library(json.loads((release_dir / "usecode-ir.json").read_bytes()))
    (release_dir / "script-library.lua").write_bytes(lua.encode())
    (release_dir / "script-library.json").write_bytes((json.dumps(info, sort_keys=True, separators=(",", ":")) + "\n").encode())
    return info


_CHAIN_CASES = """local function same(a,b)
  assert(#a == #b)
  for i=1,#a do assert(a[i] == b[i]) end
end
local function flag_count(flags)
  local n = 0; for _ in pairs(flags) do n = n+1 end
  return n
end
local cases = {
  {781,{8,10,12},{0x82D,0x82B,0x82A}},
  {150,{10,14,18},{0x82D,0x82A}},
  {0,{9,12,15},{0x82D}}
}
for _,c in ipairs(cases) do
  local a,b = {1,2,3},{9,12,15}
  local flags = {[17]=1}
  local r,t = invoke(0x82D,{c[1],a,b},3,flags)
  same(r,c[2]); same(t,c[3]); same(a,{1,2,3}); same(b,{9,12,15})
  assert(flags[17] == 1 and flag_count(flags) == 1)
end
for _,c in ipairs({{3,0,1},{1,0,0},{0,1,1}}) do
  local flags = {[60]=c[2],[17]=1}
  local r,t = invoke(0x6A4,{},c[1],flags)
  assert(r == nil and flags[60] == c[3] and flags[17] == 1 and flag_count(flags) == 2)
  same(t,{0x6A4})
end
"""


def _run_cases(lua, cases, interpreter_path):
    # The Lua text is recompiled in Python and operands are allowlisted integers.
    # No source text from data sections is embedded in the generated chunk.
    env = "{math={type=math.type,abs=math.abs},assert=assert,error=error,pcall=pcall,type=type,pairs=pairs}"
    driver = f"local invoke = assert(load([=[\n{lua}]=], '@script-library.lua', 't', {env}))()\n"
    try:
        p = subprocess.run([str(Path(interpreter_path).resolve()), "-E", "-"], input=driver + cases + '\nprint("ok")',
                           text=True, capture_output=True, check=False, timeout=8)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise ValueError(f"Lua script library runner failed: {exc}") from exc
    if p.returncode or p.stdout.strip() != "ok":
        raise ValueError(f"Lua script library verification failed: {p.stderr.strip() or p.stdout.strip()}")


def _qualification_source(ir):
    # Freeze the source of the independent vectors as well as the container edition.
    # Ignore JSON key spelling differences introduced by a serialize/parse cycle.
    functions = []
    for f in sorted(ir["functions"], key=lambda r: r["id"]):
        if f["id"] not in {0x6A4, 0x82A, 0x82B, 0x82D}:
            continue
        functions.append([f["id"], f["record_offset"], f["code_offset"], f["code_length"],
                          f["arguments"], f["locals"], f["externs"],
                          sorted((int(k),v) for k,v in f["branches"].items()),
                          [[pc,op,args,reach] for pc,op,args,_,_,reach in f["instructions"]]])
    return hashlib.sha256(json.dumps(functions, separators=(",", ":")).encode()).hexdigest()


def verify_script_library(release_dir: Path, interpreter_path: Path) -> dict:
    release_dir = Path(release_dir)
    ir = json.loads((release_dir / "usecode-ir.json").read_bytes())
    lua, info = compile_library(ir)
    if ((release_dir / "script-library.lua").read_bytes() != lua.encode()
            or json.loads((release_dir / "script-library.json").read_bytes()) != info):
        raise ValueError("script library differs from recompilation")
    if info["source_sha256"] != STEAM_FORGE_USECODE:
        raise ValueError("no independently derived execution vectors registered for this source edition")
    if _qualification_source(ir) != "73d8be2fb87fb3f20819b6ff2dbc81cfe7526b7f251f840b4663cbad245d2d99":
        raise ValueError("execution vector functions differ from the pinned source")
    _run_cases(lua, _CHAIN_CASES, interpreter_path)
    return {"status": "passed", "scenarios_passed": 6, "function_ids_observed": [0x6A4, 0x82A, 0x82B, 0x82D],
            "root_function": 0x82D, "source_sha256": info["source_sha256"],
            "interpreter_sha256": hashlib.sha256(Path(interpreter_path).read_bytes()).hexdigest(),
            "call_chain_cases": [{"selector": n, "return": a, "calls": c} for n,a,c in
                                 [(781,[8,10,12],[0x82D,0x82B,0x82A]),(150,[10,14,18],[0x82D,0x82A]),(0,[9,12,15],[0x82D])]],
            "caller_arrays_preserved": True, "flag_cases_passed": 3, "dos_runtime_comparison": "not_run"}
