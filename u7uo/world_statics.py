"""Build native statics with source provenance for fixed and terrain placements."""

from collections import Counter, defaultdict
import hashlib
import json
import struct

from .terrain import MAP_BYTES, _json_bytes, fixed_inventory
from .u7 import flex_directory, usecode_inventory
from .walking import STATIC_RULES, _static_material, world_component_positions


MOUNTAINS = (195,196,395,396)
# Two stock boulders fill the original five lifts at the facet's four Z per lift.
BOULDER_BASE = (0x134f,0x1350,0x1351,0x1352,0x1353,0x1354,0x135d,0x135e)
BOULDER_CAP = tuple(range(0x1355,0x135d))


def mountain_material(shape, frames, tfa, text, names, tiledata):
    if tfa[shape*3:shape*3+3] != bytes((0xa8,0,0x1b)) or frames >= 0:
        raise ValueError(f"Changed mountain collision or frame format for shape {shape}")
    variants = []
    for frame in range(-frames):
        variant = (frame + 2*MOUNTAINS.index(shape)) % len(BOULDER_BASE)
        layers = []
        for art,height in ((BOULDER_BASE[variant],15),(BOULDER_CAP[variant],5)):
            rules = {shape:("mountain",art,"boulder",0x4040,height)}
            native = _static_material(shape,text,names,tiledata,rules)
            if native["flags"] != 0x4040:
                raise ValueError(f"Changed collision flags for boulder {art:#x}")
            layers.append(native)
        variants.append(layers)
    return {"name":"mountain","height":20,"frame_layers":variants}


def static_layers(material,frame):
    if "frame_layers" not in material:
        return [(material["id"],0)]
    base,cap = material["frame_layers"][frame]
    return [(base["id"],0),(cap["id"],base["height"])]


