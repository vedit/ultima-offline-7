"""Read Black Gate's initial script-visible state from the owner's new-game archive."""

import hashlib
import json
import struct

from .actor import actor_table
from .area_search import opening_search
from .containers import decode_member
from .portrait import _member, face_frame
from .terrain import _child
from .u7 import seed_directory
from .world import schedule_entries


def ready_slot(data, shape):
    """Read the DOS ReadyTable entry, including its zero-filled default record."""
    if not data or len(data) != 1 + 9 * data[0]:
        raise ValueError("Invalid Black Gate READY.DAT length")
    matches = [at for at in range(1, len(data), 9) if struct.unpack_from("<H", data, at)[0] == shape]
    if len(matches) > 1:
        raise ValueError(f"Ambiguous READY.DAT entry for shape {shape}")
    at = matches[0] if matches else None
    return {"slot": data[at + 2] >> 3 if at is not None else 0, "offset": at,
            "sha256": hashlib.sha256(data).hexdigest()}


def decode_story_seed(seed, tfa):
    members = seed_directory(seed)
    digest = hashlib.sha256(seed).hexdigest()

    def member(name):
        if name not in members:
            raise ValueError(f"INITGAME.DAT lacks {name}")
        slot, offset, size = members[name]
        data = seed[offset:offset + size]
        return data, {"slot": slot, "offset": offset, "size": size, "sha256": hashlib.sha256(data).hexdigest()}

    flags, flag_source = member("flaginit")
    if not 0 < len(flags) <= 32768:
        raise ValueError("Invalid story flag count in flaginit")
    # DOS GameFlagSet::load calls set(index, input.readByte()) once per flag.
    npc_data, npc_source = member("npc.dat")
    _, rows = actor_table(npc_data, tfa, include_inventory=True)
    actors = {}
    for row in rows:
        if not row["placed"]:
            continue
        slot = row["npc_slot"]
        actor_id = f"npc:{digest}:npc.dat:{slot}"
        prefix = f"npc-item:{digest}:npc.dat:"
        for item in row["inventory"]:
            parent_offset = item["parent_offset"]
            item.update(id=prefix + str(item["record_offset"]), file_offset=npc_source["offset"] + item["record_offset"],
                        parent=actor_id if parent_offset is None else prefix + str(parent_offset), owner=actor_id)
        start = row["record_offset"]
        status = struct.unpack_from("<H", npc_data, start + 16)[0]
        hit_points = struct.unpack_from("<b", npc_data, start + 10)[0]
        experience, training = struct.unpack_from("<iB", npc_data, start + 32)
        item_flags = {str(flag): bool(status & mask) for flag, mask in
                      ((1, 0x80), (2, 0x100), (3, 0x200), (4, 0x8000), (6, 0x800),
                       (7, 0x1000), (8, 0x2000), (9, 0x4000))}
        item_flags["0"] = bool(npc_data[start + 11] & 1)
        actors[str(slot)] = {**row, "id": actor_id,
                             "file_offset": npc_source["offset"] + start,
                             "item_flags": item_flags, "status_word": status, "hit_points": hit_points,
                             "can_act": hit_points > 0 and not any(item_flags[i] for i in ("1", "7", "4")),
                             "activity": npc_data[start + 22], "experience": experience, "training": training}
    if "0" not in actors:
        raise ValueError("The initial story seed has no Avatar")
    return {"schema": 1, "seed_sha256": digest, "flags": [int(bool(v)) for v in flags],
            "actors": actors, "members": {"npc.dat": npc_source, "flaginit": flag_source}}


