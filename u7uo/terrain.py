"""Compile the flat ground around the Black Gate Avatar's starting position."""

import hashlib
import json
import struct
from collections import Counter
from pathlib import Path

from .u7 import flex_directory, seed_directory


WORLD_TILES = 3072
CHUNK_BYTES = 16 * 16 * 2
MAP_BYTES = 12 * 12 * CHUNK_BYTES
UO_BLOCK_BYTES = 4 + 8 * 8 * 3
UNRESOLVED_LAND = 0x1FA

# Presentation substitutions for flat land only. Each rule is checked against
# both installations before use. Frames remain available in the source map.
# The four UO variations within each material are selected by frame modulo four.
LAND_RULES = {
    24: ("cobblestone", "cobblestones", 0x03E9),
    146: ("grass", "grass", 0x0003),
    147: ("grass", "grass", 0x0003),
    148: ("grass", "grass", 0x0003),
}


def _child(parent, name):
    matches = [p for p in parent.iterdir() if p.name.casefold() == name.casefold()]
    if len(matches) != 1:
        raise ValueError(f"Expected one {name} in {parent}, found {len(matches)}")
    return matches[0]


class TerrainSource:
    """Retail U7MAP placement and U7CHUNKS shape words, little-endian."""

    def __init__(self, world, chunks):
        if len(world) != MAP_BYTES:
            raise ValueError(f"U7MAP must contain {MAP_BYTES} bytes")
        if not chunks or len(chunks) % CHUNK_BYTES:
            raise ValueError("U7CHUNKS must contain whole 16 by 16 chunk definitions")
        count = len(chunks) // CHUNK_BYTES
        for index, (chunk,) in enumerate(struct.iter_unpack("<H", world)):
            if chunk >= count:
                raise ValueError(f"U7MAP byte {index * 2} references missing chunk {chunk}")
        self.world = world
        self.chunks = chunks

    def tile(self, world_x, world_y):
        if not (0 <= world_x < WORLD_TILES and 0 <= world_y < WORLD_TILES):
            raise ValueError("Tile outside the 3072 by 3072 source world")
        super_x, within_super_x = divmod(world_x, 256)
        super_y, within_super_y = divmod(world_y, 256)
        chunk_x, tile_x = divmod(within_super_x, 16)
        chunk_y, tile_y = divmod(within_super_y, 16)
        super_index = super_y * 12 + super_x
        map_offset = ((super_index * 256) + chunk_y * 16 + chunk_x) * 2
        chunk_id = struct.unpack_from("<H", self.world, map_offset)[0]
        chunks_offset = chunk_id * CHUNK_BYTES + (tile_y * 16 + tile_x) * 2
        word = struct.unpack_from("<H", self.chunks, chunks_offset)[0]
        return {
            "chunk_id": chunk_id,
            "map_offset": map_offset,
            "chunks_offset": chunks_offset,
            "shape": word & 0x03FF,
            "frame": word >> 10,
        }


def encode_land_mul(width, height, land):
    """Encode a row-major list of (land ID, signed Z) pairs as UO map blocks."""
    if width <= 0 or height <= 0 or width % 8 or height % 8:
        raise ValueError("UO dimensions must be positive multiples of eight")
    if len(land) != width * height:
        raise ValueError("Land cell count does not match UO dimensions")
    result = bytearray()
    block = struct.Struct("<Hb")
    for left in range(0, width, 8):
        for top in range(0, height, 8):
            result.extend(b"\0" * 4)
            for y in range(top, top + 8):
                for x in range(left, left + 8):
                    tile_id, z = land[y * width + x]
                    if not (0 <= tile_id < 0x4000 and -128 <= z <= 127):
                        raise ValueError(f"Invalid land ID or elevation at ({x}, {y})")
                    result.extend(block.pack(tile_id, z))
    return bytes(result)


