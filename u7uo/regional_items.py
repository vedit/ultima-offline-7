"""Compile original IREG ownership trees that can use native UO item graphics."""

from collections import Counter, defaultdict
import hashlib
import json
import struct

from .terrain import UNRESOLVED_LAND
from .u7 import flex_directory, usecode_inventory


# Native art is a presentation substitution. Preserve the original frame and
# record separately for gameplay, including qualities that distinguish instances.
RULES = {
    588: ("swamp boots", "boots", (0x170b,0x170c), 5),
    203: ("small rock", "rock", (0x1771,0x1773,0x1774), 4),
    415: ("garbage", "garbage", (0x10ee,0x10ef,0x10f0,0x10f1), 4),
    628: ("cup", "ceramic mug", (0x995,0x9ca), 2),
    703: ("cannon ball", "cannon ball", (0xe73,), 2),
    717: ("plate", "plate", (0x9d7,), 4),
    824: ("pitcher", "pitcher", (0x9d6,), 2),
    994: ("tongs", "tongs", (0xfbb,0xfbc), 4),
    800: ("chest", "wooden chest", (0xe42,0xe43), 6),
    801: ("backpack", "backpack", (0xe75,), 6),
    802: ("bag", "bag", (0xe76,), 6),
    803: ("basket", "basket", (0x9b1,), 6),
    804: ("crate", "crate", (0xe3c,), 6),
    819: ("barrel", "barrel", (0xe77,), 6),
}


def read(path):
    return json.loads(path.read_bytes())


def write(path, value):
    path.write_text(json.dumps(value,sort_keys=True,separators=(",",":"))+"\n",encoding="utf-8",newline="\n")


def materials(u7, uo):
    static = u7/"STATIC"
    text = (static/"TEXT.FLX").read_bytes()
    names = flex_directory(text)
    tfa = (static/"TFA.DAT").read_bytes()
    weights = (static/"WGTVOL.DAT").read_bytes()
    tiledata = (uo/"tiledata.mul").read_bytes()
    from .story_seed import ready_slot
    if ready_slot((static/"READY.DAT").read_bytes(),588)["slot"]!=11:
        raise ValueError("Source swamp boots are not assigned to the Black Gate feet slot")
    bound = {r["id"] for r in usecode_inventory((static/"USECODE").read_bytes())["records"]}
    result = {}
    for shape,(source_name,target_name,arts,cls) in RULES.items():
        pos,size = names[shape]
        if (text[pos:pos+size].rstrip(b"\0").decode("ascii").lower()!=source_name or
                tfa[3*shape+1]&15!=cls or shape in bound):
            raise ValueError(f"Unqualified source label, class or Usecode binding for regional shape {shape}")
        graphics = []
        for art in arts:
            at = 512*964+art//32*1316+4+art%32*41
            flags, = struct.unpack_from("<Q",tiledata,at)
            if shape==588 and (tiledata[at+9]!=3 or not flags&0x400000):
                raise ValueError("Native swamp boots graphic lacks a wearable shoe layer")
            if tiledata[at+21:at+41].split(b"\0",1)[0].decode("ascii").lower()!=target_name:
                raise ValueError(f"Unrecognized UO art for {source_name} at {art:#x}")
            if bool(flags&0x200000)!=(cls==6):
                raise ValueError(f"Native container flag differs for {source_name}")
            graphics.append({"id":art,"flags":flags,"height":tiledata[at+20],"tiledata_offset":at})
        result[str(shape)]={"name":source_name,"uo_name":target_name,"class":cls,"art":graphics,
                            "weight_tenths":weights[shape*2],"volume":weights[shape*2+1],"tfa":tfa[3*shape:3*shape+3].hex()}
    return result


