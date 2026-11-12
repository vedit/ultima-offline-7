"""Project original flat terrain frames into private native UO land diamonds."""

import hashlib
import json
import re
import struct
import zlib

from .gump_overlay import BLOCK, ENTRY, _directory
from .terrain import _json_bytes
from .u7 import flex_directory


ARCHIVE = "artLegacyMUL.uop"
FIRST = 0x2000
SHAPES = (14,15,29,84,*range(85,110),112)
FORDS = {14,15,84,112}
SWAMP_FRAMES = {22:30,67:32}
VOID_SHAPE = 12
VOID_FRAMES = 4
FRAME_SIZE = 2024
MASK32 = 0xffffffff


def _rot(v, count):
    v &= MASK32
    return ((v << count) | (v >> (32-count))) & MASK32


def art_key(slot):
    """UOP lookup3 hash, with the secondary word in the high half."""
    name = f"build/artlegacymul/{slot:08d}.tga".encode("ascii")
    a = b = c = 0xdeadbeef + len(name)
    while len(name)>12:
        x,y,z = struct.unpack_from("<3I",name)
        a,b,c = (a+x)&MASK32,(b+y)&MASK32,(c+z)&MASK32
        for rotation in (4,6,8,16,19,4):
            a = ((a-c)&MASK32) ^ _rot(c,rotation)
            c = (c+b)&MASK32
            a,b,c = b,c,a
        name = name[12:]
    x,y,z = struct.unpack("<3I",name.ljust(12,b"\0"))
    a,b,c = (a+x)&MASK32,(b+y)&MASK32,(c+z)&MASK32
    for rotation in (14,11,25,16,4,14,24):
        c = ((c^b)-_rot(b,rotation))&MASK32
        a,b,c = b,c,a
    return (a<<32)|b  # After seven rotations, a is final b and b is final c.


