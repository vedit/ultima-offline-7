"""Structural IR and static dispatch inventory for original 16-bit Black Gate Usecode."""

from __future__ import annotations

import hashlib
import json
import re
import struct
import subprocess
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

from .u7 import usecode_inventory


ROOTS = {"Iolo": 0x401, "Finnigan": 0x40C}
TERMINALS = {0x25, 0x2C, 0x2D, 0x32, 0x3F}
VALUE_RETURNS = {0x2D, 0x32}
BRANCHES = {0x02, 0x04, 0x05, 0x06, 0x07, 0x31}
CALLS = {0x24, 0x47}
INTRINSICS = {0x38, 0x39}
ACTION_INTRINSICS = {1: "immediate", 2: "delayed", 0x7D: "path_callback"}
TABLE_HASHES = {
    "u7opcodes.data": "6f3672eac35382254a1d6a9a95b0f0bf7ea55255a87a306660bfe5f79f886f93",
    "u7bgintrinsics.data": "446a9338bdfd15097ed2b00741c0d3d60edc911e650b2a3bce32cffe00573ddc",
}
FORMATS = {"flag": "H", "extoffset": "H", "dataoffset": "H", "varoffset": "H",
           "offset": "h", "short": "H", "byte": "B"}


@dataclass(frozen=True)
class Opcode:
    name: str
    kinds: tuple[str, ...]
    pops: int
    pushes: int

    @property
    def fmt(self):
        return "<" + "".join(FORMATS[k] for k in self.kinds)


def _sha(data):
    return hashlib.sha256(data).hexdigest()


def load_tables(directory):
    tables = {}
    for name, expected in TABLE_HASHES.items():
        data = (directory / name).read_bytes()
        if _sha(data) != expected:
            raise ValueError(f"unrecognized Exult Tools table {name}")
        tables[name] = re.sub(r"<!--.*?-->", "", data.decode("ascii"), flags=re.S)
    opcodes = {}
    for match in re.finditer(r"<0x([A-Fa-f0-9]+)>(.*?)\n\s*</>", tables["u7opcodes.data"], re.S):
        opcode = int(match[1], 16)
        if opcode > 0x4D:
            continue  # Exult's extended instruction formats belong to different source profiles.
        def field(name):
            return re.search(fr"<{name}>\s*(.*?)\s*</>", match[2])[1]
        kinds = tuple(k for k in field("param_types").strip("{}").split(",") if k)
        spec = Opcode(field("name"), kinds, int(field("num_pop"), 0), int(field("num_push"), 0))
        if opcode in opcodes and opcodes[opcode] != spec:
            raise ValueError(f"conflicting opcode table entries for {opcode:#x}")
        if struct.calcsize(spec.fmt) != int(field("num_bytes")):
            raise ValueError(f"operand table disagrees with byte width for {opcode:#x}")
        opcodes[opcode] = spec
    names = {int(i, 16): n for i, n in re.findall(r"<0x(\w+)>\s*(\w+)\s*</>", tables["u7bgintrinsics.data"])}
    return opcodes, names


