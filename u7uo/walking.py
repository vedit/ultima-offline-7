"""Compile the street joining the original Avatar and Finnigan in Trinsic."""

import hashlib
import struct
from collections import Counter, defaultdict, deque
from pathlib import Path

from .actor import read_actor
from .containers import decode_member
from .terrain import (LAND_RULES, TerrainSource, _avatar_seed, _child, _json_bytes,
                      _resolve_rule, encode_land_mul, fixed_inventory)
from .u7 import flex_directory, seed_directory, usecode_inventory


# The western block includes the arcade pillars. The eastern block includes Johnson,
# who participates in the opening's original radius-40 NPC query.
ORIGIN = (944, 2112)
WIDTH, HEIGHT = 168, 160
GROUND = {**LAND_RULES, 18: ("tile", "flagstone", 0x201), 21: ("stone floor", "flagstone", 0x201),
          27: ("carpet", "flagstone", 0x201), 35: ("grass", "grass", 3),
          149: ("mud", "dirt", 0x079), 17: ("planking", "planks", 0x296),
          23: ("dirt", "dirt", 0x079), 46: ("rocky grass", "grass", 3),
          10: ("sand", "sand", 0x16), 47: ("carpet", "flagstone", 0x201), 48: ("ethereal void", "void!!!!!!", 1),
          0: ("carpet", "flagstone", 0x201), 4: ("grass", "grass", 3),
          **{s: ("sandy grass", "grass", 3) for s in (118, 119, 120, 121, 122, 124, 130)},
          **{s: ("grassy mud", "dirt", 0x079) for s in (134, 135, 136, 137, 138, 139, 140, 141, 144, 145)}}
# U7 shape -> U7 label, UO art, UO label, required flag, UO tile height.
# Carpet uses separate UO art over flagstone. Walls and pillars fill their
# original TFA footprint. Heights here compare game data, not sprite pixels.
STATIC_RULES = {
    27: ("carpet", 0x0AC9, "carpet", 0x200, 0),
    253: ("wall", 0x001B, "stone wall", 0x40, 20),
    348: ("wall", 0x001B, "stone wall", 0x40, 20),
    425: ("wall", 0x001B, "stone wall", 0x40, 20),
    453: ("tree", 0x0CCA, "tree", 0x40, 20),
    908: ("tile roof", 0x05B3, "tile roof", 0x10000000, 3),
    920: ("pillar", 0x00DB, "stone pillar", 0x40, 20),
    **{s: ("wall", 0x0006, "wooden wall", 0x40, 20) for s in (344, 345, 346, 349, 355, 359, 362, 371, 497)},
    **{s: ("wood roof", 0x05C2, "wooden shingle", 0x10000000, 3) for s in (170, 174, 176, 891, 956)},
    **{s: ("window", 0x000E, "window", 0x40, 20) for s in (438, 732)},
    369: ("floor", 0x051A, "stone pavers", 0x200, 0),
    47: ("carpet", 0x0AC9, "carpet", 0x200, 0),
    0: ("carpet", 0x0AC9, "carpet", 0x200, 0),
    314: ("weeds", 0x0CC7, "weed", 0x4000, 0),
    331: ("rock", 0x1771, "rock", 0, 1),
    **{s: ("stairs", 0x07B7, "cave steps", 0x600, 8) for s in (385, 386, 387, 973, 974)},
    **{s: ("rug", 0x0AB3, "rug", 0x200, 0) for s in (188, 483)},
    **{s: ("floor", 0x051A, "stone pavers", 0x200, 0) for s in (367, 368, 370, 1014)},
    **{s: ("wall", 0x001B, "stone wall", 0x40, 20) for s in (358, 374, 899, 904, 909, 910)},
    718: ("pedestal", 0x1F2A, "pedestal", 0x40, 8),
    **{s: ("pillar", 0x00DB, "stone pillar", 0x40, 20) for s in (687, 913)},
    **{s: ("wall", 0x001B, "stone wall", 0x40, 20) for s in (273, 308)},
    **{s: ("tile roof", 0x05B3, "tile roof", 0x10000000, 3) for s in (156, 966)},
    **{s: ("slate roof", 0x0595, "slate roof", 0x10000000, 3) for s in (165, 166, 167, 962, 963)},
    879: ("wall", 0x001B, "stone wall", 0x40, 20),
    **{shape: ("fortress", 0x001B, "stone wall", 0x40, 20) for shape in (191, 192, 260, 263, 352)},
    **{shape: ("crenellations", 0x0072, "battlement", 0x40, 20) for shape in (852, 878, 896, 901, 903)},
}
INTERACTIVE_FIXED_RULES = {854: ("statue", 0x43B8, "stone statue", 0x40, 20)}


