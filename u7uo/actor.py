"""Read Black Gate's initial NPC table and export Finnigan's source record."""

import hashlib
import json
import struct
from pathlib import Path

from .u7 import seed_directory, usecode_inventory


FINNIGAN_SLOT = 12
HEADER_SIZE = 117
# Kitrinx's reconstructed Black Gate LoadNpcs, ReadItemTree, typeflag and NpcBuffer.
REFERENCE = "https://github.com/Kitrinx/Ultima7_Decomp/tree/872a613c718abf3a40cf94533887171bec8cfb24/ultima7-portable/Black%20Gate/game"
INVENTORY_RECORD_SIZES = (6, 6, 6, 6, 6, 6, 12, 12, 18, 12, 12, 12, 12, 12, 6, 6)
HAS_CONTENTS = {6, 12, 13}


def _walk_inventory(data, offset, tfa, items=None):
    # Each nested list retains its original order. A root parent is the actor.
    parents = [None]
    ordinals = [0]
    count = 0
    while parents:
        if offset >= len(data):
            raise ValueError("unterminated NPC inventory")
        length = data[offset]
        record = offset
        offset += 1
        if length in (0, 1):
            parents.pop()
            ordinals.pop()
            continue
        if length not in (6, 12, 18) or offset + length > len(data):
            raise ValueError(f"invalid NPC inventory record at byte {offset - 1}")
        shape_frame = struct.unpack_from("<H", data, offset + 2)[0]
        shape = shape_frame & 0x3FF
        shape_class = tfa[3 * shape + 1] & 15
        if length != INVENTORY_RECORD_SIZES[shape_class]:
            raise ValueError(f"NPC inventory length contradicts TFA shape {shape} at {offset - 1}")
        if items is not None:
            items.append({"record_offset": record, "length": length, "parent_offset": parents[-1],
                          "ordinal": ordinals[-1], "depth": len(parents), "shape": shape,
                          "frame": shape_frame >> 10, "tfa_class": shape_class,
                          "raw_xy": list(data[offset:offset+2]), "payload_hex": data[offset:offset+length].hex()})
        ordinals[-1] += 1
        if shape_class in HAS_CONTENTS and struct.unpack_from("<H", data, offset + 4)[0]:
            parents.append(record)
            ordinals.append(0)
        offset += length
        count += 1
    return offset, count


def actor_table(data, tfa, *, include_inventory=False):
    if len(data) < 4 or len(tfa) < 3 * 1024:
        raise ValueError("truncated NPC header or TFA shape table")
    normal, extra = struct.unpack_from("<HH", data)
    total = normal + extra
    if len(data) < 4 + total * HEADER_SIZE:
        raise ValueError("incomplete NPC table")
    offset = 4
    rows = []
    inventory_count = 0
    for index in range(total):
        start = offset
        if start + HEADER_SIZE > len(data):
            raise ValueError(f"NPC slot {index} has a truncated header")
        x, y, shape_frame, contents, region = struct.unpack_from("<BBHHB", data, start)
        usecode_lift = struct.unpack_from("<H", data, start + 8)[0]
        reference = struct.unpack_from("<H", data, start + 14)[0]
        shape = shape_frame & 0x3FF
        shape_class = tfa[shape * 3 + 1] & 15
        offset += HEADER_SIZE
        count = 0
        items = [] if include_inventory else None
        if reference and shape and shape_class in HAS_CONTENTS and contents:
            offset, count = _walk_inventory(data, offset, tfa, items)
            inventory_count += count
        row = {"npc_slot": index, "record_offset": start, "record_length": offset - start,
               "inventory_records": count, "reference": reference, "placed": bool(reference and shape)}
        if items is not None:
            row["inventory"] = items
        if row["placed"]:
            if region >= 144:
                raise ValueError(f"NPC slot {index} has invalid region {region}")
            name = data[start + 101:start + 117].split(b"\x00", 1)[0].decode("cp437")
            lift = usecode_lift >> 12
            row.update({
                "name": name, "header_length": HEADER_SIZE,
                "shape": shape, "frame": shape_frame >> 10, "lift": lift, "superchunk": region,
                "source_position": [(region % 12) * 256 + x, (region // 12) * 256 + y, lift],
                "function_id": usecode_lift & 0xFFF, "face": data[start + 29],
                "header_sha256": hashlib.sha256(data[start:start + HEADER_SIZE]).hexdigest(),
            })
        rows.append(row)
    if offset != len(data):
        raise ValueError(f"unconsumed NPC bytes after {total} declared slots")
    table = {
        "normal_slots": normal, "extra_slots": extra, "records_indexed": total, "bytes_consumed": offset,
        "inventory_records_indexed": inventory_count,
    }
    return table, rows


def read_actor(data, tfa, slot):
    table, rows = actor_table(data, tfa)
    if not 0 <= slot < table["normal_slots"] or not rows[slot]["placed"]:
        raise ValueError(f"NPC slot {slot} has no placed actor")
    return {**rows[slot], "table": table}


def produce_actor(u7_root: Path, out: Path) -> dict:
    if out.resolve().is_relative_to(u7_root.resolve()):
        raise ValueError("NPC output must be outside the Ultima VII installation")
    static = next((p for p in u7_root.iterdir() if p.name.upper() == "STATIC" and p.is_dir()), None)
    if static is None:
        raise ValueError("missing STATIC directory")
    paths = {p.name.upper(): p for p in static.iterdir()}
    if not {"INITGAME.DAT", "TFA.DAT", "USECODE"}.issubset(paths):
        raise ValueError("NPC inspection requires INITGAME.DAT, TFA.DAT and USECODE")
    archive = paths["INITGAME.DAT"].read_bytes()
    members = seed_directory(archive)
    if "npc.dat" not in members:
        raise ValueError("INITGAME.DAT lacks npc.dat")
    member_slot, member_offset, size = members["npc.dat"]
    tfa = paths["TFA.DAT"].read_bytes()
    member = archive[member_offset:member_offset + size]
    actor = read_actor(member, tfa, FINNIGAN_SLOT)
    if actor["name"] != "Finnigan" or actor["face"] != FINNIGAN_SLOT or actor["function_id"] != 0x40C:
        raise ValueError("NPC slot 12 does not match the Finnigan name, face and Usecode binding")
    corpus = usecode_inventory(paths["USECODE"].read_bytes())
    binding = next((row for row in corpus["records"] if row["id"] == actor["function_id"]), None)
    if binding is None:
        raise ValueError("Finnigan's source function is missing from STATIC/USECODE")
    seed_hash = hashlib.sha256(archive).hexdigest()
    actor.update({
        "schema": 1, "id": f"npc:{seed_hash}:npc.dat:{FINNIGAN_SLOT}", "source": "STATIC/INITGAME.DAT",
        "seed_sha256": seed_hash, "member": "npc.dat", "member_slot": member_slot,
        "member_offset": member_offset, "member_bytes": size,
        "member_sha256": hashlib.sha256(member).hexdigest(),
        "file_offset": member_offset + actor["record_offset"], "tfa_sha256": hashlib.sha256(tfa).hexdigest(),
        "usecode_record_offset": binding["offset"], "usecode_sha256": corpus["sha256"],
        "source_reference": REFERENCE, "emitted_uo_mobiles": 0,
    })
    out.mkdir(parents=True, exist_ok=True)
    (out / "actor.json").write_bytes((json.dumps(actor, sort_keys=True, indent=2) + "\n").encode())
    return actor