def _decode(raw, record, schema):
    start, size = record["code_offset"], record["code_length"]
    function = record["id"]
    data_start = record["offset"] + 6
    data_end = data_start + record["data_length"]
    strings = {}
    externs = [v for (v,) in struct.iter_unpack("<H", raw[data_end + 6:start])]
    code = memoryview(raw)[start:start + size]
    rows, branches, calls, returns = [], {}, [], []
    op_counts = Counter()
    pc = 0
    while pc < size:
        opcode = code[pc]
        spec = schema.get(opcode)
        if spec is None:
            raise ValueError(f"{function:04X} at byte {start + pc}: unsupported opcode {opcode:02X}")
        end = pc + 1 + struct.calcsize(spec.fmt)
        if end > size:
            raise ValueError(f"{function:04X} at byte {start + pc}: truncated {spec.name}")
        args = list(struct.unpack_from(spec.fmt, code, pc + 1))
        if opcode == 0x1F and args[0] >= 32768:
            args[0] -= 65536
        loc = f"{function:04X} at byte {start + pc}"
        for idx, (kind, value) in enumerate(zip(spec.kinds, args)):
            if kind == "varoffset" or (opcode == 2 and idx < 3):
                if value >= record["locals"] + record["arguments"]:
                    raise ValueError(f"{loc}: invalid local {value}")
            elif kind == "dataoffset" and value not in strings:
                pos = data_start + value
                zero = raw.find(b"\x00", pos, data_end)
                if zero < 0:
                    raise ValueError(f"{loc}: invalid or unterminated string offset {value}")
                strings[value] = {"offset": pos, "length": zero - pos, "sha256": _sha(raw[pos:zero])}
        if opcode in BRANCHES:
            branches[pc] = end + args[-1]
        if opcode in CALLS:
            arg = args[0]
            if opcode == 0x24 and arg >= len(externs):
                raise ValueError(f"{loc}: invalid extern index {arg}")
            calls.append({"pc": pc, "kind": "extern" if opcode == 0x24 else "explicit_item",
                          "target": externs[arg] if opcode == 0x24 else arg})
        elif opcode in INTRINSICS:
            calls.append({"pc": pc, "kind": "intrinsic", "target": args[0], "argc": args[1]})
        if opcode in TERMINALS:
            returns.append([pc, opcode])
        rows.append([pc, opcode, args])
        op_counts[opcode] += 1
        pc = end
    boundaries = {row[0] for row in rows}
    for pc, target in branches.items():
        if target not in boundaries:
            raise ValueError(f"{function:04X} at byte {start + pc}: branch target {target} is not an instruction")
    return {
        "id": function, "record_offset": record["offset"], "code_offset": start, "code_length": size,
        "arguments": record["arguments"], "locals": record["locals"], "externs": externs,
        "strings_referenced": strings, "instructions": rows, "branches": branches,
        "call_sites": calls, "returns_or_aborts": returns, "opcodes": dict(sorted(op_counts.items())),
    }


def _flow(fn, functions, schema, diagnostics):
    rows = fn["instructions"]
    by_pc = {row[0]: (i, row) for i, row in enumerate(rows)}
    call_sites = {site["pc"]: site for site in fn["call_sites"]}
    if not rows:
        raise ValueError(f"empty instruction stream in function {fn['id']:04X}")
    reachable = set()
    todo = [0]
    while todo:
        pc = todo.pop()
        if pc in reachable:
            continue
        reachable.add(pc)
        index, (_, op, unused) = by_pc[pc]
        if op in BRANCHES:
            todo.append(fn["branches"][pc])
        if op not in TERMINALS and op != 0x06:
            if index + 1 == len(rows):
                raise ValueError(f"{fn['id']:04X} at {pc}: reachable fallthrough beyond function")
            todo.append(rows[index + 1][0])
    for pc, op, args in rows:
        spec = schema[op]
        pops, pushes = spec.pops, spec.pushes
        if op in {0x07, 0x1E}:
            pops = args[0]
        elif op in INTRINSICS:
            pops = args[1]
        elif op in CALLS:
            callee = functions.get(call_sites[pc]["target"])
            if callee is None:
                pops = pushes = None
            else:
                # Kitrinx stack_flow reports the target's declared arg count here.
                # Retail object-function slot zero can be implicit. Record nominal
                # arity, leaving its runtime stack adjustment for ABI qualification.
                pops = callee["arguments"]
                pushes = int(any(opcode in VALUE_RETURNS for _, opcode in callee["returns_or_aborts"]))
        by_pc[pc][1].extend([pops, pushes, pc in reachable])
    for site in fn["call_sites"]:
        site["entry_reachable"] = site["pc"] in reachable
        if site["kind"] != "intrinsic" and site["target"] not in functions:
            diagnostics.append({"function": fn["id"], **site, "reason": "absent_function"})
    fn["instructions_reachable_by_cfg"] = len(reachable)