def _projection():
    result = []
    for y in range(44):
        margin = 21-y if y<22 else y-22
        for x in range(margin,44-margin):
            sx = min(7,max(0,(x+y-21)*8//44))
            sy = min(7,max(0,(y-x+22)*8//44))
            result.append((y*44+x,sy*8+sx))
    return result


PROJECTION = _projection()


def compose(frame, palette, dirt, water):
    raw = bytearray(FRAME_SIZE)
    rgba = bytearray(44*44*4)
    sums = [0,0,0]
    for i,(screen,source) in enumerate(PROJECTION):
        ink = frame[source]
        if 74<=ink<=87:
            color = water[i]
        elif 138<=ink<=147:
            color = dirt[i]
        else:
            r,g,b = palette[3*ink:3*ink+3]
            if max(r,g,b)>63:
                raise ValueError(f"Invalid VGA color for shore ink {ink}")
            color = ((r//2)<<10) | ((g//2)<<5) | (b//2)
        struct.pack_into("<H",raw,2*i,color)
        channels = [(color>>shift)&31 for shift in (10,5,0)]
        for channel,value in enumerate(channels):
            sums[channel] += value
            rgba[screen*4+channel] = value*255//31
        rgba[screen*4+3] = 255
    radar = sum((v//len(PROJECTION))<<shift for v,shift in zip(sums,(10,5,0)))
    return raw,hashlib.sha256(rgba).hexdigest(),radar


def produce_shores(static, uo, shapes, text, tfa, tiledata, output):
    archive = (uo/ARCHIVE).read_bytes()
    entries = _directory(archive,5)[2]
    palettes = (static/"PALETTES.FLX").read_bytes()
    start,size = flex_directory(palettes)[0]
    palette = palettes[start:start+size]
    if len(palette)!=768:
        raise ValueError("Invalid original VGA palette")
    graphics,names = flex_directory(shapes),flex_directory(text)
    donors = {}
    for first,label,flags in ((0x79,b"dirt",0),(0xa8,b"water",0xc0)):
        for slot in range(first,first+4):
            entry = entries[art_key(slot)]
            pos,header,stored,original,_,_,compression = entry
            at = slot//32*964+4+slot%32*30
            actual,_,name = struct.unpack_from("<QH20s",tiledata,at)
            if actual!=flags or name.rstrip(b"\0")!=label or compression or stored!=original or stored<FRAME_SIZE:
                raise ValueError(f"Unqualified stock shore donor {slot}")
            donors[slot] = struct.unpack_from("<1012H",archive,pos+header)
    materials = {}
    rows = []
    pool = bytearray()
    for shape in (*SHAPES,*SWAMP_FRAMES,VOID_SHAPE):
        name = {22:"swamp",67:"muck",VOID_SHAPE:"void"}.get(shape,"ford" if shape in FORDS else "muddy bank")
        frames = VOID_FRAMES if shape==VOID_SHAPE else SWAMP_FRAMES.get(shape,32)
        expected_tfa = bytes((0,16,0)) if shape in SWAMP_FRAMES else bytes(3)
        offset,length = graphics[shape]
        at,n = names[shape]
        if (length!=frames*64 or text[at:at+n].rstrip(b"\0").lower()!=name.encode()
                or tfa[shape*3:shape*3+3]!=expected_tfa):
            raise ValueError(f"Unqualified flat shore shape {shape}")
        first = FIRST+len(rows)
        materials[shape] = (first,frames)
        for frame in range(frames):
            slot = first+frame
            at = slot//32*964+4+slot%32*30
            if art_key(slot) in entries or any(tiledata[at:at+30]):
                raise ValueError(f"Reserved shore slot {slot} is occupied")
            source = offset+64*frame
            dirt,water = 0x79+frame%4,0xa8+frame%4
            pixels=shapes[source:source+64]
            raw,digest,radar = compose(pixels,palette,donors[dirt],donors[water])
            row=dict(shape=shape,frame=frame,name=name,slot=slot,source_offset=source,
                     rgba_sha256=digest,radar=radar)
            if shape==VOID_SHAPE:
                # DOS blits these four uniform flats from SHAPES.VGA. The source
                # has no solid/water/field flag. Only frame 0 uses a cycling ink.
                ink=(226,175,173,171)[frame]
                if pixels!=bytes([ink])*64:
                    raise ValueError(f"Unexpected source void frame {frame}")
                row.update(palette_index=ink,palette_rgb6=list(palette[3*ink:3*ink+3]))
            else:
                row.update(dirt=dirt,water=water)
            rows.append(row)
            pool.extend(raw)
    spec = {"schema":3,"source_sha256":{k:hashlib.sha256(v).hexdigest() for k,v in
            (("SHAPES.VGA",shapes),("PALETTES.FLX",palettes),(ARCHIVE,archive),("tiledata.mul",tiledata))},
            "palette":0,"frames":rows,"pool_sha256":hashlib.sha256(pool).hexdigest(),
            "palette_animation":"static phase zero"}
    (output/"shore-art.mul").write_bytes(pool)
    (output/"shore-art.json").write_bytes(_json_bytes(spec))
    return materials


def stage_shores(proof, assets):
    spec = json.loads((proof/"shore-art.json").read_bytes())
    pool = (proof/"shore-art.mul").read_bytes()
    rows = spec["frames"]
    shapes = [(s,f) for s in SHAPES for f in range(32)]
    if spec["schema"] not in (1,2,3):
        raise ValueError("Unknown private land art schema")
    if spec["schema"]>=2:
        shapes.extend((s,f) for s,n in SWAMP_FRAMES.items() for f in range(n))
    if spec["schema"]>=3:
        shapes.extend((VOID_SHAPE,f) for f in range(VOID_FRAMES))
    if (len(rows)!=len(shapes) or len(pool)!=len(rows)*FRAME_SIZE or
            hashlib.sha256(pool).hexdigest()!=spec["pool_sha256"]):
        raise ValueError("Invalid compiled shore art pool")
    stock = (assets/ARCHIVE).read_bytes()
    tiles = bytearray((assets/"tiledata.mul").read_bytes())
    radar = bytearray((assets/"radarcol.mul").read_bytes())
    for name,data in ((ARCHIVE,stock),("tiledata.mul",tiles)):
        if hashlib.sha256(data).hexdigest()!=spec["source_sha256"][name]:
            raise ValueError(f"Shore art inputs changed: {name}")
    capacity,last,original = _directory(stock,5)
    aliases = (assets/"art.def").read_text(encoding="ascii",errors="replace")
    references = {int(n) for line in aliases.splitlines() for n in
                  re.findall(r"\b\d+\b",line.partition("#")[0].partition("}")[0])}
    block = len(stock)
    out = bytearray(stock)
    struct.pack_into("<I",out,24,len(original)+len(rows))
    struct.pack_into("<Q",out,last+4,block)
    records = bytearray(capacity*ENTRY.size)
    payload = bytearray()
    metadata = struct.pack("<HHQ",3,8,0)
    for i,row in enumerate(rows):
        slot = FIRST+i
        key = art_key(slot)
        if (row["slot"]!=slot or (row["shape"],row["frame"])!=shapes[i] or
                key in original or slot in references or (assets/"Art/Land"/f"{slot}.art").exists()):
            raise ValueError(f"Invalid or shadowed shore slot {slot}")
        pos = block+BLOCK.size+len(records)+len(payload)
        index = i%capacity
        ENTRY.pack_into(records,index*ENTRY.size,pos,len(metadata),FRAME_SIZE,FRAME_SIZE,key,zlib.adler32(metadata),0)
        payload.extend(metadata)
        payload.extend(pool[i*FRAME_SIZE:(i+1)*FRAME_SIZE])
        at = slot//32*964+4+slot%32*30
        struct.pack_into("<QH20s",tiles,at,0,0,row["name"].encode("ascii"))
        struct.pack_into("<H",radar,2*slot,row["radar"])
        if index+1==capacity or i+1==len(rows):
            following = block+BLOCK.size+len(records)+len(payload)
            out.extend(BLOCK.pack(index+1,following if i+1<len(rows) else 0)+records+payload)
            block = following
            records = bytearray(capacity*ENTRY.size)
            payload.clear()
    after = _directory(out,5)[2]
    if any(after.get(key)!=entry for key,entry in original.items()):
        raise ValueError("Private shore art changed a stock archive entry")
    # Replace each staged file. This also keeps retail inodes intact on a hardlinked stage.
    for name,data in ((ARCHIVE,out),("tiledata.mul",tiles),("radarcol.mul",radar)):
        target = assets/name
        tmp = target.with_suffix(".shore-tmp")
        with tmp.open("xb") as stream:
            stream.write(data)
        tmp.replace(target)
    return {"frames":len(rows),"first_slot":FIRST,"stock_entries_preserved":len(original)}
