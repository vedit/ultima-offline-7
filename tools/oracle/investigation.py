"""Read the original save's quest flags and trace the Trinsic key to a chunk or actor."""

import argparse
import hashlib
import json
from pathlib import Path
import struct

from u7uo.u7 import seed_directory


def _key_report(session, receipt, usecode):
    from .qualify import mask, MENU, TEXT
    from u7uo.u7 import usecode_inventory

    data = next(r for r in usecode_inventory(usecode)["records"] if r["id"] == 0x40c)
    base = data["code_offset"]
    # This is Finnigan's post-acceptance branch at 040C:003C. The original
    # 0885 initial-offer helper contains similar text but different branches.
    specs = [
        ("address-seated-mayor", TEXT, "942a26a3d4988f047ea574b1276d9744952e3e80346b44f3b8f394872b75b54f", [0x3c]),
        ("searched-stable-response-menu", MENU, "7ad573b4746bfe80593ee7f85e7bc80e75e49cfc6783e1c0af8fa0aaa188eccf", []),
        ("report-completed-search", TEXT, "d5e11956306f05da8a0df3a6c4a9b346228e16cb407903bc4902c48cf267b791", [0x46]),
        ("original-key-clue-topics", (98,64,280,95), "1be8a9714350acbd4b176229954d1af8c00d5c80d4c218d28085822c27902478",
         [0x54,0x51,0x4e,0x66]),
        ("original-report-key", TEXT, "27c5561ea19bb94a7691d7ad1abc249d3f924cdeb271119000708cd0a5e7a62b", [0x87]),
    ]
    frames = []
    for label, box, digest, pcs in specs:
        matches = [f for f in receipt["frames"] if f["file"].endswith("-" + label + ".png")]
        if len(matches) != 1 or (frames and matches[0]["elapsed_ms"] <= frames[-1]["elapsed_ms"]):
            raise ValueError("missing or unordered original investigation screen")
        record = matches[0]
        raw = (session / record["file"]).read_bytes()
        if hashlib.sha256(raw).hexdigest() != record["sha256"] or mask(raw, box) != digest:
            raise ValueError(f"original investigation screen disagrees at {label}")
        text = []
        for pc in pcs:
            if usecode[base + pc] != (0x1d if len(pcs) > 1 else 0x1c):
                raise ValueError("unexpected original investigation text instruction")
            start = data["offset"] + 6 + struct.unpack_from("<H", usecode, base + pc + 1)[0]
            end = usecode.index(0, start, data["offset"] + 6 + data["data_length"])
            text.append({"function_id": 0x40c, "pc": pc, "source_string_offset": start,
                         "source_string_sha256": hashlib.sha256(usecode[start:end]).hexdigest()})
        frames.append({**record, "glyph_mask_sha256": digest, "rect": box, "source_strings": text})
    for idx, x1, x2, y1, y2 in ((1,102,136,65,80), (3,101,148,78,92)):
        inputs = [a for a in receipt["actions"] if a["type"] == "click" and
                  frames[idx]["elapsed_ms"] < a["elapsed_ms"] < frames[idx+1]["elapsed_ms"]]
        if len(inputs) != 1 or inputs[0].get("button", 0) != 0 or not (
                x1 <= inputs[0]["x"]*320 <= x2 and y1 <= inputs[0]["y"]*200 <= y2):
            raise ValueError("original investigation menu input differs")
        frames[idx]["choice_input"] = inputs[0]
    if usecode[base+0x92:base+0x96] != bytes.fromhex("13 43 48 00"):
        raise ValueError("original Finnigan key report no longer sets flag 72")
    return {"source_frames": frames, "flag_write": {"function_id": 0x40c, "pc": 0x93, "flag": 72}}