def area_eggs(archive, tfa, digest, origin, width, height):
    """Resolve IREG eggs within the emitted area, including their original Usecode caller identity."""
    left, top = origin
    if min(width, height) <= 0 or min(origin) < 0 or left + width > 3072 or top + height > 3072:
        raise ValueError("Invalid trigger area")
    directory = seed_directory(archive)
    eggs = []
    for sy in range(top // 256, (top + height - 1) // 256 + 1):
        for sx in range(left // 256, (left + width - 1) // 256 + 1):
            region = 12 * sy + sx
            name = f"u7ireg{region:02x}"
            _, start, size = directory[name]
            objects, _ = decode_member(archive[start:start + size], tfa, start, digest, region)
            for obj in objects:
                if obj["kind"] != "egg":
                    continue
                x, y = obj["world_xy"]
                if not (left <= x < left + width and top <= y < top + height):
                    continue
                raw = bytes.fromhex(obj["payload_hex"])
                flags, probability, data1, _, data2 = struct.unpack_from("<HBHBH", raw, 4)
                kind = flags & 15
                egg = {**obj, "position": [x, y, obj["lift"]], "member": name,
                       "kind_id": kind, "criteria": (flags >> 4) & 7, "nocturnal": bool(flags & 128),
                       "once": bool(flags & 256), "hatched": bool(flags & 512), "distance": (flags >> 10) & 31,
                       "repeat": bool(flags & 32768), "probability": probability, "data1": data1, "data2": data2}
                if kind == 5:
                    egg.update(function_id=data2, event=3)
                eggs.append(egg)
    return eggs


def opening_moongate(static, tfa, uo_root):
    shape_id, target = 157, 0x0DDA
    label, label_offset = _member(_child(static, "TEXT.FLX").read_bytes(), shape_id, "TEXT.FLX")
    if label.rstrip(b"\0") != b"Moongate":
        raise ValueError("Unexpected source name for the opening moongate")
    shape, start = _member(_child(static, "SHAPES.VGA").read_bytes(), shape_id, "SHAPES.VGA")
    palette, _ = _member(_child(static, "PALETTES.FLX").read_bytes(), 0, "PALETTES.FLX")
    count = (struct.unpack_from("<I", shape, 4)[0] - 4) // 4
    if count != 12:
        raise ValueError("Opening moongate frames differ from the qualified source")
    frames = []
    for i in range(count):
        w, h, pixels, offset, origin = face_frame(shape, i)
        opaque = [p for p in pixels if p is not None]
        red = sum(palette[p*3] > max(palette[p*3+1:p*3+3]) for p in opaque)
        if not opaque or red <= len(opaque) // 2:
            raise ValueError("Source moongate does not match the native red moongate presentation")
        frames.append({"frame": i, "width": w, "height": h, "origin": list(origin), "file_offset": start + offset})
    tiles = _child(uo_root, "tiledata.mul").read_bytes()
    native = []
    for item in range(target, target + 5):
        offset = 512 * 964 + (item // 32) * 1316 + 4 + (item % 32) * 41
        name = tiles[offset+21:offset+41].split(b"\0", 1)[0]
        if name != b"red moongate":
            raise ValueError(f"UO art {item:#x} does not identify the red moongate")
        native.append({"id": item, "tiledata_offset": offset, "flags": struct.unpack_from("<Q", tiles, offset)[0]})
    return {"name": "Moongate", "source_shape": shape_id, "source_frames": count, "frames": frames,
            "name_file_offset": label_offset, "tfa": tfa[3*shape_id:3*shape_id+3].hex(),
            "shape_sha256": hashlib.sha256(shape).hexdigest(), "uo_item_id": target, "uo_family": native,
            "presentation": "Native red moongate animation. Original Usecode owns object state and lifetime."}


def gate_records(archive, tfa, walking, uo_root):
    left, top = walking["source_origin"]
    right, bottom = left + walking["width"], top + walking["height"]
    # 0834 searches up to 25 source tiles from the Avatar. Keep the candidate
    # census outside the build too, so an omitted leaf cannot become an empty result.
    directory = seed_directory(archive)
    digest = hashlib.sha256(archive).hexdigest()
    candidates, placed = [], []
    tiledata = _child(uo_root, "tiledata.mul").read_bytes()
    for sy in range(max(0, top - 25) // 256, min(3071, bottom + 24) // 256 + 1):
        for sx in range(max(0, left - 25) // 256, min(3071, right + 24) // 256 + 1):
            region = sy * 12 + sx
            _, start, size = directory[f"u7ireg{region:02x}"]
            objects, _ = decode_member(archive[start:start+size], tfa, start, digest, region)
            for obj in objects:
                shape = obj["shape"]
                if obj["edge"] != "world" or shape not in (271, 272, 276, 277):
                    continue
                x, y = obj["world_xy"]
                if not (left-25 <= x < right+25 and top-25 <= y < bottom+25):
                    continue
                rec = {**obj, "position": [x, y, obj["lift"]], "handle": 0x300000 + obj["archive_offset"]}
                candidates.append({k: rec[k] for k in ("id", "handle", "shape", "position")})
                if not (left <= x < right and top <= y < bottom):
                    continue
                size_byte = tfa[3*shape+2]
                w, h = (size_byte & 7)+1, ((size_byte >> 3) & 7)+1
                if obj["frame"] & 32:
                    w, h = h, w
                art, name = {271: (0x6F5, "portcullis"), 272: (0x6F6, "portcullis"),
                             276: (0x141, "wooden beam"), 277: (0x141, "wooden beam")}[shape]
                off = 512*964 + art//32*1316 + 4 + art%32*41
                if (tiledata[off+21:off+41].split(b"\0", 1)[0] != name.encode()
                        or not struct.unpack_from("<Q", tiledata, off)[0] & 0x40 or tiledata[off+20] != 20):
                    raise ValueError("Unexpected native gate geometry")
                rec.update(footprint=[w,h], uo_art=art, uo_name=name, staged_land_id=
                           walking["cells"][(y-top)*walking["width"]+x-left]["land_id"])
                placed.append(rec)
    return placed, candidates


def investigation_chests(archive, tfa, walking, uo_root):
    """Recover the full original containment tree for the lock that fits the stables key."""
    left, top = walking["source_origin"]
    right, bottom = left + walking["width"], top + walking["height"]
    keys = {o["quality_byte"] for o in walking["investigation_items"] if o["shape"] == 641}
    tiledata = _child(uo_root, "tiledata.mul").read_bytes()
    arts = {522: (0x0E42, "wooden chest"), 955: (0x1088, "necklace"),
            797: (0x0EF3, "blank scroll%s%"), 644: (0x0EED, "gold coin")}
    directory, digest = seed_directory(archive), hashlib.sha256(archive).hexdigest()
    trees = []
    for sy in range(top//256, (bottom-1)//256+1):
        for sx in range(left//256, (right-1)//256+1):
            region = sy*12 + sx
            name = f"u7ireg{region:02x}"
            _, offset, size = directory[name]
            rows, _ = decode_member(archive[offset:offset+size], tfa, offset, digest, region)
            for chest in rows:
                if chest["shape"] != 522 or chest["edge"] != "world" or chest["quality_byte"] not in keys:
                    continue
                x, y = chest["world_xy"]
                if not left <= x < right or not top <= y < bottom:
                    continue
                objects = []
                for obj in (chest, *(child for child in rows if child["root"] == chest["id"])):
                    if obj["shape"] not in arts:
                        raise ValueError(f"Unmapped investigation chest contents at {obj['id']}")
                    art, label = arts[obj["shape"]]
                    i = 512*964 + art//32*1316 + 4 + art%32*41
                    if tiledata[i+21:i+41].split(b"\0",1)[0] != label.encode():
                        raise ValueError("Investigation chest art differs from the pinned native catalog")
                    amount = max(1, obj["quality_byte"] & 127) if obj["tfa_class"] == 3 else 1
                    objects.append({**obj, "uo_art": art, "amount": amount, "handle": 0x300000 + obj["archive_offset"]})
                trees.append({"member": name, "id": chest["id"], "objects": objects,
                              "staged_land_id": walking["cells"][(y-top)*walking["width"]+x-left]["land_id"]})
    return trees


def forge_clock(archive, *, require_saved=False):
    """Read the Forge world clock. Other GAMETIM members track separate timers."""
    timer = seed_directory(archive).get("gametimm.dat")
    ticks, days, rate = 9000, 0, 1  # GameTime(6, 1), gtimer.cpp, if there is no saved clock.
    if timer:
        _, offset, size = timer
        if size != 6:
            raise ValueError("Invalid original game clock record")
        ticks, days, rate = struct.unpack_from("<HHH", archive, offset)
    elif require_saved:
        raise ValueError("Missing saved Forge world clock GAMETIMM.DAT")
    if ticks >= 36000 or rate == 0:
        raise ValueError("Invalid original world clock values")
    return {"ticks": ticks, "days": days, "rate": rate, "ticks_per_minute": 25,
            "ticks_per_day": 36000, "source": "gametimm.dat" if timer else "DOS GameTime(6,1)"}


def produce_story_seed(u7_root, output, uo_root=None):
    static = _child(u7_root, "STATIC")
    if output.resolve().is_relative_to(u7_root.resolve()):
        raise ValueError("Story-state output must be outside the input installation")
    archive = _child(static, "INITGAME.DAT").read_bytes()
    tfa = _child(static, "TFA.DAT").read_bytes()
    result = decode_story_seed(archive, tfa)
    result["clock"] = forge_clock(archive)
    # Normal new game: PartySaver::save adds Avatar to the empty roster.
    # ResetItemBufferGlobals initially locks Avatar movement during the opening.
    # The user's existing saves and cheat-start path are not an initialization source.
    if any(a["item_flags"]["6"] for a in result["actors"].values()):
        raise ValueError("The initial NPC roster differs from the qualified normal new-game seed")
    result["opening_party_slots"] = [0]
    result["opening_avatar_dont_move"] = 1
    avatar_x, avatar_y, _ = result["actors"]["0"]["source_position"]
    result["opening_nearby"] = opening_search(archive, tfa, result, (avatar_x - 3, avatar_y), 40)
    if uo_root is not None:
        weight_volume = _child(static, "WGTVOL.DAT").read_bytes()
        tiles = _child(uo_root, "tiledata.mul").read_bytes()
        coin = 0x0EED
        ready = ready_slot(_child(static, "READY.DAT").read_bytes(), 644)
        if ready["slot"] != 0:
            raise ValueError("Unqualified currency ready-slot preference")
        off = 512*964 + coin//32*1316 + 4 + coin%32*41
        if tiles[off+21:off+41].split(b"\0",1)[0] != b"gold coin" or tfa[644*3+1] & 15 != 3:
            raise ValueError("Original gold and UO coin art no longer match the quantity profile")
        result["runtime_shapes"] = {"157": opening_moongate(static, tfa, uo_root),
                                    "644": {"shape":644, "uo_art":coin, "uo_item_id":coin, "tfa":tfa[644*3:644*3+3].hex(),
                                            "weight":weight_volume[644*2], "volume":weight_volume[644*2+1],
                                            "tiledata_offset":off, "class":3, "ready":ready}}
    walking = json.loads((output / "walking/terrain.json").read_bytes())
    left, top = walking["source_origin"]
    timetable = _child(static, "SCHEDULE.DAT").read_bytes()
    result["schedule_sha256"] = hashlib.sha256(timetable).hexdigest()
    for actor in result["actors"].values():
        actor["schedule"] = []
    for entry in schedule_entries(timetable):
        actor = result["actors"].get(str(entry["npc_slot"]))
        if actor is not None:
            actor["schedule"].append(entry)
    result["investigation_items"] = walking["investigation_items"]
    result["interactive_fixed"] = walking["interactive_fixed"]
    if uo_root is not None:
        result["gate_objects"], result["gate_search_candidates"] = gate_records(archive, tfa, walking, uo_root)
        result["gate_query_bounds"] = [left, top, left + walking["width"], top + walking["height"]]
        result["investigation_chests"] = investigation_chests(archive, tfa, walking, uo_root)
    for item in result["investigation_items"]:
        x, y = item["world_xy"]
        cell = walking["cells"][(y - top) * walking["width"] + x - left]
        item["staged_land_id"] = cell["land_id"]
    result["eggs"] = area_eggs(archive, tfa, result["seed_sha256"], (left, top), walking["width"], walking["height"])
    result["walking_actor_slots"] = [row["npc_slot"] for row in result["actors"].values()
                                     if row["npc_slot"] != 0
                                     and left <= row["source_position"][0] < left + walking["width"]
                                     and top <= row["source_position"][1] < top + walking["height"]]
    for slot in result["walking_actor_slots"]:
        actor = result["actors"][str(slot)]
        x, y, _ = actor["source_position"]
        cell = walking["cells"][(y - top) * walking["width"] + x - left]
        if (cell["x"], cell["y"]) != (x - left, y - top):
            raise ValueError(f"Walking terrain for NPC slot {slot} is out of order")
        actor["staged_land_id"] = cell["land_id"]
    (output / "story-seed.json").write_bytes((json.dumps(result, sort_keys=True, separators=(",", ":")) + "\n").encode())
    return result