def to_local(x, y):
    return x - ORIGIN[0], y - ORIGIN[1]


def to_world(x, y):
    return x + ORIGIN[0], y + ORIGIN[1]


def inside(x, y):
    return 0 <= x < WIDTH and 0 <= y < HEIGHT


def encode_statics(width, height, objects):
    if width <= 0 or height <= 0 or width % 8 or height % 8:
        raise ValueError("Invalid static facet dimensions")
    blocks = defaultdict(bytearray)
    for obj in objects:
        x, y = obj["x"], obj["y"]
        if not (0 <= x < width and 0 <= y < height and 0 <= obj["id"] <= 65535
                and -128 <= obj["z"] <= 127 and 0 <= obj["hue"] <= 65535):
            raise ValueError("Static outside the facet or UO value range")
        block = (x // 8) * (height // 8) + y // 8
        blocks[block].extend(struct.pack("<HBBbH", obj["id"], x % 8, y % 8, obj["z"], obj["hue"]))
    index, data = bytearray(), bytearray()
    for i in range(width * height // 64):
        chunk = blocks.get(i, b"")
        if len(chunk) > 1024 * 7:
            raise ValueError(f"ClassicUO static limit exceeded in block {i}")
        index.extend(struct.pack("<iii", len(data) if chunk else -1, len(chunk), 0))
        data.extend(chunk)
    return bytes(index), bytes(data)


def _flat_neighbor(source, x, y):
    # Exult objs/chunkter.cc searches nearby flat shapes within the source
    # chunk to fill an unpainted square under a non-flat shape. Retain donor
    # provenance so this visual substitution can be distinguished from U7MAP.
    xmin, ymin = x // 16 * 16, y // 16 * 16
    nearby = [(x + dx, y + dy) for dy in (-1, 0, 1) for dx in (-1, 0, 1)
              if xmin <= x + dx < xmin + 16 and ymin < y + dy < ymin + 16]
    for ax, ay in nearby + [(xmin + i % 16, ymin + i // 16) for i in range(256)]:
        donor = source.tile(ax, ay)
        if donor["shape"] in GROUND:
            return donor, [ax, ay]
    raise ValueError(f"No qualified ground material beneath source object at ({x},{y})")


def _static_material(shape, text, names, tiledata, rules=STATIC_RULES):
    rule = rules.get(shape)
    if rule is None:
        raise ValueError(f"No route static mapping for shape {shape}")
    label, art, target, required, expected_height = rule
    offset, size = names[shape]
    if text[offset:offset + size].rstrip(b"\0").lower() != label.encode():
        raise ValueError(f"Source material name changed for static shape {shape}")
    # 512 land groups followed by 32-record groups of 41-byte static records.
    offset = 512 * 964 + (art // 32) * 1316 + 4 + (art % 32) * 41
    flags = struct.unpack_from("<Q", tiledata, offset)[0]
    height = tiledata[offset + 20]
    name = tiledata[offset + 21:offset + 41].split(b"\0", 1)[0]
    if name != target.encode() or height != expected_height or (flags & required != required if required else flags != 0):
        raise ValueError(f"UO static art {art:#06x} differs from expected {target}")
    return {"id": art, "name": target, "flags": flags, "height": height}


def investigation_items(records, text, names, weight_volume, tiledata):
    """Map the investigated objects by source shape/frame, retaining each IREG identity."""
    items = []
    for obj in records:
        shape, frame = obj["shape"], obj["frame"]
        if obj["edge"] != "world" or obj["kind"] != "simple":
            continue
        if (shape, frame) == (641, 0):
            original, art, target, display = "/key//s", 0x100F, "gold key", "key"
        elif (shape, frame) == (810, 2):
            original, art, target, display = "bucket", 0x14E0, "bucket", "bloody bucket"
        elif (shape, frame) == (867, 0):
            original, art, target, display = "victim", 0x1D8D, "body", "victim"
        elif shape == 912 and frame in (0, 1, 2, 3, 24, 25):
            original, art, target, display = "blood", 0x122A + frame % 4, "blood", "blood"
        else:
            continue
        offset, size = names[shape]
        entry = 512 * 964 + art // 32 * 1316 + 4 + art % 32 * 41
        if (text[offset:offset+size].rstrip(b"\0") != original.encode()
                or tiledata[entry+21:entry+41].split(b"\0", 1)[0] != target.encode()):
            raise ValueError(f"Unexpected investigation art binding for source {shape}/{frame}")
        items.append({**obj, "source_name": original, "uo_art": art, "uo_name": target,
                      "display_name": display, "movable": weight_volume[shape * 2] != 0,
                      "tiledata_offset": entry})
    return items


def world_component_positions(obj, tfa, material):
    shape = obj["shape"]
    physical, shape_class, footprint = tfa[shape * 3:shape * 3 + 3]
    dx, dy = (footprint & 7) + 1, ((footprint >> 3) & 7) + 1
    if obj["frame"] & 32 and obj["family"] in ("IFIX", "IREG"):
        dx, dy = dy, dx
    if obj["family"] == "IFIX" and (shape_class & 15) != 14:
        raise ValueError(f"IFIX shape {shape} is not a building-class fixture")
    if shape == 920 and (physical >> 5, material["height"]) != (5, 20):
        raise ValueError("Pillar no longer calibrates the five-lift / twenty-Z height scale")
    x, y = obj["x"], obj["y"]
    z = obj["lift"] * 4
    if obj["family"] == "IREG" and shape in (385, 386, 387, 973, 974):
        # UO's bridge collision stands halfway up an eight-unit native tread.
        z += (physical >> 5) * 4 - material["height"] // 2
    elif obj["family"] == "IFIX" and shape in (367, 368, 369, 370, 1014):
        # The UO paver is a zero-height surface. U7 stands on top of the slab.
        z += (physical >> 5) * 4
    for row in range(dy):
        for col in range(dx):
            yield x-col, y-row, z  # U7 anchors the southeast corner.


def _components(obj, tfa, material):
    result = []
    for wx,wy,z in world_component_positions(obj,tfa,material):
        tx,ty = to_local(wx,wy)
        if inside(tx,ty):
            result.append({"id":material["id"],"x":tx,"y":ty,"z":z,"hue":0,"source_id":obj["id"]})
    return result


def _find_route(start, end, blocked):
    if start in blocked or end in blocked:
        raise ValueError("A source endpoint is blocked on the walking profile")
    previous = {start: None}
    todo = deque([start])
    while todo:
        x, y = todo.popleft()
        if (x, y) == end:
            route = []
            step = end
            while step is not None:
                route.append(list(step))
                step = previous[step]
            return route[::-1]
        for dx, dy in ((-1, 0), (0, 1), (1, 0), (0, -1)):
            dest = (x + dx, y + dy)
            if inside(*dest) and dest not in blocked and dest not in previous:
                previous[dest] = (x, y)
                todo.append(dest)
    raise ValueError("No cardinal path between source endpoints on walking profile")


def produce_walking_area(u7_root, uo_root, output_dir):
    u7, uo, out = map(Path, (u7_root, uo_root, output_dir))
    if any(out.resolve().is_relative_to(p.resolve()) for p in (u7, uo)):
        raise ValueError("Walking output must be separate from the game installations")
    static = _child(u7, "STATIC")
    regions = [12 * sy + sx for sy in range(ORIGIN[1] // 256, (ORIGIN[1]+HEIGHT-1) // 256 + 1)
               for sx in range(ORIGIN[0] // 256, (ORIGIN[0]+WIDTH-1) // 256 + 1)]
    files = {n: _child(static, n).read_bytes() for n in (
        "U7MAP", "U7CHUNKS", "INITGAME.DAT", "TFA.DAT", "WGTVOL.DAT", "TEXT.FLX", "USECODE",
        *(f"U7IFIX{region:02X}" for region in regions))}
    files["tiledata.mul"] = tiledata = _child(uo, "tiledata.mul").read_bytes()
    if len(tiledata) != 3188736:
        raise ValueError("Walking proof requires the supported 64-bit UO tiledata layout")
    hashes = {n: hashlib.sha256(v).hexdigest() for n, v in files.items()}
    seed, tfa, text = files["INITGAME.DAT"], files["TFA.DAT"], files["TEXT.FLX"]
    seed_hash = hashes["INITGAME.DAT"]
    names = flex_directory(text)
    members = seed_directory(seed)
    _, offset, size = members["npc.dat"]
    avatar = _avatar_seed(seed)["position"]
    actor = read_actor(seed[offset:offset + size], tfa, 12)
    finnigan = actor["source_position"]
    if (actor["function_id"] != 0x40C or actor["name"] != "Finnigan" or
            any(not inside(*to_local(*p[:2])) or p[2] != 0 for p in (avatar, finnigan))):
        raise ValueError("Unqualified Trinsic walking endpoints")

    live_records, fixtures = [], []
    for region in regions:
        member = f"u7ireg{region:02x}"
        _, offset, size = members[member]
        movable, _ = decode_member(seed[offset:offset + size], tfa, offset, seed_hash, region)
        live_records.extend({**o, "member": member} for o in movable
                            if "world_xy" in o and inside(*to_local(*o["world_xy"])))
        filename = f"U7IFIX{region:02X}"
        fixed = fixed_inventory(files[filename], region, seed_hash)
        fixtures.extend({**o, "family": "IFIX", "file": filename} for o in fixed["objects"]
                        if inside(*to_local(o["x"], o["y"])))
    clues = investigation_items(live_records, text, names, files["WGTVOL.DAT"], tiledata)
    clue_ids = {o["id"] for o in clues}
    stairs = [dict(o, family="IREG", x=o["world_xy"][0], y=o["world_xy"][1]) for o in live_records
              if o["edge"] == "world" and o["shape"] in (385, 386, 387, 973, 974)]
    fixtures.extend(stairs)
    stair_ids = {o["id"] for o in stairs}
    source = TerrainSource(files["U7MAP"], files["U7CHUNKS"])
    cells, land_rules = [], {}
    for y in range(HEIGHT):
        for x in range(WIDTH):
            wx, wy = to_world(x, y)
            tile = source.tile(wx, wy)
            material, donor = tile, None
            shape = tile["shape"]
            if shape in STATIC_RULES:
                fixtures.append({**tile, "family": "U7CHUNKS", "id": f"terrain:{seed_hash}:{wx}:{wy}",
                                 "x": wx, "y": wy, "lift": 0})
            if shape not in GROUND:
                if shape not in STATIC_RULES:
                    raise ValueError(f"Unmapped terrain shape {shape} at ({wx},{wy})")
                material, donor = _flat_neighbor(source, wx, wy)
            land_shape = material["shape"]
            if land_shape not in land_rules:
                land_rules[land_shape] = _resolve_rule(land_shape, text, names, tiledata, GROUND)
            land_id = land_rules[land_shape]["first_land_id"] + material["frame"] % land_rules[land_shape]["variants"]
            cell = {**tile, "x": x, "y": y, "land_id": land_id, "z": 0}
            if donor:
                cell["underlay_source_xy"] = donor
            cells.append(cell)

    bound_shapes = {entry["id"] for entry in usecode_inventory(files["USECODE"])["records"]}
    static_rules, statics, interactive_fixed = {}, [], []
    for obj in fixtures:
        shape = obj["shape"]
        if shape in bound_shapes:
            if obj["family"] == "IFIX" and shape in INTERACTIVE_FIXED_RULES:
                material = _static_material(shape, text, names, tiledata, INTERACTIVE_FIXED_RULES)
                x, y = to_local(obj["x"], obj["y"])
                interactive_fixed.append({**obj, "material": material, "function_id": shape,
                                          "staged_land_id": cells[y*WIDTH+x]["land_id"]})
                continue
            raise ValueError(f"Refusing to bake a shape-specific Usecode binding for {shape}")
        if shape not in static_rules:
            static_rules[shape] = _static_material(shape, text, names, tiledata)
        statics.extend(_components(obj, tfa, static_rules[shape]))
    by_id = {obj["id"]: obj for obj in fixtures}
    blocked = {(obj["x"], obj["y"]) for obj in statics if obj["z"] == 0 and
               static_rules[by_id[obj["source_id"]]["shape"]]["flags"] & 0x40}
    blocked.update((c["x"], c["y"]) for c in cells if c["land_id"] == 1)
    # Keep the route clear of all source IREG anchors, including deferred
    # scripted encounters and signs. Their interactions are not baked as art.
    blocked.update(to_local(*obj["world_xy"]) for obj in live_records)
    route = _find_route(to_local(*avatar[:2]), to_local(*finnigan[:2]), blocked)
    anchors = {o["id"]: o for o in fixtures if o["family"] == "IFIX" and o["shape"] == 920}
    if not anchors or not any(s["source_id"] in anchors for s in statics):
        raise ValueError("No qualified source IFIX pillar placement")
    for pos in route:
        if tuple(pos) != to_local(*to_world(*pos)):
            raise ValueError("Route coordinate round trip failed")
    index, data = encode_statics(WIDTH, HEIGHT, statics)
    files_out = {"map0.mul": encode_land_mul(WIDTH, HEIGHT, [(c["land_id"], c["z"]) for c in cells]),
                 "staidx0.mul": index, "statics0.mul": data, "fixed.json": _json_bytes(fixtures)}
    report = {
        "schema": 1, "kind": "trinsic-walking-area", "width": WIDTH, "height": HEIGHT,
        "source_origin": list(ORIGIN), "cell_count": len(cells), "blocks": len(index) // 12,
        "avatar": {"source": avatar, "local": [*route[0], 0]},
        "finnigan": {"source": finnigan, "local": [*route[-1], 0], "npc_slot": 12},
        "transform": f"local=(source_x-{ORIGIN[0]},source_y-{ORIGIN[1]}); target_z=source_lift*4",
        "height_evidence": "IFIX pillar shape 920 stands five source lifts high; UO art 0x00db stands 20 Z. Roof and tree art have substituted heights.",
        "route": route, "route_check": "cardinal structural path", "landmark_ids": sorted(anchors),
        "fixed": {"file": "fixed.json", "source_ifix_placements": sum(o["family"] == "IFIX" for o in fixtures),
                  "terrain_placements": sum(o["family"] == "U7CHUNKS" for o in fixtures)},
        "statics": statics, "cells": cells, "land_rules": land_rules, "static_rules": static_rules,
        "investigation_items": clues,
        "interactive_fixed": interactive_fixed,
        "ireg_objects_deferred": [{"id": o["id"], "shape": o["shape"], "world_xy": o["world_xy"]}
                                  for o in live_records if o["id"] not in clue_ids and o["id"] not in stair_ids],
        "scope": "Structural route. Inventory, NPC schedules, triggers, original collision and gameplay require runtime verification.",
        "source_sha256": hashes, "output_sha256": {n: hashlib.sha256(v).hexdigest() for n, v in files_out.items()},
    }
    out.mkdir(parents=True, exist_ok=True)
    for name, data in files_out.items():
        (out / name).write_bytes(data)
    (out / "terrain.json").write_bytes(_json_bytes(report))
    return report
