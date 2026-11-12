"""Translate and execute an integer/flag subset of Black Gate Usecode."""

from __future__ import annotations

import hashlib
import json
import re
import struct
import subprocess
from dataclasses import dataclass
from pathlib import Path

from .u7 import STEAM_FORGE_USECODE, usecode_inventory


PROOF_FUNCTION = 0x06A4
STEAM_FUNCTION_CODE = "29aa57acfdf72f37e12858728c7477f6b8a3f934bf47f7491f7de52209f48db8"
SEMANTICS = "https://github.com/exult/exult/blob/dba00df48237c4b33862f0a9892a8001f75d6eb8/usecode/ucinternal.cc"
# mnemonic, operand format, values popped, values pushed
OPS = {
    0x05: ("jne", "<h", 1, 0), 0x06: ("jmp", "<h", 0, 0),
    0x13: ("pushtrue", "", 0, 1), 0x14: ("pushfalse", "", 0, 1),
    0x1F: ("pushi", "<h", 0, 1), 0x22: ("cmpeq", "", 2, 1),
    0x25: ("ret", "", 0, 0), 0x43: ("popf", "<H", 1, 0),
    0x48: ("pusheventid", "", 0, 1),
}


@dataclass(frozen=True)
class Instruction:
    pc: int
    op: int
    end: int
    arg: int | None


def translate(code: bytes, source_offset: int = 0) -> tuple[str, list[dict]]:
    """Emit Lua with fixed integer stack slots and branch labels at instruction boundaries."""
    if not 0 < len(code) <= 65535:
        raise ValueError("Usecode proof requires 1..65535 instruction bytes")
    insns = {}
    pc = 0
    while pc < len(code):
        op = code[pc]
        if op not in OPS:
            raise ValueError(f"unsupported opcode 0x{op:02X} at source offset {source_offset + pc}")
        name, fmt, _, _ = OPS[op]
        end = pc + 1 + struct.calcsize(fmt)
        if end > len(code):
            raise ValueError(f"truncated {name} operand at {source_offset + pc}")
        arg = struct.unpack_from(fmt, code, pc + 1)[0] if fmt else None
        if name == "popf" and arg >= 32768:
            raise ValueError(f"global flag index {arg} exceeds the host range")
        insns[pc] = Instruction(pc, op, end, arg)
        pc = end

    depths = {0: 0}
    highest = 0
    for pc, ins in insns.items():
        if pc not in depths:
            raise ValueError(f"unreachable instruction at {source_offset + pc}")
        name, _, pops, pushes = OPS[ins.op]
        depth = depths[pc]
        if depth < pops:
            raise ValueError(f"stack underflow at {source_offset + pc}")
        after = depth - pops + pushes
        highest = max(highest, after)
        if name == "ret" and depth:
            raise ValueError(f"nonempty stack at procedure return at {source_offset + pc}")
        edges = [] if name in {"ret", "jmp"} else [ins.end]
        if name in {"jmp", "jne"}:
            target = ins.end + ins.arg
            if target <= pc:
                raise ValueError(f"backward branch unsupported at {source_offset + pc}")
            edges.append(target)
        for target in edges:
            if target not in insns:
                raise ValueError(f"{name} reaches a non-instruction offset {source_offset + target}")
            if target in depths and depths[target] != after:
                raise ValueError(f"inconsistent stack depth at join {source_offset + target}")
            depths[target] = after

    # Lua 5.4 limits a single function to 200 local variables.
    if highest > 197:
        raise ValueError("operand stack exceeds the Lua proof backend's local variable limit")
    lines = ["return function(event, flags)"]
    if highest:
        lines.append("  local " + ", ".join(f"s{n}" for n in range(1, highest + 1)))
    source_map = []
    for pc, ins in insns.items():
        name = OPS[ins.op][0]
        depth = depths[pc]
        top, below, new = f"s{depth}", f"s{depth - 1}", f"s{depth + 1}"
        if name == "pusheventid":
            line = f"{new} = event"
        elif name in {"pushtrue", "pushfalse", "pushi"}:
            value = ins.arg if name == "pushi" else int(name == "pushtrue")
            line = f"{new} = {value}"
        elif name == "cmpeq":
            line = f"{below} = ({below} == {top}) and 1 or 0"
        elif name == "jne":
            line = f"if {top} == 0 then goto pc_{ins.end + ins.arg} end"
        elif name == "jmp":
            line = f"goto pc_{ins.end + ins.arg}"
        elif name == "popf":
            line = f"flags[{ins.arg}] = ({top} ~= 0) and 1 or 0"
        elif name == "ret":
            line = "do return end"
        else:
            raise ValueError(f"missing Lua emitter for {name}")
        lines.extend([f"  ::pc_{pc}::", "  " + line])
        source_map.append({
            "pc": pc, "source_offset": source_offset + pc, "opcode": name,
            "operand": ins.arg, "lua_line": len(lines), "stack_before": depth,
        })
    lines.append("end")
    return "\n".join(lines) + "\n", source_map