def inspect_save(save: Path) -> dict:
    raw=save.read_bytes()
    entries=seed_directory(raw)
    def member(k):
        _,start,size=entries[k]
        return raw[start:start+size]
    items=member("u7ibuf.dat")
    npcs=member("u7nbuf.dat")
    nodes=member("itemnode.dat")
    flags=member("flaginit")
    if len(nodes)!=2059 or len(items)%8 or len(flags)!=837 or (len(npcs)-4)%129:
        raise ValueError("unrecognized original Forge runtime save tables")
    def item(a):
        if a%8 or not 0<a<=len(items)-8:
            raise ValueError(f"invalid DOS item handle {a}")
        return struct.unpack_from("<HHHBB",items,a)
    def chain(head,needle):
        visited=set()
        while head:
            if head in visited:
                raise ValueError("cycle in DOS list")
            visited.add(head)
            if head==needle:
                return True
            head=item(head)[0]
        return False
    def word(b,i):
        return struct.unpack_from("<H",b,i)[0]
    npc_count=(len(npcs)-4)//129
    actors={}
    for slot in range(npc_count):
        ref=word(npcs,105*slot+2)
        if ref not in (0,0xffff):
            actors[ref]=slot
    free=word(nodes,0)
    keys=[]
    for a in range(8,len(items),8):
        _,position,shape,attr,quality=item(a)
        if shape&1023!=641 or (shape>>10)&31 or quality!=253 or chain(free,a):
            continue
        kind=attr&7
        if kind<4:
            x,y=position&255,position>>8
            chunk=kind*256+(y>>4)*16+(x>>4)
            if not chain(word(nodes,6+chunk*2),a):
                raise ValueError("ground key absent from its recorded chunk list")
            region=nodes[-5+kind]
            if region>=144:
                raise ValueError("invalid loaded region for ground key")
            keys.append({"item_handle":a,"location":"world","world_xy":[(region%12)*256+x,(region//12)*256+y]})
        elif kind in (6,7):
            refs=[]
            cur,parent=a,position
            while parent:
                if parent in refs:
                    raise ValueError("cyclic original key ownership")
                refs.append(parent)
                _,parent_or_xy,_,ext_lo,ext_hi=item(parent)
                ext=ext_lo|ext_hi<<8
                item(ext)
                if not chain(word(items,ext),cur):
                    raise ValueError("parent contents disagree with key ownership link")
                if parent in actors or items[ext+5]&7 not in (6,7):
                    break
                cur,parent=parent,parent_or_xy
            keys.append({"item_handle":a,"location":"inventory","parents":refs,
                         "parent_shapes":[item(ref)[2]&1023 for ref in refs],
                         "actor_slot":actors.get(refs[-1]) if refs else None})
    if len(keys)!=1:
        raise ValueError(f"expected one live quality-253 key, saw {len(keys)}")
    positions={}
    for a,slot in actors.items():
        if slot not in (0,1,2,11,12):
            continue
        _,xy,_,lo,hi=item(a)
        ext=lo|(hi<<8)
        item(ext)
        reg=items[ext+2]
        positions[str(slot)]={"item_handle":a,"region":reg,"world_xy":[reg%12*256+(xy&255),reg//12*256+(xy>>8)],
                              "location_kind":items[ext+5]&7}
    return {"schema":1,"save_file":save.name,"save_sha256":hashlib.sha256(raw).hexdigest(),"key":keys[0],
            "flags":{str(k):flags[k] for k in [20,59,60,61,64,67,72,76,87,89,90,92,94,95,96,97,98,99,100]},
            "actors":positions,"source":"Kitrinx original Black Gate itemrec.h, item.cpp, u7npc.cpp and u7ibuf.cpp"}


def _estate_chest(path):
    raw = path.read_bytes()
    _, off, size = seed_directory(raw)["u7ibuf.dat"]
    items = raw[off:off + size]
    matches = []
    for handle in range(8, len(items), 8):
        _, xy, word, extension = struct.unpack_from("<4H", items, handle)
        if xy != 0x54cc or word not in (522, 800):
            continue
        if not 0 < extension <= len(items) - 8 or extension % 8:
            continue
        head, region, quality, _, position = struct.unpack_from("<H4B", items, extension)
        if (region, quality, position >> 4) != (99, 253, 6) or position & 7 >= 4:
            continue
        children, seen = [], set()
        while head:
            if not 0 < head <= len(items) - 8 or head % 8 or head in seen:
                raise ValueError("invalid original chest contents list")
            seen.add(head)
            nxt, parent, child, kind, attr = struct.unpack_from("<HHHBB", items, head)
            if parent != handle or kind & 7 not in (6, 7):
                raise ValueError("original chest child disagrees with its parent")
            children.append({"handle": head, "shape": child & 1023, "frame": child >> 10, "attribute": attr})
            head = nxt
        matches.append({"handle": handle, "shape": word, "world_xyz": [972, 2132, 6],
                        "key_quality": quality, "children": children})
    if len(matches) != 1:
        raise ValueError("expected one original estate chest")
    return matches[0]


def read_gate(path, tfa, expected_lift=0):
    raw = path.read_bytes()
    index = seed_directory(raw)
    _, off, size = index["itemnode.dat"]
    nodes = raw[off:off + size]
    _, off, size = index["u7ibuf.dat"]
    items = raw[off:off + size]
    x, y = 1102, 2217
    loaded = nodes[-5:-1].index(12 * (y // 256) + x // 256)
    chunk = loaded * 256 + (y % 256 // 16) * 16 + x % 256 // 16
    current = struct.unpack_from("<H", nodes, 6 + chunk * 2)[0]
    seen, matches = set(), []
    while current:
        if current in seen or current % 8 or current > len(items) - 8:
            raise ValueError("invalid native eastern gate chunk")
        seen.add(current)
        nxt, xy, shape, attr, quality = struct.unpack_from("<HHHBB", items, current)
        if xy == (y % 256 << 8 | x % 256) and shape == 271 and (attr & 7) == loaded:
            foot = tfa[3 * shape + 2]
            dx, dy = 1 + (foot & 7), 1 + (foot >> 3 & 7)
            if (dx, dy, attr >> 4) != (1, 4, expected_lift):
                raise ValueError("unrecognized original east-gate footprint")
            matches.append({"handle": current, "shape": shape, "frame": 0, "quality": quality,
                            "anchor": [x,y], "lift": attr >> 4, "cells": [[x, row] for row in range(y - dy + 1, y + 1)]})
        current = nxt
    if len(matches) != 1:
        raise ValueError("missing verified eastern gate")
    return matches[0]


def qualify_stable(session: Path, installation: Path) -> dict:
    """Bind the ordered native GUI saves to independently checked game inputs and live linked lists."""
    from .qualify import qualify

    refusal = qualify(session, installation)
    if refusal.get("same_session_reentry", {}).get("visible_outcome") != "acceptance":
        raise ValueError("missing the original, rendered acceptance branch")
    receipt = json.loads((session / "receipt.json").read_bytes())
    expected = [
        ("accepted", "world", 0, 0),
        ("stable-entry", "world", 1, 0),
        ("avatar-key", "inventory", 1, 0),
    ]
    mayor_report = {}
    if any(c["file"].startswith("mayor-key-report-") for c in receipt["checkpoints"]):
        expected.append(("mayor-key-report", "inventory", 1, 1))
        source = installation / "Assets/UltimaVII-Steam/STATIC/USECODE"
        mayor_report = _key_report(session, receipt, source.read_bytes())
    estate, gate = {}, {}
    if any(c["file"].startswith("estate-unlocked-") for c in receipt["checkpoints"]):
        expected.extend([("before-chest", "inventory", 1, 1), ("estate-unlocked", "inventory", 1, 1)])
    if any(c["file"].startswith("blocked-east-gate-") for c in receipt["checkpoints"]):
        expected.extend([("east-gate-before-password", "inventory", 1, 1), ("blocked-east-gate", "inventory", 1, 1)])
    states = []
    last_action = -1
    for label, location, clue, reported in expected:
        matches = [(i, a) for i, a in enumerate(receipt["actions"]) if
                   a["type"] == "state" and a.get("label") == label]
        if len(matches) != 1 or matches[0][0] <= last_action:
            raise ValueError("missing or unordered original native save action")
        last_action, action = matches[0]
        filename = f"{label}-GAME0{action['slot']}.U7"
        records = [c for c in receipt["checkpoints"] if c["file"] == filename]
        path = session / filename
        state = inspect_save(path)
        if (len(records) != 1 or records[0]["sha256"] != state["save_sha256"] or
                records[0]["bytes"] != path.stat().st_size):
            raise ValueError("original save differs from its recorded DOS export")
        if [state["flags"][k] for k in ("60", "61", "72", "89", "90")] != [clue, 0, reported, 0, 1]:
            raise ValueError("unexpected flags in original investigation checkpoint")
        key = state["key"]
        if key["location"] != location or (states and key["item_handle"] != states[0]["key"]["item_handle"]):
            raise ValueError("original ground and carried key do not agree")
        if location == "world" and key["world_xy"] != [1068, 2197]:
            raise ValueError("Trinsic stable ground key moved prematurely")
        if location == "inventory" and (key["actor_slot"] != 0 or key["parent_shapes"][0] != 801):
            raise ValueError("key did not enter the original Avatar's backpack")
        states.append({**state, "elapsed_ms": action["elapsed_ms"]})
        if label in ("before-chest", "estate-unlocked"):
            estate[label] = _estate_chest(path)
        if label in ("east-gate-before-password", "blocked-east-gate"):
            gate[label] = {"asset": read_gate(path, (installation / "Assets/UltimaVII-Steam/STATIC/TFA.DAT").read_bytes()),
                           "avatar_xy": state["actors"]["0"]["world_xy"], "save_sha256": state["save_sha256"],
                           "flag61": state["flags"]["61"], "elapsed_ms": action["elapsed_ms"]}
    if gate:
        before, after = gate["east-gate-before-password"], gate["blocked-east-gate"]
        if (before["asset"] != after["asset"] or before["avatar_xy"] != [1094,2217] or
                after["avatar_xy"] != [1101,2217] or before["flag61"] or after["flag61"]):
            raise ValueError("unexpected native pre-password east gate outcome")
        motion = [a for a in receipt["actions"] if before["elapsed_ms"] < a["elapsed_ms"] < after["elapsed_ms"]
                  and a["type"] == "click" and a.get("button", 0) == 1]
        if len(motion) != 1 or motion[0]["hold"] < 1000 or motion[0]["x"] <= .8:
            raise ValueError("missing sustained original eastward walk")
        gate["ordinary_walk"] = motion[0]
    if estate:
        before, after = estate["before-chest"], estate["estate-unlocked"]
        if (before["shape"], after["shape"]) != (522, 800) or before["handle"] != after["handle"]:
            raise ValueError("expected the same original chest to change from locked to unlocked")
        if before["children"] != after["children"] or [
                (c["shape"], c["frame"], c["attribute"]) for c in after["children"]] != [
                (955, 1, 8), (797, 0, 5), (644, 7, 228)]:
            raise ValueError("original estate chest evidence differs")
        estate["observation_frames"] = [
            f for f in receipt["frames"] if f["file"].endswith(("-open-investigation-chest.png",
                                                                   "-read-christophers-original-scroll.png"))]
        if len(estate["observation_frames"]) != 2:
            raise ValueError("original open-chest or readable-scroll frame missing")
    return {"schema": 1, "status": "passed", "edition": refusal["game"],
            "edition_source_sha256": refusal["edition_source_sha256"],
            "wasm_sha256": refusal["wasm_sha256"], "inputs_checked": refusal["inputs_checked"],
            "acceptance": refusal["same_session_reentry"], "ground_key_shape_frame_quality": [641, 0, 253],
            "checkpoints": states, "coverage": [c["save_file"] for c in states],
            "mayor_report": mayor_report, "estate_chest": estate, "closed_eastern_gate": gate}


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("checkpoint",type=Path)
    parser.add_argument("--installation", type=Path, help="Qualify a complete original stable investigation session")
    args=parser.parse_args()
    if args.installation:
        report = qualify_stable(args.checkpoint, args.installation)
        target = args.checkpoint / "stable-investigation-check.json"
    else:
        report = inspect_save(args.checkpoint)
        target = args.checkpoint.with_suffix(".investigation.json")
    target.write_text(json.dumps(report, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    print(target)
