"""Black Gate opening AreaSearch. Use the original chunk lists and actor insertion order."""

from .containers import decode_member
from .u7 import seed_directory


def extent(position, shape, frame, tfa):
    x, y, z = position
    physical, _, foot = tfa[shape*3:shape*3+3]
    dx, dy = foot & 7, foot >> 3 & 7
    if frame & 32:
        dx, dy = dy, dx
    heights = (0x8000, 0x4000, 0x6000, 0x7000, 0x7800, 0x7C00, 0x7E00, 0x7F00)
    return (((2 << dx) - 1) << (15 - x % 16), ((2 << dy) - 1) << (15 - y % 16),
            heights[physical >> 5] >> z)


def compare(a, b):
    # CompareItemExtent returns 1 to insert before b, 2 for after, 0 if incomparable.
    x, y, z = a
    u, v, w = b
    if x <= u and y <= v and z <= w:
        return 1
    if x >= u and y >= v and z >= w:
        return 2
    if x & u and y & v:
        return 1 if z < w else 2 if z > w else 0
    if x & u:
        lower, higher = y < v, y > v
    elif y & v:
        lower, higher = x < u, x > u
    else:
        lower, higher = x < u and y < v, x >= u and y > v
    if lower and (z <= w or z & w):
        return 1
    if higher and (z >= w or z & w):
        return 2
    return 0


def insert_item(chunk, key, boxes):
    # PlaceItem first inserts before its first successor. Dependencies found
    # later in the list are then moved before the insertion in source order.
    index = next((i for i, other in enumerate(chunk) if compare(boxes[key], boxes[other]) == 1), len(chunk))
    chunk.insert(index, key)
    while True:
        rest = chunk[index + 1:]
        candidate = next((i for i in range(1, len(rest)) if compare(boxes[key], boxes[rest[i]]) == 2), None)
        if candidate is None:
            return
        while True:
            prior = next((i for i in range(1, candidate) if compare(boxes[rest[candidate]], boxes[rest[i]]) == 2), None)
            if prior is None:
                break
            candidate = prior
        chunk.insert(index, chunk.pop(index + 1 + candidate))
        index += 1


def opening_search(archive, tfa, seed, center, radius):
    left, top = center[0] - radius, center[1] - radius
    right, bottom = center[0] + radius, center[1] + radius
    if min(left, top) < 0 or max(right, bottom) >= 3072:
        raise ValueError("This opening search requires an interior source area")
    directory = seed_directory(archive)
    chunks, boxes, source_regions = {}, {}, []
    # Include all top-level pre-existing objects in the scanned chunks before
    # RelinkNpcsInArea places actors in ascending original slot order.
    for ry in range(top//256, bottom//256 + 1):
        for rx in range(left//256, right//256 + 1):
            reg = 12*ry + rx
            member = f"u7ireg{reg:02x}"
            _, start, size = directory[member]
            rows, _ = decode_member(archive[start:start+size], tfa, start, seed["seed_sha256"], reg)
            source_regions.append(member)
            for row in rows:
                if row["edge"] != "world":
                    continue
                x, y = row["world_xy"]
                group = (x//16, y//16)
                if not (left//16 <= group[0] <= right//16 and top//16 <= group[1] <= bottom//16):
                    continue
                if row["tfa_class"] in (12, 13):
                    raise ValueError(f"Opening search has a regional NPC with no bound actor slot: {row['id']}")
                boxes[row["id"]] = extent([x,y,row["lift"]],row["shape"],row["frame"],tfa)
                chunks.setdefault(group, []).append(row["id"])
    eligible = {}
    for actor in sorted(seed["actors"].values(), key=lambda row: row["npc_slot"]):
        slot = actor["npc_slot"]
        x, y, z = actor["source_position"]
        if slot == 0:
            x, y = center
        group = (x//16, y//16)
        if not (left//16 <= group[0] <= right//16 and top//16 <= group[1] <= bottom//16):
            continue
        flags = tfa[3*actor["shape"] + 1]
        if (left <= x <= right and top <= y <= bottom and flags & 15 in (12,13)
                and not flags & 128 and not actor["item_flags"]["0"] and not actor["item_flags"]["4"]):
            eligible[actor["id"]] = slot
        boxes[actor["id"]] = extent((x,y,z),actor["shape"],actor["frame"],tfa)
        insert_item(chunks.setdefault(group, []), actor["id"], boxes)
    slots = []
    for group in sorted(chunks, key=lambda k: (k[1], k[0]), reverse=True):
        slots.extend(eligible[key] for key in chunks[group] if key in eligible)
    return {"center": list(center), "radius": radius, "mask": 8, "slots": slots, "regions": source_regions,
            "ordering": "AreaScan bottom-right chunk first; IREG lists with DOS PlaceItem actor insertion",
            "scope": "Opening actors at original positions, Avatar after scripted west steps; runtime must check deltas."}