def analyze_usecode(raw, schema, intrinsic_names, roots=None):
    roots = ROOTS if roots is None else roots
    inventory = usecode_inventory(raw)
    functions = {rec["id"]: _decode(raw, rec, schema) for rec in inventory["records"]}
    diagnostics, actions = [], []
    op_counts, intrinsic_counts = Counter(), Counter()
    edges = {}
    for function_id, fn in functions.items():
        _flow(fn, functions, schema, diagnostics)
        op_counts.update(fn["opcodes"])
        edges[function_id] = sorted({
            s["target"] for s in fn["call_sites"] if s["kind"] != "intrinsic" and s["entry_reachable"]
        })
        for site in fn["call_sites"]:
            if site["kind"] != "intrinsic":
                continue
            target = site["target"]
            intrinsic_counts[target] += 1
            if intrinsic_names.get(target, "UNKNOWN").upper().startswith("UNKNOWN"):
                diagnostics.append({"function": function_id, **site, "reason": "unnamed_intrinsic"})
            if target in ACTION_INTRINSICS:
                actions.append({"function": function_id, "source_offset": fn["code_offset"] + site["pc"],
                                "dispatch": ACTION_INTRINSICS[target], **site})
    reach = {}
    for name, root in roots.items():
        if root not in functions:
            raise ValueError(f"missing {name} root function {root:04X}")
        visited, pending = set(), [root]
        while pending:
            target = pending.pop()
            if target in visited or target not in functions:
                continue
            visited.add(target)
            pending.extend(edges[target])
        bound_sites = [s for f in visited for s in functions[f]["call_sites"] if s["entry_reachable"]]
        reach[name] = {
            "root": root, "functions": sorted(visited), "function_count": len(visited),
            "script_call_sites": sum(s["kind"] != "intrinsic" for s in bound_sites),
            "intrinsic_call_sites": sum(s["kind"] == "intrinsic" for s in bound_sites),
            "intrinsic_ids": sorted({s["target"] for s in bound_sites if s["kind"] == "intrinsic"}),
            "dynamic_action_sites": sum(a["function"] in visited and a["entry_reachable"] for a in actions),
        }
    ir = {
        "schema": 1, "format": "dos-black-gate-16bit", "sha256": inventory["sha256"],
        "instruction_columns": ["pc", "opcode", "operands", "nominal_pops", "nominal_pushes", "cfg_reachable"],
        "stack_effect_source": "Exult opcode metadata and Kitrinx nominal call arity; runtime object ABI unverified",
        "functions": list(functions.values()),
    }
    summary = {
        "schema": 1, "sha256": inventory["sha256"], "status": "decoded",
        "functions_decoded": len(functions), "code_bytes": sum(f["code_length"] for f in functions.values()),
        "instructions": sum(op_counts.values()), "distinct_opcodes": len(op_counts),
        "opcodes": {f"{i:02X}": {"name": schema[i].name, "occurrences": n} for i,n in sorted(op_counts.items())},
        "extern_entries": sum(len(f["externs"]) for f in functions.values()),
        "script_call_sites": sum(s["kind"] != "intrinsic" for f in functions.values() for s in f["call_sites"]),
        "distinct_intrinsics": len(intrinsic_counts), "intrinsic_call_sites": sum(intrinsic_counts.values()),
        "intrinsics": {f"{i:02X}": {"name": intrinsic_names.get(i), "sites": n} for i,n in sorted(intrinsic_counts.items())},
        "callgraph": reach, "diagnostics": diagnostics,
        "action_dispatch": {"site_counts": dict(sorted(Counter(a["dispatch"] for a in actions).items())),
                            "sites": actions, "action_array_commands": "not_decoded", "callback_targets": "unresolved"},
        "observed_runtime_invocations": None, "execution": "not_run", "lua_generation": "not_run",
    }
    return summary, ir