def _avatar_seed(data):
    members = seed_directory(data)
    if "npc.dat" not in members:
        raise ValueError("INITGAME.DAT lacks npc.dat")
    slot, offset, size = members["npc.dat"]
    if size < 16 or not struct.unpack_from("<H", data, offset)[0]:
        raise ValueError("Missing initial Avatar record in npc.dat")
    record = offset + 4  # two uint16 population counts precede NPC zero
    x, y = data[record : record + 2]
    superchunk = data[record + 6]
    lift = data[record + 9] >> 4
    if superchunk >= 144:
        raise ValueError(f"Invalid Avatar superchunk {superchunk}")
    position = [superchunk % 12 * 256 + x, superchunk // 12 * 256 + y, lift]
    return {"member": "npc.dat", "slot": slot, "record_offset": record, "position": position}


def fixed_inventory(data, superchunk, seed_hash):
    """Decode DOS four-byte IFIX records, retaining the FLEX slot and record order."""
    if not 0 <= superchunk < 144:
        raise ValueError("Invalid IFIX superchunk number")
    if len(seed_hash) != 64 or any(c not in "0123456789abcdef" for c in seed_hash):
        raise ValueError("Expected a lowercase SHA-256 source seed fingerprint")
    directory = flex_directory(data)
    if len(directory) != 256:
        raise ValueError("Expected one IFIX directory slot per chunk in the superchunk")
    if struct.unpack_from("<I", data, 88)[0] != 0xCC:
        raise ValueError("Unsupported IFIX archive version")
    filename = f"U7IFIX{superchunk:02X}"
    records = []
    for slot, (start, size) in enumerate(directory):
        if size % 4:
            raise ValueError(f"{filename} slot {slot} contains a partial fixed-object record")
        left = (superchunk % 12) * 256 + (slot % 16) * 16
        top = (superchunk // 12) * 256 + (slot // 16) * 16
        for ordinal in range(size // 4):
            offset = start + ordinal * 4
            xy, lift, value = struct.unpack_from("<BBH", data, offset)
            records.append({
                "id": f"ifix:{seed_hash}:{superchunk:02x}:{slot:02x}:{ordinal}",
                "slot": slot, "ordinal": ordinal, "offset": offset,
                "x": left + (xy >> 4), "y": top + (xy & 15), "lift": lift,
                "shape": value & 0x03FF, "frame": value >> 10,
            })
    return {
        "schema": 1, "source_file": filename,
        "source_sha256": hashlib.sha256(data).hexdigest(), "seed_sha256": seed_hash,
        "superchunk": superchunk, "slots": len(directory),
        "occupied_slots": sum(size > 0 for _, size in directory),
        "record_count": len(records), "objects": records,
        "status": "source-inventory", "emitted_statics": 0,
    }


def _resolve_rule(shape, text, directory, tiledata, rules=LAND_RULES):
    rule = rules.get(shape)
    if rule is None:
        raise ValueError(f"Unmapped source shape {shape} in Trinsic ground proof")
    source_name, target_name, first_id = rule
    if shape >= len(directory):
        raise ValueError(f"TEXT.FLX lacks shape {shape}")
    offset, size = directory[shape]
    label = text[offset : offset + size].rstrip(b"\0")
    if label.lower() != source_name.encode("ascii"):
        raise ValueError(f"Source name mismatch for shape {shape}, expected {source_name}")
    # ModernUO and ClassicUO read 64-bit land flags in the provisioned client.
    # Only IDs >0 occur in these rules. Both loaders agree on their offsets.
    variants = 1 if shape == 48 else 4
    expected_flags = 0x50 if shape == 48 else 0
    for land_id in range(first_id, first_id + variants):
        group, within_group = divmod(land_id, 32)
        offset = group * (4 + 32 * 30) + 4 + within_group * 30
        flags, _, name = struct.unpack_from("<QH20s", tiledata, offset)
        if name.split(b"\0", 1)[0].lower() != target_name.encode("ascii") or flags != expected_flags:
            raise ValueError(f"UO land {land_id:#06x} differs from expected {target_name} flags {expected_flags:#x}")
    return {"source_label": source_name, "target_label": target_name,
            "first_land_id": first_id, "variants": variants}


def produce_terrain(u7_root, uo_root, output_dir):
    """Emit a private 16 by 16 ground sample suitable for both native MUL readers.

    The caller owns staging and publication of the resulting directory.
    No static or mutable objects are included in this ground-only proof.
    """
    u7_root, uo_root, out = map(Path, (u7_root, uo_root, output_dir))
    for source_root in (u7_root, uo_root):
        if out.resolve().is_relative_to(source_root.resolve()):
            raise ValueError("Terrain output must be outside the input installations")
    static = _child(u7_root, "STATIC")
    sources = {name: _child(static, name).read_bytes()
               for name in ("U7MAP", "U7CHUNKS", "INITGAME.DAT", "TEXT.FLX")}
    terrain = TerrainSource(sources["U7MAP"], sources["U7CHUNKS"])
    seed = _avatar_seed(sources["INITGAME.DAT"])
    avatar_x, avatar_y, avatar_z = seed["position"]
    if (avatar_x // 16, avatar_y // 16, avatar_z) != (67, 138, 0):
        raise ValueError(f"Initial Avatar {seed['position']} is outside the supported Trinsic start chunk")

    tiledata = _child(uo_root, "tiledata.mul").read_bytes()
    if len(tiledata) != 3188736:
        raise ValueError("Ground proof requires the supported 64-bit UO Classic tiledata layout")
    sources["tiledata.mul"] = tiledata
    text = sources["TEXT.FLX"]
    directory = flex_directory(text)
    width = height = 16
    left, top = avatar_x // 16 * 16, avatar_y // 16 * 16
    superchunk = avatar_y // 256 * 12 + avatar_x // 256
    ifix_name = f"U7IFIX{superchunk:02X}"
    sources[ifix_name] = _child(static, ifix_name).read_bytes()
    hashes = {name: hashlib.sha256(data).hexdigest() for name, data in sources.items()}
    fixed = fixed_inventory(sources[ifix_name], superchunk, hashes["INITGAME.DAT"])
    fixed_in_sample = sum(left <= obj["x"] < left + width and top <= obj["y"] < top + height
                          for obj in fixed["objects"])
    cells, material_rules = [], {}
    counts = Counter()
    for y in range(height):
        for x in range(width):
            tile = terrain.tile(left + x, top + y)
            shape = tile["shape"]
            if shape not in material_rules:
                material_rules[shape] = _resolve_rule(shape, text, directory, tiledata)
            variant = tile["frame"] % 4
            land_id = material_rules[shape]["first_land_id"] + variant
            cells.append({"x": x, "y": y, **tile, "land_id": land_id, "z": 0})
            counts[shape] += 1

    mul = encode_land_mul(width, height, [(cell["land_id"], cell["z"]) for cell in cells])
    blocks = width * height // 64
    files = {"map0.mul": mul, "staidx0.mul": struct.pack("<iii", -1, 0, 0) * blocks,
             "statics0.mul": b"", "fixed.json": _json_bytes(fixed)}
    report = {
        "schema": 1, "kind": "trinsic-ground-proof", "width": width, "height": height,
        "source_origin": [left, top], "avatar": seed, "blocks": blocks,
        "cell_count": len(cells), "source_chunk_placements": len(sources["U7MAP"]) // 2,
        "source_chunk_definitions": len(sources["U7CHUNKS"]) // CHUNK_BYTES,
        "distinct_source_shape_frames": len({(c["shape"], c["frame"]) for c in cells}),
        "rules": {str(shape): {**material_rules[shape], "occurrences": counts[shape]}
                  for shape in sorted(material_rules)},
        "fixed": {"file": "fixed.json", "superchunk_records": fixed["record_count"],
                  "records_in_ground_sample": fixed_in_sample, "emitted_statics": 0},
        "transform": "target (x,y) = source (x,y) - source_origin; no rotation",
        "scope": "Flat land appearance only. Z=0 is the ground plane. Statics, objects, scripts, collision and gameplay are unqualified.",
        "source_sha256": hashes,
        "output_sha256": {name: hashlib.sha256(data).hexdigest() for name, data in files.items()},
        "cells": cells,
    }
    out.mkdir(parents=True, exist_ok=True)
    for name, data in files.items():
        (out / name).write_bytes(data)
    (out / "terrain.json").write_bytes(_json_bytes(report))
    return report


def _json_bytes(data):
    return (json.dumps(data, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")