def produce_world_statics(u7, uo, output, census, land):
    static = u7/"STATIC"
    source = (output/"world-land.source").read_bytes()
    tiledata = (uo/"tiledata.mul").read_bytes()
    text = (static/"TEXT.FLX").read_bytes()
    names = flex_directory(text)
    tfa = (static/"TFA.DAT").read_bytes()
    bindings = {r["id"] for r in usecode_inventory((static/"USECODE").read_bytes())["records"]}
    frames = land["graphic_frame_counts"]
    seed = census["seed_sha256"]
    folder = output/"world-statics"
    folder.mkdir()
    terrain_defs = {}
    materials = {}
    blocks = defaultdict(bytearray)
    counts = Counter()
    reasons = Counter()
    families = Counter()
    sample_region = land.get("loader_sample_region")
    sample = []
    fixed_inputs = bytearray()
    fixed_archives = []
    for region, source_region in enumerate(census["regions"]):
        archive = (static/source_region["ifix"]).read_bytes()
        fixed = fixed_inventory(archive,region,seed)
        if fixed["source_sha256"] != source_region["ifix_sha256"]:
            raise ValueError("Fixed-object archive changed during world compilation")
        fixed_archives.append({"offset":len(fixed_inputs),"length":len(archive),"sha256":fixed["source_sha256"]})
        fixed_inputs.extend(archive)
        placements = [dict(o,family="IFIX") for o in fixed["objects"]]
        for slot in range(256):
            placement_offset = (region*256+slot)*2
            chunk, = struct.unpack_from("<H",source,placement_offset)
            if chunk not in terrain_defs:
                rows = []
                for i,word in enumerate(struct.unpack_from("<256H",source,MAP_BYTES+chunk*512)):
                    shape,frame = word & 1023,(word>>10)&31
                    if frames[shape]<0 or shape in STATIC_RULES:
                        rows.append((i,shape,frame))
                terrain_defs[chunk] = rows
            for i,shape,frame in terrain_defs[chunk]:
                x = region%12*256 + slot%16*16 + i%16
                y = region//12*256 + slot//16*16 + i//16
                placements.append({"id":f"terrain:{seed}:{x}:{y}","family":"U7CHUNKS","x":x,"y":y,"lift":0,
                                   "shape":shape,"frame":frame,"offset":chunk*512+2*i,"map_offset":placement_offset})
        for obj in placements:
            shape, family = obj["shape"],obj["family"]
            counts[family] += 1
            if shape in bindings:
                disposition = "requires-live-usecode"
            elif shape not in STATIC_RULES and not (shape in MOUNTAINS and family=="U7CHUNKS"):
                disposition = "unmapped-static-art"
            elif family=="IFIX" and tfa[shape*3+1]&15 != 14:
                disposition = "unqualified-fixed-object-class"
            elif obj["frame"]&31 >= abs(frames[shape]):
                disposition = "missing-source-frame"
            else:
                if shape not in materials:
                    materials[shape] = (mountain_material(shape,frames[shape],tfa,text,names,tiledata)
                                        if shape in MOUNTAINS else _static_material(shape,text,names,tiledata))
                material = materials[shape]
                layers = static_layers(material,obj["frame"])
                components = [(x,y,z+dz,art) for x,y,z in world_component_positions(obj,tfa,material)
                              for art,dz in layers]
                if any(not (0<=x<3072 and 0<=y<3072 and -128<=z<=127) for x,y,z,art in components):
                    disposition = "world-edge-or-height-needs-qualification"
                else:
                    disposition = "emitted"
                    if len(layers)==1:
                        obj["target_art"] = material["id"]
                    else:
                        obj["target_layers"] = layers
                    obj["native_records"] = []
                    for x,y,z,art in components:
                        block = x//8*384 + y//8
                        bucket = blocks[block]
                        obj["native_records"].append([block,len(bucket)//7])
                        bucket.extend(struct.pack("<HBBbH",art,x%8,y%8,z,0))
                        if y//256*12+x//256==sample_region:
                            sample.append({"x":x%256,"y":y%256,"id":art,"z":z,"hue":0})
            obj["disposition"] = disposition
            reasons[disposition] += 1
            families[(family,shape,obj["frame"],disposition)] += 1
        (folder/f"region-{region:02x}.json").write_bytes(_json_bytes(placements))
    index = bytearray()
    with (folder/"statics0.mul").open("wb") as stream:
        for i in range(384**2):
            records = blocks.get(i,b"")
            if len(records)>1024*7:
                raise ValueError(f"Native static limit exceeded at world block {i}")
            index.extend(struct.pack("<iii",stream.tell() if records else -1,len(records),0))
            stream.write(records)
    (folder/"staidx0.mul").write_bytes(index)
    (folder/"tfa.dat").write_bytes(tfa)
    (folder/"ifix.source").write_bytes(fixed_inputs)
    if sample_region is not None:
        profile = output/"world-land-sample"
        spec = json.loads((profile/"terrain.json").read_bytes())
        spec["statics"] = sample
        (profile/"terrain.json").write_bytes(_json_bytes(spec))
        local_index,local_data = bytearray(),bytearray()
        for bx in range(sample_region%12*32,sample_region%12*32+32):
            for by in range(sample_region//12*32,sample_region//12*32+32):
                records = blocks.get(bx*384+by,b"")
                local_index.extend(struct.pack("<iii",len(local_data) if records else -1,len(records),0))
                local_data.extend(records)
        (profile/"staidx0.mul").write_bytes(local_index)
        (profile/"statics0.mul").write_bytes(local_data)
    report = {"schema":1,"source_counts":dict(counts),"dispositions":dict(reasons),
              "fixed_archives":fixed_archives,"flat_overlay_shapes":sorted(STATIC_RULES),"mapped_materials":materials,
              "native_records":sum(len(b)//7 for b in blocks.values()),
              "occupied_native_blocks":len(blocks),"source_seed_sha256":seed,"sample_region":sample_region,
              "sample_native_records":len(sample),"family_counts":[[*k,n] for k,n in sorted(families.items())],
              "scope":"IFIX and U7CHUNKS fixtures. IREG and actors retain their separate live identity requirements."}
    if counts["IFIX"] != census["totals"]["fixed"] or sum(reasons.values()) != sum(counts.values()):
        raise ValueError("Fixed and terrain placement coverage does not reconcile")
    (folder/"summary.json").write_bytes(_json_bytes(report))
    return report


def read_native_blocks(directory):
    index = (directory/"staidx0.mul").read_bytes()
    data = (directory/"statics0.mul").read_bytes()
    if len(index) != 384**2*12:
        raise ValueError("Incorrect whole-world native static index length")
    blocks = {}
    consumed = 0
    for block,(start,size,reserved) in enumerate(struct.iter_unpack("<iii",index)):
        if not size and start==-1 and reserved==0:
            continue
        if start != consumed or not 0<size<=1024*7 or size%7 or reserved or start+size>len(data):
            raise ValueError(f"Invalid static index entry at world block {block}")
        blocks[block] = (start,size//7)
        consumed += size
    if consumed != len(data):
        raise ValueError("Native static bytes are unaccounted for")
    return data,blocks


def verify_world_statics(release):
    folder = release/"world-statics"
    report = json.loads((folder/"summary.json").read_bytes())
    land = json.loads((release/"world-land.json").read_bytes())
    tfa = (folder/"tfa.dat").read_bytes()
    if hashlib.sha256(tfa).hexdigest() != land["source_sha256"]["TFA.DAT"]:
        raise ValueError("Whole-world static footprints disagree with the source TFA file")
    raw,blocks = read_native_blocks(folder)
    source = (release/"world-land.source").read_bytes()
    archives = (folder/"ifix.source").read_bytes() if "fixed_archives" in report else None
    original_fixed_count = 0
    terrain_slots = {}
    overlays = set(report.get("flat_overlay_shapes",STATIC_RULES))
    owned = bytearray(len(raw)//7)
    reasons,source_counts = Counter(),Counter()
    for region in range(144):
        objects = json.loads((folder/f"region-{region:02x}.json").read_bytes())
        original_fixed = {}
        if archives is not None:
            a = report["fixed_archives"][region]
            original = archives[a["offset"]:a["offset"]+a["length"]]
            fixed = fixed_inventory(original,region,report["source_seed_sha256"])
            if a["sha256"]!=fixed["source_sha256"]:
                raise ValueError(f"Original object archive hash differs in region {region:02x}")
            original_fixed = {o["id"]:o for o in fixed["objects"]}
            original_fixed_count += len(original_fixed)
        expected_terrain = set()
        for slot in range(256):
            place = 2*(region*256+slot)
            chunk, = struct.unpack_from("<H",source,place)
            if chunk not in terrain_slots:
                words = struct.unpack_from("<256H",source,MAP_BYTES+chunk*512)
                terrain_slots[chunk] = [i for i,w in enumerate(words) if land["graphic_frame_counts"][w&1023]<0 or (w&1023) in overlays]
            expected_terrain.update((place,chunk*512+2*j) for j in terrain_slots[chunk])
        unique = set()
        for o in objects:
            shape = o["shape"]
            if o["id"] in unique or o["y"]//256*12+o["x"]//256!=region:
                raise ValueError("Duplicate or misplaced fixed-object identity")
            unique.add(o["id"])
            if o["family"]=="IFIX" and archives is not None:
                ref = original_fixed.pop(o["id"],None)
                if ref is None or any(o[k]!=v for k,v in ref.items()):
                    raise ValueError(f"Incorrect original IFIX provenance for {o['id']}")
            elif o["family"]=="U7CHUNKS":
                x,y = o["x"],o["y"]
                pos = (region*256 + ((y%256)//16)*16 + (x%256)//16)*2
                chunk, = struct.unpack_from("<H",source,pos)
                at = chunk*512+2*((y%16)*16+(x%16))
                word, = struct.unpack_from("<H",source,MAP_BYTES+at)
                if ((pos,at) not in expected_terrain or (pos,at)!=(o["map_offset"],o["offset"])
                        or (word&1023,(word>>10)&31,0)!=(shape,o["frame"],o["lift"])
                        or o["id"]!=f"terrain:{report['source_seed_sha256']}:{x}:{y}"):
                    raise ValueError(f"Incorrect original terrain provenance for {o['id']}")
                expected_terrain.remove((pos,at))
            reasons[o["disposition"]] += 1
            source_counts[o["family"]] += 1
            refs = o.get("native_records",[])
            if o["disposition"] != "emitted":
                if refs:
                    raise ValueError("Unresolved fixture has a native component")
                continue
            dims = tfa[3*shape+2]
            nx,ny = 1+(dims&7),1+((dims>>3)&7)
            if o["family"]=="IFIX" and o["frame"]&32:
                nx,ny = ny,nx
            height = 4*o["lift"]
            if o["family"]=="IFIX" and shape in (367,368,369,370,1014):
                height += 4*(tfa[3*shape]>>5)
            material = report["mapped_materials"][str(shape)]
            layers = static_layers(material,o["frame"])
            if "frame_layers" in material:
                if (shape not in MOUNTAINS or tfa[3*shape:3*shape+3]!=bytes((0xa8,0,0x1b))
                        or o.get("target_layers") != [list(layer) for layer in layers]):
                    raise ValueError(f"Mountain layers disagree with source fixture {o['id']}")
            expected = {(o["x"]-dx,o["y"]-dy,height+dz,art)
                        for dx in range(nx) for dy in range(ny) for art,dz in layers}
            for block,ordinal in refs:
                start,count = blocks[block]
                if not 0<=ordinal<count:
                    raise ValueError(f"Static ordinal outside native block for {o['id']}")
                offset = start+7*ordinal
                art,x,y,z,hue = struct.unpack_from("<HBBbH",raw,offset)
                pos = (block//384*8+x,block%384*8+y,z,art)
                if (owned[offset//7] or hue!=0
                        or x>=8 or y>=8 or pos not in expected):
                    raise ValueError(f"Native static differs from {o['id']} at world position {pos}")
                expected.remove(pos)
                owned[offset//7] = 1
            if expected:
                raise ValueError(f"Incomplete original footprint for {o['id']}")
        if original_fixed or expected_terrain:
            raise ValueError(f"Original placements were omitted in region {region:02x}")
    if (not all(owned) or len(owned)!=report["native_records"] or reasons!=report["dispositions"]
            or source_counts!=report["source_counts"]):
        raise ValueError("Unreconciled source object or native static component")
    return {"status":"passed","native_records":len(owned),"source_counts":dict(source_counts),
            "dispositions":dict(reasons),"sample_region":report["sample_region"],
            "original_ifix_records_verified":original_fixed_count,"sample_native_records":report["sample_native_records"]}


def explain_static(release, source_id):
    bits = source_id.split(":")
    if len(bits)==5 and bits[0]=="ifix":
        region = int(bits[2],16)
    elif len(bits)==4 and bits[0]=="terrain":
        x,y = map(int,bits[2:])
        if not (0<=x<3072 and 0<=y<3072):
            raise ValueError("Terrain ID is outside the source world")
        region = y//256*12+x//256
    else:
        return None
    if not 0<=region<144:
        raise ValueError("Static ID is outside the source world")
    folder = release/"world-statics"
    for obj in json.loads((folder/f"region-{region:02x}.json").read_bytes()):
        if obj["id"]==source_id:
            file = f"U7IFIX{region:02X}" if obj["family"]=="IFIX" else "U7CHUNKS"
            return {"id":source_id,"source":"STATIC/"+file,"object":obj,
                    "native_files":["world-statics/staidx0.mul","world-statics/statics0.mul"]}
    return None
