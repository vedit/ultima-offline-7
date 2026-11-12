"""Extract a linked inventory from the original Trinsic new-game stream."""

import hashlib
import json
import struct
from collections import Counter
from pathlib import Path

from .u7 import seed_directory


MEMBER = "u7ireg64"
SUPERCHUNK = 0x64


def decode_member(data, tfa, absolute_offset, seed_hash, superchunk=SUPERCHUNK):
    """Parse an original DOS regional object stream from INITGAME.DAT.

    Exult Game_map::read_ireg_objects distinguishes hatchables and barges by
    shape class. A barge member is physically attached; it is not inventory.
    A nonzero type word on an ordinary container or barge opens a nested list.
    """
    if not 0 <= superchunk < 144:
        raise ValueError("Invalid IREG superchunk number")
    member = f"u7ireg{superchunk:02x}"
    if len(tfa) < 3 * 1024:
        raise ValueError("Truncated TFA.DAT shape class table")
    if len(seed_hash) != 64 or any(c not in "0123456789abcdef" for c in seed_hash):
        raise ValueError("Invalid seed fingerprint")
    objects, markers, stack = [], [], []
    next_order = Counter()
    pos = 0
    while pos < len(data):
        offset = pos
        length = data[pos]
        pos += 1
        parent = stack[-1] if stack else None
        parent_id = parent["id"] if parent else None
        if length in (0, 1):
            markers.append({"offset": offset, "tag": length, "parent": parent_id})
            if parent:
                stack.pop()
            continue
        if length == 2:
            if pos + 2 > len(data):
                raise ValueError(f"Truncated IREG index at byte {offset}")
            markers.append({"offset": offset, "tag": length, "parent": parent_id,
                            "index_word": int.from_bytes(data[pos:pos + 2], "little")})
            pos += 2
            continue
        if length not in (6, 12, 18):
            raise ValueError(f"Unsupported IREG length or control tag {length:#04x} at byte {offset}")
        if pos + length > len(data):
            raise ValueError(f"Truncated IREG record at byte {offset}")
        raw = data[pos:pos + length]
        pos += length
        x, y, shape_frame = struct.unpack_from("<BBH", raw)
        shape, frame = shape_frame & 1023, shape_frame >> 10
        shape_class = tfa[3 * shape + 1] & 15
        opens = False
        if length == 6 and shape_class in (0, 2, 3, 4, 5):
            kind = "simple"
        elif length == 12 and shape_class in (6, 7, 9, 11):
            kind = {6: "container", 7: "egg", 9: "barge", 11: "virtue_stone"}[shape_class]
            opens = kind in ("container", "barge") and any(raw[4:6])
        elif length == 18 and shape_class == 8:
            kind = "spellbook"
        else:
            raise ValueError(f"Unsupported IREG length {length} / class {shape_class} at byte {offset}")
        if parent and kind == "egg":
            # Exult handles eggs in the scene before it attempts container attachment.
            raise ValueError(f"Unqualified egg inside a nested list at byte {offset}")
        edge = ("world" if parent is None else
                "barge_member" if parent["kind"] == "barge" else "inventory")
        item = {
            "id": f"ireg:{seed_hash}:{member}:{offset}",
            "offset": offset, "archive_offset": absolute_offset + offset, "length": length,
            "payload_hex": raw.hex(), "tfa_class": shape_class, "kind": kind,
            "shape": shape, "frame": frame, "lift": raw[4 if length == 6 else 9] >> 4,
            "raw_xy": [x, y], "parent": parent_id, "edge": edge,
            "ordinal": next_order[parent_id], "depth": len(stack),
            "inventory_depth": (parent["inventory_depth"] if parent else 0) + (edge == "inventory"),
            "root": stack[0]["id"] if stack else None,
        }
        if kind == "simple":
            # A quantity or takeability flag may share this byte; retain it verbatim.
            item["quality_byte"] = raw[5]
        elif kind in ("container", "barge"):
            item["type_word"] = int.from_bytes(raw[4:6], "little")
            item["quality_byte"] = raw[7]
            item["flags_byte"] = raw[11]
        next_order[parent_id] += 1
        if edge in ("world", "barge_member"):
            item["world_xy"] = [superchunk % 12 * 256 + x, superchunk // 12 * 256 + y]
        if edge == "inventory":
            item["gump_xy"] = [x, y]
        objects.append(item)
        if opens:
            stack.append(item)
    if stack:
        raise ValueError(f"Unterminated IREG container opened at byte {stack[-1]['offset']}")
    return objects, markers


def produce_container(u7_root, output_dir):
    """Write one real containment witness; require an inventory child to exist."""
    root, out = Path(u7_root), Path(output_dir)
    if out.resolve().is_relative_to(root.resolve()):
        raise ValueError("Inventory output must be outside the U7 installation")
    static = root / "STATIC"
    seed = (static / "INITGAME.DAT").read_bytes()
    tfa = (static / "TFA.DAT").read_bytes()
    members = seed_directory(seed)
    if MEMBER not in members:
        raise ValueError("Missing initial Trinsic U7IREG64 member")
    slot, absolute_offset, size = members[MEMBER]
    seed_hash = hashlib.sha256(seed).hexdigest()
    objs, markers = decode_member(seed[absolute_offset:absolute_offset + size], tfa,
                                  absolute_offset, seed_hash)
    children = [o for o in objs if o["edge"] == "inventory"]
    if not children:
        raise ValueError("No positive inventory containment witness in initial Trinsic U7IREG64")
    # Prefer nested inventories; break ties by the earliest original record.
    deepest = max(children, key=lambda obj: obj["inventory_depth"])
    root_id = deepest["root"]
    witness = [o for o in objs if o["id"] == root_id or o["root"] == root_id]
    witness_ids = {o["id"] for o in witness}
    inventory_edges = sum(o["edge"] == "inventory" for o in witness)
    result = {
        "schema": 1, "kind": "initial-ireg-containment", "source_file": "STATIC/INITGAME.DAT",
        "seed_sha256": seed_hash, "tfa_sha256": hashlib.sha256(tfa).hexdigest(),
        "member": MEMBER, "slot": slot, "member_offset": absolute_offset, "member_size": size,
        "scanned_objects": len(objs), "scanned_markers": len(markers),
        "root_id": root_id, "witness_objects": len(witness),
        "max_inventory_depth": deepest["inventory_depth"], "inventory_edges": inventory_edges,
        "objects": witness, "markers": [m for m in markers if m["parent"] in witness_ids],
        "emitted_uo_objects": 0,
    }
    out.mkdir(parents=True, exist_ok=True)
    (out / "container.json").write_bytes(
        (json.dumps(result, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8"))
    return result
