"""Emit reusable native UO land blocks for the original 3072-square world."""

from collections import Counter
import hashlib
import json
import struct

from .terrain import CHUNK_BYTES, MAP_BYTES, UNRESOLVED_LAND, TerrainSource, _avatar_seed, _json_bytes, _resolve_rule, encode_land_mul
from .u7 import flex_directory
from .walking import GROUND, STATIC_RULES
from .water import water_material
from .world import count_terrain_words
from .world_substrate import chunk_underlays, shape_frames, substrate_chunks
from .shore import FIRST as SHORE_FIRST, SHAPES as SHORE_SHAPES, SWAMP_FRAMES, VOID_FRAMES, produce_shores


def compile_world_blocks(world, chunks, materials):
    """The signed index maps UO block coordinates to canonical 196-byte native blocks."""
    TerrainSource(world, chunks)
    if any(first <= UNRESOLVED_LAND < first + variants for first, variants in materials.values()):
        raise ValueError("A source material overlaps the unresolved land tile")
    stride = 384
    index = [-1] * (stride * stride)
    pool = {}
    chunk_cache = {}
    counts = Counter()
    regions = [0] * 144
    for placement, (chunk_id,) in enumerate(struct.iter_unpack("<H", world)):
        if chunk_id not in chunk_cache:
            words = struct.unpack_from("<256H", chunks, chunk_id * CHUNK_BYTES)
            blocks = []
            for dy in (0, 8):
                for dx in (0, 8):
                    tiles = []
                    for y in range(dy, dy + 8):
                        for word in words[16*y+dx:16*y+dx+8]:
                            shape, frame = word & 1023, (word >> 10) & 31
                            if shape in materials:
                                first, variants = materials[shape]
                                tiles.append((first + frame % variants, 0))
                            else:
                                tiles.append((UNRESOLVED_LAND, 0))
                    if any(land != UNRESOLVED_LAND for land, _ in tiles):
                        native = encode_land_mul(8, 8, tiles)
                        blocks.append(pool.setdefault(native, len(pool)))
                    else:
                        blocks.append(-1)
            chunk_cache[chunk_id] = blocks, Counter(word & 1023 for word in words)
        blocks, local = chunk_cache[chunk_id]
        counts.update(local)
        region, within = divmod(placement, 256)
        x = region % 12 * 32 + within % 16 * 2
        y = region // 12 * 32 + within // 16 * 2
        for quadrant, entry in enumerate(blocks):
            index[(x + quadrant % 2)*stride + y + quadrant//2] = entry
            regions[region] += entry >= 0
    return struct.pack(f"<{len(index)}i", *index), b"".join(pool), counts, regions


def region_map(region, index, pool):
    if not 0 <= region < 144 or len(index) != 384**2 * 4 or len(pool) % 196:
        raise ValueError("Invalid world block index or region")
    bx, by = region % 12 * 32, region // 12 * 32
    result = bytearray()
    for x in range(bx,bx+32):
        for y in range(by,by+32):
            slot, = struct.unpack_from("<i",index,4*(x*384+y))
            if not 0 <= slot < len(pool)//196:
                raise ValueError(f"Cannot materialize source region {region:02X}: missing or invalid block at {x},{y}")
            result.extend(pool[slot*196:(slot+1)*196])
    return result


def explain_world_cell(directory, x, y, report):
    raw = (directory/"world-land.source").read_bytes()
    original = TerrainSource(raw[:MAP_BYTES],raw[MAP_BYTES:]).tile(x,y)
    # Keep the high bit of the U7CHUNKS word independently. Exult's original
    # two-byte terrain reader selects the five-bit frame for rendering.
    raw_frame = original["frame"]
    original.update(frame=raw_frame & 31,raw_word=original["shape"] | raw_frame<<10,
                    high_bit=raw_frame>>5)
    donor = None
    shape, frame = original["shape"], original["frame"]
    missing = "Source shape has no land rule"
    if "graphic_frame_counts" in report:
        start = original["chunk_id"] * CHUNK_BYTES
        words = struct.unpack_from("<256H",raw,MAP_BYTES+start)
        local = y%16*16+x%16
        j = chunk_underlays(words,report["graphic_frame_counts"])[local]
        if j is None:
            available = abs(report["graphic_frame_counts"][shape])
            missing = (f"Shape {shape} requests frame {frame}, but SHAPES.VGA contains "
                       f"{available} frames for this shape" if frame >= available else
                       f"No drawable flat underlay in source chunk {original['chunk_id']}")
            shape = None
        elif j != local:
            shape,frame = words[j]&1023,(words[j]>>10)&31
            donor = {"source_position":[x//16*16+j%16,y//16*16+j//16],
                     "chunks_offset":start+2*j,"shape":shape,"frame":frame}
    material = next((r for r in report["materials"] if r["shape"] == shape),None)
    block = (x//8)*384+y//8
    with (directory/"world-land.idx").open("rb") as stream:
        stream.seek(block*4)
        slot, = struct.unpack("<i",stream.read(4))
    result = {"id":f"tile:{x},{y}","source_position":[x,y],"source":original,
              "source_files":{"map_offset":"STATIC/U7MAP","chunks_offset":"STATIC/U7CHUNKS"},
              "material_rule":material,"world_block":block,"native_block_emitted":slot>=0}
    if (directory/"swamp.json").is_file():
        at=original["shape"]*3+1
        with (directory/"world-statics/tfa.dat").open("rb") as stream:
            stream.seek(at)
            field=bool(stream.read(1)[0]&16)
        result["terrain_contact"]={"original_shape":original["shape"],"tfa_offset":at,"field":field,
                                   "swamp_poison_roll":field and original["shape"] in (22,67,334,335)}
    if donor:
        result["underlay_donor"] = donor
    if slot < 0:
        result["diagnostic"] = (missing if material is None
                                else "This tile has a rule but its block contains unresolved cells")
        return result
    at = slot*196+4+3*((y%8)*8+x%8)
    with (directory/"world-land.mul").open("rb") as stream:
        stream.seek(at)
        land,z = struct.unpack("<Hb",stream.read(3))
    if material is None and report.get("schema") == 3 and (land,z) == (UNRESOLVED_LAND,0):
        result["diagnostic"] = missing + ". The facet uses impassable padding at this position."
        result["padding"] = {"pool_offset":at,"land_id":land,"z":z}
        return result
    if material is None or (land,z)!=(material["first_land_id"]+frame%material["variants"],0):
        raise ValueError("World land pool differs from the original material or frame")
    result["native"] = {"pool_offset":at,"land_id":land,"z":z}
    shore_path = directory/"shore-art.json"
    if SHORE_FIRST<=land<SHORE_FIRST+32*len(SHORE_SHAPES)+sum(SWAMP_FRAMES.values())+VOID_FRAMES and shore_path.is_file():
        frames = json.loads(shore_path.read_bytes())["frames"]
        art = frames[land-SHORE_FIRST]
        if (art["slot"],art["shape"],art["frame"])!=(land,shape,frame):
            raise ValueError("Shore art identity differs from its source substrate")
        result["shore_graphic"] = art
    return result


def verify_world_land(directory):
    report = json.loads((directory/"world-land.json").read_bytes())
    raw = (directory/"world-land.source").read_bytes()
    source = TerrainSource(raw[:MAP_BYTES],raw[MAP_BYTES:])
    for name, payload in (("U7MAP",source.world),("U7CHUNKS",source.chunks)):
        if hashlib.sha256(payload).hexdigest() != report["source_sha256"][name]:
            raise ValueError(f"World land source differs from the input {name}")
    if "graphic_frame_counts" in report:
        source = TerrainSource(source.world,substrate_chunks(source.chunks,report["graphic_frame_counts"]))
    index = (directory/"world-land.idx").read_bytes()
    pool = (directory/"world-land.mul").read_bytes()
    if len(index) != 4*384**2 or len(pool)%196:
        raise ValueError("Malformed world land block storage")
    materials = {r["shape"]:(r["first_land_id"],r["variants"]) for r in report["materials"]}
    mixed_format = report.get("schema") == 3
    if mixed_format and (report["unresolved_land_id"] != UNRESOLVED_LAND or
                         any(a <= UNRESOLVED_LAND < a+v for a,v in materials.values())):
        raise ValueError("Ambiguous world land padding")
    expected = {}
    used = set()
    matched = missing = matched_cells = mixed = 0
    for i,(slot,) in enumerate(struct.iter_unpack("<i",index)):
        bx,by = divmod(i,384)
        x,y = bx*8,by*8
        chunk = source.tile(x,y)["chunk_id"]
        key = (chunk,bx%2,by%2)
        if key not in expected:
            cells = []
            mapped = 0
            for dy in range(8):
                for dx in range(8):
                    tile = source.tile(x+dx,y+dy)
                    rule = materials.get(tile["shape"])
                    if rule:
                        cells.append((rule[0] + (tile["frame"] & 31) % rule[1],0))
                        mapped += 1
                    elif mixed_format:
                        cells.append((UNRESOLVED_LAND,0))
            block = (bytes(4) + b"".join(struct.pack("<Hb",*c) for c in cells)
                     if mapped and len(cells)==64 else None)
            expected[key] = block,mapped
        block,mapped = expected[key]
        if block is None and slot == -1:
            missing += 1
        elif slot >= 0 and block == pool[slot*196:(slot+1)*196]:
            matched += 1
            matched_cells += mapped
            mixed += mapped < 64
            used.add(slot)
        else:
            raise ValueError(f"World block at source {x},{y} differs from the declared material rules")
    if (matched != report["emitted_blocks"] or matched+missing != report["total_blocks"]
            or len(used) != len(pool)//196 or len(used)!=report["distinct_native_blocks"]
            or mixed_format and (matched_cells != report["cells_with_land_rule"]
                                 or mixed != report["mixed_blocks"]
                                 or matched-mixed != report["fully_mapped_blocks"])):
        raise ValueError("World land coverage or native block pool does not reconcile")
    return {"status":"passed","blocks_matched_to_original_positions":matched,"unresolved_blocks":missing,
            "distinct_native_blocks":len(used),"matched_cells":matched_cells,"mixed_blocks":mixed,
            "fully_mapped_blocks":matched-mixed,"padding_cells":384**2*64-matched_cells}


def produce_world_land(u7, uo, output):
    static = u7 / "STATIC"
    world, chunks, text, tfa = [(static / name).read_bytes() for name in ("U7MAP","U7CHUNKS","TEXT.FLX","TFA.DAT")]
    tiledata = (uo / "tiledata.mul").read_bytes()
    if len(tiledata) != 3188736 or len(tfa) < 3072:
        raise ValueError("Unsupported U7 shape or UO tiledata layout for world land")
    names = flex_directory(text)
    materials = {}
    rules = dict(GROUND)
    for shape in range(150):
        offset, length = names[shape]
        name = text[offset:offset+length].rstrip(b"\0").lower()
        if name == b"cavefloor":
            rules[shape] = ("cavefloor","cave",0x245)
        elif name in (b"rut",b"sidewalk",b"sandy ground"):
            target, first = {b"rut":("dirt",0x79),b"sidewalk":("flagstone",0x201),
                             b"sandy ground":("sand",0x16)}[name]
            rules[shape] = (name.decode("ascii"),target,first)
        elif name in (b"grassy mud",b"sandy grass",b"grass") and shape not in rules:
            rules[shape] = (name.decode("ascii"),"dirt" if name == b"grassy mud" else "grass",
                            0x79 if name == b"grassy mud" else 3)
    water = water_material(tiledata)
    for shape in range(150):
        if tfa[3*shape] & 0x10:
            materials[shape] = water
        elif shape in rules:
            r = _resolve_rule(shape,text,names,tiledata,rules)
            materials[shape] = (r["first_land_id"],r["variants"])
    graphics = (static/"SHAPES.VGA").read_bytes()
    materials.update(produce_shores(static,uo,graphics,text,tfa,tiledata,output))
    frames = shape_frames(graphics)
    substrate = substrate_chunks(chunks,frames)
    index, pool, counts, regions = compile_world_blocks(world,substrate,materials)
    if sum(counts.values()) != 3072**2:
        raise ValueError("World land occurrence reconciliation failed")
    source_counts = Counter()
    for word,n in count_terrain_words(world,chunks).items():
        source_counts[word&1023] += n
    mixed_slots = {offset//196 for offset in range(0,len(pool),196)
                   if any(cell == UNRESOLVED_LAND for cell,_ in struct.iter_unpack("<Hb",pool[offset+4:offset+196]))}
    incomplete_regions = set()
    mixed = 0
    for i,(slot,) in enumerate(struct.iter_unpack("<i",index)):
        if slot < 0 or slot in mixed_slots:
            bx,by = divmod(i,384)
            incomplete_regions.add(by//32*12+bx//32)
            mixed += slot >= 0
    report = {"schema":3,"width":3072,"height":3072,"native_block_bytes":196,
              "unresolved_land_id":UNRESOLVED_LAND,"mixed_blocks":mixed,"fully_mapped_blocks":sum(regions)-mixed,
              "index_format":"signed little-endian int32 at blockX * 384 + blockY; -1 means unresolved",
              "block_pool":"world-land.mul","block_index":"world-land.idx",
              "source_sha256":{k:hashlib.sha256(v).hexdigest() for k,v in
                               zip(("U7MAP","U7CHUNKS","TEXT.FLX","TFA.DAT","tiledata.mul"),(world,chunks,text,tfa,tiledata))},
              "total_blocks":384**2,"emitted_blocks":sum(regions),"distinct_native_blocks":len(pool)//196,
              "graphic_frame_counts":frames,"rle_placement_count":sum(n for s,n in source_counts.items() if frames[s]<0),
              "source_cells":3072**2,"cells_with_land_rule":sum(counts[s] for s in materials),
              "emitted_blocks_by_superchunk":regions,
              "materials":[{"shape":s,"first_land_id":a,"variants":v,"occurrences":counts[s],
                            "requires_static_overlay":s in STATIC_RULES} for s,(a,v) in sorted(materials.items()) if counts[s]],
              "unresolved":[{"shape":s if s!=1023 else None,"occurrences":n} for s,n in counts.most_common() if s not in materials],
              "scope":"Mapped substrate cells are emitted at source coordinates. Unresolved cells receive impassable padding; entirely unresolved blocks have no pool entry."}
    report["source_sha256"]["SHAPES.VGA"] = hashlib.sha256(graphics).hexdigest()
    (output/"world-land.mul").write_bytes(pool)
    (output/"world-land.idx").write_bytes(index)
    (output/"world-land.source").write_bytes(world + chunks)
    complete = [i for i in range(144) if i not in incomplete_regions]
    if complete:
        start = _avatar_seed((static/"INITGAME.DAT").read_bytes())["position"]
        start_region = start[1]//256*12 + start[0]//256
        region = start_region if start_region in complete else complete[0]
        folder = output/"world-land-sample"
        folder.mkdir()
        # Build the oracle table by direct source coordinate reads, separately
        # from chunk deduplication, UO block addressing and pool materialization.
        source = TerrainSource(world,substrate)
        left, top = region%12*256, region//12*256
        cells = []
        for y in range(256):
            for x in range(256):
                tile = source.tile(left+x,top+y)
                first, variants = materials[tile["shape"]]
                cells.append({"x":x,"y":y,"z":0,"land_id":first+tile["frame"]%variants})
        (folder/"map0.mul").write_bytes(region_map(region,index,pool))
        (folder/"staidx0.mul").write_bytes(struct.pack("<iii",-1,0,0)*1024)
        (folder/"statics0.mul").write_bytes(b"")
        (folder/"terrain.json").write_bytes(_json_bytes({"width":256,"height":256,"source_region":region,
                                                        "source_origin":[left,top],"cells":cells,"statics":[]}))
        report["loader_sample_region"] = region
    (output/"world-land.json").write_bytes(_json_bytes(report))
    return report