def _ucxt_agreement(output, raw, ir):
    """Compare ordered function IDs, PCs and raw instruction bytes, ignoring quoted data."""
    expected = {f["id"]: f for f in ir["functions"]}
    current = None
    seen = set()
    index = total = 0
    for line in output.splitlines():
        number = re.fullmatch(rb"\s*\.funcnumber\s+([0-9A-F]+)H\s*", line)
        if number:
            if current is not None and index != len(current["instructions"]):
                raise ValueError("ucxt omitted instructions")
            function = int(number[1], 16)
            if function not in expected or function in seen:
                raise ValueError("ucxt function set differs from the structural IR")
            seen.add(function)
            current, index = expected[function], 0
            continue
        row = re.match(rb"^([0-9A-F]+): ([0-9A-F]{2}(?: [0-9A-F]{2})*) *(?:\t|$)", line)
        if not row:
            continue
        if current is None or index >= len(current["instructions"]):
            raise ValueError("unexpected ucxt instruction")
        rows = current["instructions"]
        pc = rows[index][0]
        end = rows[index + 1][0] if index + 1 < len(rows) else current["code_length"]
        offset = current["code_offset"]
        if int(row[1], 16) != pc or bytes.fromhex(row[2].decode()) != raw[offset + pc:offset + end]:
            raise ValueError(f"ucxt disagrees at function {current['id']:04X}, source offset {offset + pc}")
        total += 1
        index += 1
    if set(expected) != seen or current is None or index != len(current["instructions"]):
        raise ValueError("incomplete ucxt disassembly")
    return total


def _kitrinx_root_agreement(output, fn):
    rows = {}
    for match in re.finditer(rb"^  ([\dA-F]+)  ([a-z_0-9]+)(.*)$", output, re.M):
        pc = int(match[1], 16)
        if pc in rows:
            raise ValueError("duplicate Kitrinx instruction address")
        rows[pc] = match[3]
    expected = {row[0] for row in fn["instructions"]}
    if expected != rows.keys():
        raise ValueError(f"Kitrinx instruction boundaries differ for {fn['id']:04X}")
    for pc, target in fn["branches"].items():
        branch = re.search(rb"->([\dA-F]+)", rows[pc])
        if branch is None or int(branch[1], 16) != target:
            raise ValueError(f"Kitrinx branch target differs at {fn['id']:04X}+{pc:04X}")
    for site in fn["call_sites"]:
        operand = rows[site["pc"]].split(b"[", 1)[0].strip()
        if site["kind"] == "extern":
            expected_operand = f"fn:{site['target']:04X}"
        elif site["kind"] == "intrinsic":
            expected_operand = f"{site['target']} {site['argc']}"
        else:
            expected_operand = str(site["target"])
        if operand.split() != expected_operand.encode().split():
            raise ValueError(f"Kitrinx call operand differs at {fn['id']:04X}+{site['pc']:04X}")
    return {"instructions": len(rows), "branch_targets": len(fn["branches"]), "call_sites": len(fn["call_sites"])}