def _digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _artifact(code: bytes, record_offset: int, code_offset: int, usecode_sha: str):
    lua, source_map = translate(code, code_offset)
    metadata = {
        "format": 1, "function_id": PROOF_FUNCTION, "source": "STATIC/USECODE",
        "source_sha256": usecode_sha, "record_offset": record_offset, "code_offset": code_offset,
        "code_hex": code.hex(), "code_sha256": _digest(code), "instruction_count": len(source_map),
        "source_map": source_map, "lua_sha256": _digest(lua.encode()), "semantics_source": SEMANTICS,
        "dos_runtime_comparison": "not_run",
    }
    return lua, metadata


def _dos_child(folder: Path, name: str) -> Path:
    found = [p for p in folder.iterdir() if p.name.upper() == name]
    if len(found) != 1:
        raise ValueError(f"expected one {name} in {folder}")
    return found[0]


def produce_lua(u7_root: Path, output_dir: Path) -> dict:
    data = _dos_child(_dos_child(u7_root, "STATIC"), "USECODE").read_bytes()
    corpus = usecode_inventory(data)
    rec = next((row for row in corpus["records"] if row["id"] == PROOF_FUNCTION), None)
    if rec is None:
        raise ValueError(f"proof function 0x{PROOF_FUNCTION:04X} missing from STATIC/USECODE")
    pc = rec["code_offset"]
    lua, metadata = _artifact(data[pc:pc + rec["code_length"]], rec["offset"], pc, corpus["sha256"])
    (output_dir / "function.lua").write_bytes(lua.encode())
    (output_dir / "script.json").write_bytes((json.dumps(metadata, indent=2) + "\n").encode())
    return metadata


def verify_lua(release_dir: Path, interpreter_path: Path) -> dict:
    """Recompile saved bytecode, compare source maps, and run three independent flag states."""
    try:
        raw = (release_dir / "script.json").read_bytes()
        if len(raw) > 16_000_000:
            raise ValueError("script.json exceeds the proof size limit")
        m = json.loads(raw)
        code = bytes.fromhex(m["code_hex"])
        record_offset, code_offset, sha = m["record_offset"], m["code_offset"], m["source_sha256"]
        if (type(record_offset) is not int or type(code_offset) is not int
                or not 0 <= record_offset <= code_offset - 12 or not re.fullmatch("[a-f0-9]{64}", sha)):
            raise ValueError("invalid source provenance")
        lua, expected = _artifact(code, record_offset, code_offset, sha)
        if m != expected or (release_dir / "function.lua").read_bytes() != lua.encode():
            raise ValueError("Lua artifact or source map differs from recompilation")
        if sha == STEAM_FORGE_USECODE and expected["code_sha256"] != STEAM_FUNCTION_CODE:
            raise ValueError("instruction bytes differ from the pinned Steam function")
        inputs = release_dir / "inputs.json"
        if inputs.is_file():
            inventory = json.loads(inputs.read_bytes())["u7"]["usecode"]
            rec = next((r for r in inventory["records"] if r["id"] == PROOF_FUNCTION), None)
            if (inventory["sha256"] != sha or not rec or rec["offset"] != record_offset
                    or rec["code_offset"] != code_offset or rec["code_length"] != len(code)):
                raise ValueError("Lua function provenance disagrees with the frozen Usecode inventory")
    except (TypeError, KeyError, UnicodeError) as exc:
        raise ValueError(f"invalid script metadata: {exc}") from exc

    # Only generated, byte-for-byte recompiled code reaches load. Empty _ENV for the
    # generated chunk, stdin for the trusted driver, no profile scripts or LUA_INIT.
    driver = """local fn = assert(load([=[
""" + lua + """]=], "@function.lua", "t", {}))()
local cases = {{3, 0, 1}, {1, 0, 0}, {0, 1, 1}}
for _, case in ipairs(cases) do
  local flags = {[2] = 1, [60] = case[2], [61] = 0}
  fn(case[1], flags)
  assert(flags[60] == case[3] and flags[2] == 1 and flags[61] == 0, "unexpected flag value")
  local count = 0
  for _ in pairs(flags) do count = count + 1 end
  assert(count == 3, "unexpected global flag")
end
print("3 scenarios passed")
"""
    try:
        result = subprocess.run([str(interpreter_path.resolve()), "-E", "-"], input=driver,
                                text=True, capture_output=True, timeout=5, check=False)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise ValueError(f"could not execute Lua proof: {exc}") from exc
    if result.returncode or result.stdout.strip() != "3 scenarios passed":
        raise ValueError(f"Lua proof failed: {result.stderr.strip() or result.stdout.strip()}")
    return {
        "status": "passed", "function_id": PROOF_FUNCTION, "instruction_count": len(expected["source_map"]),
        "interpreter_sha256": _digest(interpreter_path.read_bytes()), "scenarios_passed": 3,
        "scenarios": [
            {"event": event, "flag_0x3c_before": before, "flag_0x3c_after": after}
            for event, before, after in [(3, 0, 1), (1, 0, 0), (0, 1, 1)]
        ], "other_flags_preserved": True, "dos_runtime_comparison": "not_run",
    }
