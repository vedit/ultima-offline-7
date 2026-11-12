"""Bind Trinsic scenery and schedule furniture to their original IREG placements."""
import json
import re
import struct

from .gump_overlay import BLOCK, ENTRY, _directory
from .shore import ARCHIVE, art_key
from .u7 import flex_directory, usecode_inventory


# A post and the two orientations of a rail. Keep the stock item heights intact.
ART = {0x7000:0x85f, 0x7001:0x85d, 0x7002:0x85e}


def fence_art(assets):
    path = assets/ARCHIVE
    original = path.read_bytes()
    capacity, last, entries = _directory(original, 5)
    tiles = bytearray((assets/"tiledata.mul").read_bytes())
    aliases = {int(v) for line in (assets/"art.def").read_text(encoding="ascii",errors="replace").splitlines()
               for v in re.findall(r"\b\d+\b", line.partition("#")[0])}
    block_offset = len(original)
    header = bytearray(original[:28])
    struct.pack_into("<I", header, 24, len(entries)+len(ART))
    records = bytearray(capacity*ENTRY.size)
    payload = bytearray()
    if len(ART)>capacity:
        raise ValueError("Item art directory block too small")
    for i,(private,stock) in enumerate(ART.items()):
        target = 512*964 + private//32*1316 + 4 + private%32*41
        source = 512*964 + stock//32*1316 + 4 + stock%32*41
        tile = bytearray(tiles[source:source+41])
        key = art_key(private+0x4000)
        if (key in entries or private+0x4000 in aliases or any(tiles[target:target+41]) or
                (assets/"Art/Statics"/f"{private}.art").exists()):
            raise ValueError(f"Fence art slot {private:#x} already occupied")
        if (tile[21:].rstrip(b"\0") != b"wooden fence" or tile[20]!=6 or
                not struct.unpack_from("<Q",tile)[0]&0x40):
            raise ValueError("Expected solid six-Z stock fence donor")
        tile[20] = 8
        tiles[target:target+41] = tile
        off, size, packed, raw, _, checksum, flag = entries[art_key(stock+0x4000)]
        dest = block_offset+BLOCK.size+len(records)+len(payload)
        ENTRY.pack_into(records,i*ENTRY.size,dest,size,packed,raw,key,checksum,flag)
        payload.extend(original[off:off+size+packed])
    # The stager owns this private copy. Append through a replacement to preserve immutable inputs.
    out = bytearray(original)
    out[:len(header)] = header
    struct.pack_into("<Q",out,last+4,block_offset)
    out.extend(BLOCK.pack(len(ART),0)+records+payload)
    final = _directory(out,5)[2]
    if any(final[k]!=v for k,v in entries.items()):
        raise ValueError("A previous art entry changed while installing fences")
    for private,stock in ART.items():
        p,n,m,*_ = final[art_key(private+0x4000)]
        q,h,k,*_ = entries[art_key(stock+0x4000)]
        if out[p:p+n+m] != original[q:q+h+k]:
            raise ValueError("Fence overlay pixels differ from stock art")
    for file,data in ((path,out),(assets/"tiledata.mul",tiles)):
        temp = file.with_suffix(".fence-tmp")
        with temp.open("xb") as f:
            f.write(data)
        temp.replace(file)


def town_fixtures(proof, assets, static, seed):
    tfa = (static/"TFA.DAT").read_bytes()
    weights = (static/"WGTVOL.DAT").read_bytes()
    text = (static/"TEXT.FLX").read_bytes()
    names = flex_directory(text)
    scripts = {r["id"] for r in usecode_inventory((static/"USECODE").read_bytes())["records"]}
    for shape,expected in ((420,b"\x48\x04\x00"), (378,b"\x48\x04\x01")):
        off,size = names[shape]
        if (text[off:off+size].rstrip(b"\0") != b"fence" or tfa[3*shape:3*shape+3]!=expected or
                weights[2*shape] or shape in scripts):
            raise ValueError("Unqualified fence material or Usecode binding")
    left, top, right, bottom = seed["gate_query_bounds"]
    seat_art = (0xB31, 0xB2F, 0xB2E, 0xB30)  # N, E, S, W in ClassicUO chair.txt
    for shape, label, flags, weight in ((873,b"chair",b"\x48\x04\x00",80),(292,b"seat",b"\x48\x02\x00",0)):
        off,size = names[shape]
        if (text[off:off+size].rstrip(b"\0") != label or tfa[shape*3:shape*3+3] != flags or
                weights[2*shape] != weight or shape not in scripts):
            raise ValueError("Unqualified source chair material")
    fences, beds, seats = [], [], []
    for sy in range(top//256,(bottom-1)//256+1):
        for sx in range(left//256,(right-1)//256+1):
            region = proof / f"world-ireg/u7ireg{sy*12+sx:02x}.json"
            for obj in json.loads(region.read_bytes())["objects"]:
                shape = obj["shape"]
                if obj["edge"]!="world" or shape not in (420,378,1011,696,873,292):
                    continue
                x,y = obj["world_xy"]
                if not (left<=x<right and top<=y<bottom):
                    continue
                row = {k:obj[k] for k in ("id","shape","world_xy","lift","frame")}
                if shape in (1011,696):
                    beds.append(row)
                elif shape in (873,292):
                    if obj["kind"]!="simple":
                        raise ValueError("Unexpected source seat record")
                    facing = obj["frame"] & 3
                    dx,dy = ((0,-1),(1,0),(0,1),(-1,0))[facing]
                    seats.append({**row, "quality_byte":obj["quality_byte"], "offset":obj["offset"],
                                  "art":seat_art[facing], "sitting_xy":[x+dx,y+dy], "movable":shape==873})
                else:
                    if obj["kind"]!="simple":
                        raise ValueError("Unexpected fence object record")
                    size = tfa[shape*3+2]
                    w,h = 1+(size&7),1+((size>>3)&7)
                    if obj["frame"]&32:
                        w,h = h,w
                    fences.append({**row,"footprint":[w,h],"art":0x7000 if shape==420 else 0x7001 if w>1 else 0x7002})
    if fences:
        fence_art(assets)
    # AreaScan visits chunks bottom-right first, retaining IREG list order within each chunk.
    seats.sort(key=lambda row:(-int(row["world_xy"][1]//16),-int(row["world_xy"][0]//16),row["offset"]))
    seed.update(schedule_beds=beds, schedule_seats=seats, town_fences=fences, fence_art=ART if fences else {})