def disposition(group, rules, frames, reserved, land_id):
    if any(row["id"] in reserved for row in group):
        return "existing-import"
    for row in group:
        material = rules.get(str(row["shape"]))
        if not material:
            return f"unmapped-shape:{row['shape']}"
        if row["edge"]=="barge_member" or row["kind"] not in ("simple","container"):
            return "unsupported-object-kind"
        if (row["frame"]&31)>=abs(frames[row["shape"]]):
            return "missing-source-frame"
    if land_id is None or land_id==UNRESOLVED_LAND:
        return "unresolved-land"
    if bytes.fromhex(rules[str(group[0]["shape"])]["tfa"])[2]&63:
        return "world-footprint-needs-composite"
    return "live"


def compile_placements(directory, rules):
    story = read(directory/"story-seed.json")
    reserved = {r["id"] for r in read(directory/"container.json")["objects"]}
    for key in ("eggs","gate_objects","investigation_items"):
        reserved.update(r["id"] for r in story.get(key,[]))
    for tree in story.get("investigation_chests",[]):
        reserved.update(r["id"] for r in tree["objects"])
    overrides = {}
    for filename in ("walking/terrain.json","water/terrain.json"):
        patch = read(directory/filename)
        ox,oy = patch["source_origin"]
        overrides.update({(ox+c["x"],oy+c["y"]):c["land_id"] for c in patch["cells"]})
        reserved.update(s["source_id"] for s in patch["statics"] if s.get("source_id"))
    index = (directory/"world-land.idx").read_bytes()
    pool = (directory/"world-land.mul").read_bytes()
    frames = read(directory/"world-land.json")["graphic_frame_counts"]
    emitted, roots = [], {}
    counts = Counter()
    for region in range(144):
        member = f"u7ireg{region:02x}"
        groups = defaultdict(list)
        for row in read(directory/"world-ireg"/f"{member}.json")["objects"]:
            groups[row["root"] or row["id"]].append(row)
        outcomes = {}
        for group in groups.values():
            root = group[0]
            x,y = root["world_xy"]
            slot, = struct.unpack_from("<i",index,4*((x//8)*384+y//8))
            land = overrides.get((x,y))
            if land is None and slot>=0:
                land, = struct.unpack_from("<H",pool,slot*196+4+3*((y%8)*8+x%8))
            reason = disposition(group,rules,frames,reserved,land)
            outcomes[str(root["offset"])]=reason
            counts[reason]+=len(group)
            if reason!="live":
                continue
            for row in group:
                material = rules[str(row["shape"])]
                arts = material["art"]
                emitted.append({"id":row["id"],"offset":row["offset"],"member":member,"parent":row["parent"],
                                "ordinal":row["ordinal"],"kind":row["kind"],"shape":row["shape"],"frame":row["frame"],
                                "payload":row["payload_hex"],"xy":row.get("world_xy",row.get("gump_xy")),
                                "lift":row["lift"],"land":land if row["edge"]=="world" else None,
                                "art":arts[(row["frame"]&31)%len(arts)]["id"]})
        roots[member]=outcomes
    coverage={"records":sum(counts.values()),"dispositions":dict(sorted(counts.items())),"roots":roots}
    return {"schema":1,"seed_sha256":story["seed_sha256"],"materials":rules,"objects":emitted},coverage


def produce_regional_items(directory,u7,uo):
    live,coverage = compile_placements(directory,materials(u7,uo))
    write(directory/"world-live.json",live)
    write(directory/"world-live-coverage.json",coverage)
    return len(live["objects"])


def verify_regional_items(directory):
    live = read(directory/"world-live.json")
    coverage = read(directory/"world-live-coverage.json")
    rebuilt,expected = compile_placements(directory,live["materials"])
    if live!=rebuilt or coverage!=expected or coverage["records"]!=read(directory/"world.json")["totals"]["movable"]:
        raise ValueError("Regional import records, ownership or dispositions differ from the original catalog")
    rows = live["objects"]
    return {"status":"passed","catalog_records":coverage["records"],"live_records":len(rows),
            "roots":sum(r["parent"] is None for r in rows),"inventory_links":sum(r["parent"] is not None for r in rows),
            "containers":sum(r["kind"]=="container" for r in rows),"regions":len({r["member"] for r in rows}),
            "sha256":hashlib.sha256((directory/"world-live.json").read_bytes()).hexdigest()}
