"""Index field contacts from original U7MAP/U7CHUNKS words, before RLE underlay substitution."""

from collections import Counter
import hashlib
import json
import struct

from .terrain import TerrainSource, MAP_BYTES, _json_bytes
from .u7 import seed_directory
from .world import count_terrain_words


def field_contacts(world,chunks,tfa):
    TerrainSource(world,chunks)
    fields = {}
    data = bytearray()
    counts = Counter()
    for index,(chunk,) in enumerate(struct.iter_unpack("<H",world)):
        if chunk not in fields:
            words = struct.unpack_from("<256H",chunks,chunk*512)
            fields[chunk] = [(i,w&1023) for i,w in enumerate(words) if tfa[(w&1023)*3+1]&16]
        region,local = divmod(index,256)
        left = region%12*256+local%16*16
        top = region//12*256+local//16*16
        for i,shape in fields[chunk]:
            data.extend(struct.pack("<HHH",left+i%16,top+i//16,shape))
            counts[shape] += 1
    return data,counts


def produce_swamp(u7,output,story):
    static = u7/"STATIC"
    tfa = (static/"TFA.DAT").read_bytes()
    contacts,counts = field_contacts((static/"U7MAP").read_bytes(),(static/"U7CHUNKS").read_bytes(),tfa)
    monsters = (static/"MONSTERS.DAT").read_bytes()
    if len(monsters)!=1+25*monsters[0]:
        raise ValueError("Unsupported Black Gate monster table")
    immune = set()
    for at in range(1,len(monsters),25):
        if monsters[at+4]&1:
            immune.add(struct.unpack_from("<H",monsters,at)[0])
    seed = (static/"INITGAME.DAT").read_bytes()
    _,offset,size = seed_directory(seed)["npc.dat"]
    npc = seed[offset:offset+size]
    actors = {}
    for slot,row in story["actors"].items():
        shape = row["shape"]
        extent = tfa[shape*3+2]
        width,height = (extent&7)+1,((extent>>3)&7)+1
        if row["frame"]&32:
            width,height = height,width
        actors[slot] = {"width":width,"height":height,"poison_safe":shape in immune,
                        "flies":bool(npc[row["record_offset"]+51]&16)}
    spec = {"schema":1,"seed_sha256":hashlib.sha256(seed).hexdigest(),"source_counts":counts,
            "contacts_sha256":hashlib.sha256(contacts).hexdigest(),"actors":actors,
            "monsters_sha256":hashlib.sha256(monsters).hexdigest()}
    (output/"swamp-fields.bin").write_bytes(contacts)
    (output/"swamp.json").write_bytes(_json_bytes(spec))


def verify_swamp(directory):
    raw=(directory/"world-land.source").read_bytes()
    source=TerrainSource(raw[:MAP_BYTES],raw[MAP_BYTES:])
    tfa=(directory/"world-statics/tfa.dat").read_bytes()
    meta=json.loads((directory/"swamp.json").read_bytes())
    data=(directory/"swamp-fields.bin").read_bytes()
    if len(data)%6 or hashlib.sha256(data).hexdigest()!=meta["contacts_sha256"]:
        raise ValueError("Field index hash or length differs from manifest")
    seen=set()
    counts=Counter()
    for x,y,shape in struct.iter_unpack("<HHH",data):
        if ((x,y) in seen or source.tile(x,y)["shape"]!=shape or not tfa[3*shape+1]&16):
            raise ValueError(f"Field contact disagrees with source at {x},{y}")
        seen.add((x,y))
        counts[shape]+=1
    expected=Counter()
    for word,n in count_terrain_words(source.world,source.chunks).items():
        shape=word&1023
        if tfa[3*shape+1]&16:
            expected[shape]+=n
    if counts!=expected or counts!={int(k):v for k,v in meta["source_counts"].items()}:
        raise ValueError("Field index does not account for every original terrain contact")
    return {"status":"passed","raw_field_cells":len(seen),"source_shapes":dict(counts)}