def oracle_comparison(raw, usecode_file, installation, summary, ir):
    """Qualify the record layout separately from regenerating control flow."""
    tools = installation / "Tools"
    kit = tools / "Ultima7_Decomp-872a613c718abf3a40cf94533887171bec8cfb24" / "ultima7-usecode" / "build"
    exult = tools / "ExultTools" / "ucxt.exe"
    verify, dis, roundtrip = (kit / f"u7uc{name}.exe" for name in ("verify", "dis", "round"))
    tool_hashes = {exult: "df180aa93e70f773d2f5d069ff345bda2af52f91d1638efcdbdf3712a27d3909",
                   verify: "8016f239ba3b8e99ebd553830263c5c8485e438549bc40b3151931c8c58c49ef",
                   dis: "5a6d1a66f88b27c64f93a5e945b929c3522013f829978f227098e3d566a8af58",
                   roundtrip: "816a33a914031cd657974089302ea696ba63d636cc03206bee7fdab8fa3da23d"}
    for path, expected in tool_hashes.items():
        if _sha(path.read_bytes()) != expected:
            raise ValueError(f"unrecognized Usecode oracle binary {path.name}")

    def run(tool, *args, codes=(0,)):
        try:
            result = subprocess.run([tool, *args], capture_output=True, timeout=60)
        except subprocess.TimeoutExpired as exc:
            raise ValueError(f"{tool.name} timed out") from exc
        if result.returncode not in codes:
            raise ValueError(f"{tool.name} failed with exit code {result.returncode}")
        return result.stdout

    total = _ucxt_agreement(run(exult, "-fov", "-fa", "-ro", f"-i{usecode_file}", "-a"), raw, ir)
    verifier = run(verify, usecode_file)
    matched = re.search(rb"(\d+) instructions re-encoded byte-exactly", verifier)
    if matched is None or int(matched[1]) != total or total != summary["instructions"]:
        raise ValueError("Usecode instruction count differs across structural IR, ucxt and Kitrinx")
    roots = {}
    by_id = {fn["id"]: fn for fn in ir["functions"]}
    for name, target in ROOTS.items():
        roots[name] = _kitrinx_root_agreement(run(dis, usecode_file, f"{target:04X}"), by_id[target])
    layout = run(roundtrip, "--record", "--detail", usecode_file)
    generated = run(roundtrip, "--generate", "--detail", usecode_file, codes=(0, 1))
    pattern = rb"whole records regenerated byte for byte: (\d+) \((\d+) bytes\)"
    original_ok, generated_ok = re.search(pattern, layout), re.search(pattern, generated)
    if (not original_ok or not generated_ok or
            (int(original_ok[1]), int(original_ok[2])) != (len(by_id), len(raw))):
        raise ValueError("Kitrinx could not reproduce all records using the original layout")
    mismatches = [{"function": int(fid, 16), "regenerated_bytes": int(a), "original_bytes": int(b)}
                  for fid,a,b in re.findall(rb"([0-9A-F]{4}) produced (\d+) bytes, original has (\d+)", generated)]
    if int(generated_ok[1]) + len(mismatches) != len(by_id):
        raise ValueError("unaccounted Kitrinx structured-regeneration mismatch")
    return {
        "table_sha256": TABLE_HASHES, "binary_sha256": {p.name: h for p,h in tool_hashes.items()},
        "ucxt_raw_instructions_matching_by_function_pc_and_bytes": total,
        "kitrinx_instructions_reencoded": total, "kitrinx_opening_root_disassembly_agreement": roots,
        "kitrinx_original_layout_exact": int(original_ok[1]), "kitrinx_structured_layout_exact": int(generated_ok[1]),
        "structured_size_differences": mismatches, "gameplay_trace": "not_run",
    }


def produce_usecode(u7_root: Path, output_dir: Path, installation: Path) -> dict:
    """Write a private, deterministic static census plus original-bytecode IR."""
    u7_root, output_dir, installation = Path(u7_root), Path(output_dir), Path(installation)
    if output_dir.resolve().is_relative_to(u7_root.resolve()):
        raise ValueError("Usecode output must be outside the Ultima VII installation")
    static = next((d for d in u7_root.iterdir() if d.is_dir() and d.name.upper() == "STATIC"), None)
    file = next((p for p in static.iterdir() if p.name.upper() == "USECODE"), None) if static else None
    if file is None:
        raise ValueError("missing STATIC/USECODE")
    raw = file.read_bytes()
    schema, names = load_tables(installation / "Tools/ExultTools/data")
    summary, ir = analyze_usecode(raw, schema, names)
    summary["oracles"] = oracle_comparison(raw, file, installation, summary, ir)
    if file.read_bytes() != raw:
        raise ValueError("Usecode changed during oracle comparison")
    output_dir.mkdir(parents=True, exist_ok=True)
    for name, body in (("usecode.json", summary), ("usecode-ir.json", ir)):
        (output_dir / name).write_bytes((json.dumps(body, sort_keys=True, separators=(",", ":")) + "\n").encode())
    return summary
