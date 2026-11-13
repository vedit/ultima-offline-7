import sys,struct,hashlib
from pathlib import Path
from collections import defaultdict,Counter
sys.dont_write_bytecode=True
BASE=Path(__file__).resolve().parent
ATLAS=BASE.parent
sys.path.insert(0,str(ATLAS))
from source import D,U,member,flex_directory,seed_directory,decode_member,fixed_inventory,TerrainSource,shapes,palette,uo,tile,tiledata,archive,entries,art_key
from frames import rle
from u7uo.actor import actor_table
from u7uo.world import schedule_entries
from u7uo.world_substrate import shape_frames
from PIL import Image
from functools import lru_cache
BOUNDS=(928,2080,1120,2352)
def inside(x,y):return BOUNDS[0]<=x<BOUNDS[2] and BOUNDS[1]<=y<BOUNDS[3]
def digest(p):
    with p.open('rb') as inp:return hashlib.file_digest(inp,'sha256').hexdigest()
counts=shape_frames(shapes)
text=(D/'TEXT.FLX').read_bytes(); names=[member(text,i).rstrip(b'\x00').decode('cp437').strip() for i in range(1024)]
tfa=(D/'TFA.DAT').read_bytes()
@lru_cache(None)
def src(s,f):
    count=counts[s];raw=member(shapes,s)
    base=f if count<0 and f<abs(count) else f&31
    assert base<abs(count),(s,f,count)
    if count<0:
        w,h,p,_,origin=rle(raw[:int.from_bytes(raw[:4],'little')],base)
    else:
        w=h=8;origin=(7,7);p=raw[base*64:base*64+64]
    im=Image.new('RGBA',(w,h))
    im.putdata([(0,0,0,0) if v is None else (*[min(255,x*255//63) for x in palette[v*3:v*3+3]],255) for v in p])
    if count<0 and base!=f:im=im.transpose(Image.Transpose.TRANSPOSE);origin=origin[::-1]
    return im,origin
def census():
    records=defaultdict(list); inputs=['SHAPES.VGA','TEXT.FLX','PALETTES.FLX','U7MAP','U7CHUNKS','TFA.DAT','INITGAME.DAT','SCHEDULE.DAT']
    def record(s,f,x,y,z,layer,file,off,owner=''):
        records[s,f].append((x,y,z,layer,file,off,owner))
    terr=TerrainSource((D/'U7MAP').read_bytes(),(D/'U7CHUNKS').read_bytes())
    for y in range(BOUNDS[1],BOUNDS[3]):
        for x in range(BOUNDS[0],BOUNDS[2]):
            o=terr.tile(x,y);record(o['shape'],o['frame'],x,y,0,'Terrain','U7CHUNKS',o['chunks_offset'])
    seed=(D/'INITGAME.DAT').read_bytes();sd=seed_directory(seed);h=hashlib.sha256(seed).hexdigest()
    for sy in range(BOUNDS[1]//256,(BOUNDS[3]-1)//256+1):
        for sx in range(BOUNDS[0]//256,(BOUNDS[2]-1)//256+1):
            reg=sy*12+sx;file=f'U7IFIX{reg:02X}';inputs.append(file)
            for o in fixed_inventory((D/file).read_bytes(),reg,h)['objects']:
                if inside(o['x'],o['y']):record(o['shape'],o['frame'],o['x'],o['y'],o['lift'],'Fixed',file,o['offset'])
            file=f'u7ireg{reg:02x}';_,off,size=sd[file];locations={}
            objs=decode_member(seed[off:off+size],tfa,off,h,reg)[0]
            for o in objs:
                loc=(*o['world_xy'],o['lift']) if 'world_xy' in o else locations[o['parent']]
                locations[o['id']]=loc
                if inside(*loc[:2]):record(o['shape'],o['frame'],*loc,{'inventory':'Contained','world':'World object','barge_member':'Barge member'}[o['edge']],file,o['offset'],o['parent'] or '')
                if inside(*loc[:2]) and o['kind']=='egg':
                    raw=bytes.fromhex(o['payload_hex'])
                    if raw[4]&15==1:
                        asset=int.from_bytes(raw[10:12],'little');record(asset&1023,asset>>10,*loc,'Spawner target',file,o['offset'],o['id'])
    _,off,size=sd['npc.dat'];actors=actor_table(seed[off:off+size],tfa,include_inventory=True)[1]
    schedules=defaultdict(list)
    for ent in schedule_entries((D/'SCHEDULE.DAT').read_bytes()):
        if inside(*ent['world_xy']):schedules[ent['npc_slot']].append(ent)
    for o in actors:
        if not o['placed']:continue
        loc=o['source_position'];slot=o['npc_slot'];owner=f"{o['name']} (NPC {slot})"
        if inside(*loc[:2]):layer='Actor'
        elif slot in schedules:loc=(*schedules[slot][0]['world_xy'],None);layer='Scheduled visitor'
        else:continue
        record(o['shape'],o['frame'],*loc,layer,'npc.dat',o['record_offset'],owner)
        for it in o['inventory']:record(it['shape'],it['frame'],*loc,'Actor inventory','npc.dat',it['record_offset'],owner+f" / parent {it['parent_offset']}")
    from trade import vendor_records
    vendor_records((D/'USECODE').read_bytes(),actors,record)
    inputs.append('USECODE')
    return records,inputs
if __name__=='__main__':
    rec,_=census(); print(len(rec),'pairs',sum(map(len,rec.values())),'references',len({s for s,f in rec}),'shapes')
    for s in sorted({s for s,f in rec}):
        print(s,names[s],counts[s],','.join(str(f) for sh,f in sorted(rec) if s==sh))



