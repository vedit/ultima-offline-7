"""Census of the original new-game world, retaining region- and byte-level provenance."""

from collections import Counter
import hashlib
import json
import re
import struct

from .actor import actor_table
from .containers import decode_member
from .terrain import CHUNK_BYTES, TerrainSource, fixed_inventory
from .u7 import seed_directory


def schedule_entries(data):
    """DOS Schedule_read uses a 16-bit count and count+1 cumulative 16-bit indices."""
    if len(data) < 4:
        raise ValueError("Truncated SCHEDULE.DAT")
    count = int.from_bytes(data[:2], "little")
    start = 2 + (count + 1) * 2
    if not 0 < count <= 256 or len(data) < start or (len(data) - start) % 4:
        raise ValueError("Invalid SCHEDULE.DAT dimensions")
    indices = struct.unpack_from(f"<{count + 1}H", data, 2)
    total = (len(data) - start) // 4
    if indices[0] or indices[-1] != total or any(a > b for a, b in zip(indices, indices[1:])):
        raise ValueError("SCHEDULE.DAT indices do not partition the entries")
    entries = []
    for slot, (first, end) in enumerate(zip(indices, indices[1:])):
        for index in range(first, end):
            offset = start + index * 4
            activity, x, y, region = data[offset:offset + 4]
            if region >= 144:
                raise ValueError(f"SCHEDULE.DAT at {offset} names invalid region {region}")
            entries.append({"npc_slot": slot, "ordinal": index - first, "offset": offset,
                            "time_slot": activity & 7, "activity": activity >> 3, "region": region,
                            "world_xy": [region % 12 * 256 + x, region // 12 * 256 + y]})
    return entries


def count_terrain_words(world, chunks):
    """Count each definition once, weighting its tile words by actual placement count."""
    TerrainSource(world, chunks)
    placements = Counter(value for value, in struct.iter_unpack("<H", world))
    words = Counter()
    for chunk, frequency in placements.items():
        offset = chunk * CHUNK_BYTES
        local = Counter(word for word, in struct.iter_unpack("<H", chunks[offset:offset + CHUNK_BYTES]))
        for word, count in local.items():
            words[word] += frequency * count
    return words


def world_census(u7, region=None, *, movable_output=None):
    if region is not None and not 0 <= region < 144:
        raise ValueError("Region must be in the range 00–8F (hex)")
    static = u7 / "STATIC"
    archive = (static / "INITGAME.DAT").read_bytes()
    fingerprint = hashlib.sha256(archive).hexdigest()
    tfa = (static / "TFA.DAT").read_bytes()
    members = seed_directory(archive)
    if movable_output is not None:
        if region is not None:
            raise ValueError("A published movable-object catalog requires the whole world")
        movable_output.mkdir()
        (movable_output/"initgame.source").write_bytes(archive)
    _, start, size = members["npc.dat"]
    actor_counts, actors = actor_table(archive[start:start + size], tfa)
    schedules = schedule_entries((static / "SCHEDULE.DAT").read_bytes())
    world = (static / "U7MAP").read_bytes()
    chunks = (static / "U7CHUNKS").read_bytes()
    terrain = TerrainSource(world, chunks) if region is not None else None
    families = Counter()
    totals = Counter()
    regions = []
    for index in range(144) if region is None else [region]:
        filename = f"U7IFIX{index:02X}"
        fixed = fixed_inventory((static / filename).read_bytes(), index, fingerprint)
        member = f"u7ireg{index:02x}"
        slot, offset, size = members[member]
        try:
            movable, markers = decode_member(archive[offset:offset + size], tfa, offset, fingerprint, index)
        except ValueError as exc:
            raise ValueError(f"INITGAME.DAT/{member} (archive offset {offset}): {exc}") from exc
        consumed = sum(1 + obj["length"] for obj in movable) + sum(3 if m["tag"] == 2 else 1 for m in markers)
        if consumed != size:
            raise ValueError(f"IREG byte reconciliation failed for {member}")
        if movable_output is not None:
            (movable_output/f"{member}.json").write_text(
                json.dumps({"member":member,"slot":slot,"offset":offset,"size":size,
                            "objects":movable,"markers":markers},sort_keys=True,separators=(",",":"))+"\n",
                encoding="utf-8",newline="\n")
        fixed_count = fixed["record_count"]
        counts = {"fixed": fixed_count, "movable": len(movable), "ireg_bytes_consumed": consumed,
                  "ireg_markers": len(markers), "inventory_links": sum(o["edge"] == "inventory" for o in movable),
                  "barge_links": sum(o["edge"] == "barge_member" for o in movable)}
        totals.update(counts)
        families.update((o["shape"], o["frame"]) for o in movable)
        families.update((o["shape"], o["frame"]) for o in fixed["objects"])
        regions.append({"index": index, "ifix": filename, "ifix_sha256": fixed["source_sha256"],
                        "ireg_member": member, "member_slot": slot, "member_offset": offset, **counts})
        if region is not None:
            left = index % 12 * 256
            top = index // 12 * 256
            return {**regions[0], "seed_sha256": fingerprint, "fixed_objects": fixed["objects"],
                    "movable_objects": movable, "markers": markers,
                    "land_chunk_ids": [terrain.tile(left + x, top + y)["chunk_id"]
                                       for y in range(0, 256, 16) for x in range(0, 256, 16)],
                    "actors": [r for r in actors if r.get("superchunk") == index],
                    "schedule_destinations": [s for s in schedules if s["region"] == index]}
    ground = count_terrain_words(world, chunks)
    return {"schema": 1, "seed_sha256": fingerprint, "regions": regions, "totals": dict(totals),
            "land_tile_occurrences": ground.total(), "land_shape_frame_pairs": len(ground),
            "land_by_shape_frame": [[word & 1023, word >> 10, n] for word, n in sorted(ground.items())],
            "object_shape_frame_pairs": len(families),
            "objects_by_shape_frame": [[shape, frame, n] for (shape, frame), n in sorted(families.items())],
            "actor_table": actor_counts, "placed_actor_slots": sum(r["placed"] for r in actors),
            "schedule_entries": len(schedules), "scheduled_slots": len({s["npc_slot"] for s in schedules}),
            "scope": "Source inventory. Target emission, behavior and gameplay are unqualified."}


def verify_movable_catalog(directory):
    catalog = directory/"world-ireg"
    census = json.loads((directory/"world.json").read_bytes())
    archive = (catalog/"initgame.source").read_bytes()
    tfa = (directory/"world-statics/tfa.dat").read_bytes()
    seed = hashlib.sha256(archive).hexdigest()
    if seed != census["seed_sha256"] or [r["index"] for r in census["regions"]] != list(range(144)):
        raise ValueError("Original movable catalog seed or region coverage differs")
    members = seed_directory(archive)
    counts = Counter()
    for region in census["regions"]:
        index = region["index"]
        name = f"u7ireg{index:02x}"
        slot, start, length = members[name]
        data = archive[start:start+length]
        objects, markers = decode_member(data,tfa,start,seed,index)
        stored = json.loads((catalog/f"{name}.json").read_bytes())
        if stored != {"member":name,"slot":slot,"offset":start,"size":length,"objects":objects,"markers":markers}:
            raise ValueError(f"Movable catalog differs from original bytes in {name}")
        ancestry = {}
        next_ordinal = Counter()
        for row in objects:
            parent, edge = row["parent"], row["edge"]
            if (row["id"] in ancestry or row["ordinal"] != next_ordinal[parent] or
                    (parent is None) != (edge == "world") or
                    (parent is not None and (parent not in ancestry or edge !=
                        ("barge_member" if ancestry[parent]["kind"]=="barge" else "inventory")))):
                raise ValueError(f"Invalid movable parent, order or attachment at {row['id']}")
            if ("world_xy" in row) != (edge != "inventory") or ("gump_xy" in row) != (edge=="inventory"):
                raise ValueError(f"Movable coordinates use the wrong space at {row['id']}")
            next_ordinal[parent] += 1
            ancestry[row["id"]] = row
            counts[edge] += 1
        if len(objects)!=region["movable"] or len(markers)!=region["ireg_markers"] or length!=region["ireg_bytes_consumed"]:
            raise ValueError(f"Movable catalog counts differ from census for {name}")
    if sum(counts.values()) != census["totals"]["movable"]:
        raise ValueError("Movable world record total differs")
    return {"status":"passed","regions":144,"source_records":sum(counts.values()),"edges":dict(counts),
            "source_bytes":census["totals"]["ireg_bytes_consumed"],"source_sha256":seed}


def explain_movable(directory, source_id):
    match = re.fullmatch(r"ireg:([0-9a-f]{64}):(u7ireg[0-9a-f]{2}):([0-9]+)",source_id)
    if not match or int(match[2][-2:],16)>=144:
        raise ValueError("Invalid regional movable source ID")
    member = match[2]
    rows = json.loads((directory/"world-ireg"/f"{member}.json").read_bytes())["objects"]
    table = {row["id"]:row for row in rows}
    if source_id not in table:
        raise ValueError(f"No such movable object in {member}: {source_id}")
    item = anchor = table[source_id]
    chain = []
    while anchor["parent"]:
        anchor = table[anchor["parent"]]
        chain.append(anchor)
    location = next(row for row in (item,*chain) if "world_xy" in row)
    result = {"id":source_id,"member":member,"source":"STATIC/INITGAME.DAT","object":item,
            "owner_chain":[r["id"] for r in chain],"position_source_id":location["id"],
            "initial_world_position":[*location["world_xy"],location["lift"]],
            "children":[r["id"] for r in rows if r["parent"]==source_id]}
    if (directory/"world-live-coverage.json").is_file():
        coverage=json.loads((directory/"world-live-coverage.json").read_bytes())
        reason=coverage["roots"][member][str(anchor["offset"])]
        result["regional_disposition"]=reason
        if reason=="live":
            live=json.loads((directory/"world-live.json").read_bytes())
            record=next(r for r in live["objects"] if r["id"]==source_id)
            result["native_item"]={"art":record["art"],"kind":record["kind"],"material":live["materials"][str(item["shape"])]}
    return result
