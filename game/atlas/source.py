import sys, hashlib, struct, mmap, zlib
from pathlib import Path
from collections import defaultdict
from functools import lru_cache
sys.dont_write_bytecode = True
sys.path.insert(0, r'C:\Users\veditoid\Documents\ChatGPT\Ultima Offline')
from u7uo.u7 import flex_directory, seed_directory
from u7uo.terrain import TerrainSource, fixed_inventory
from u7uo.containers import decode_member
from u7uo.shore import art_key
from u7uo.gump_overlay import _directory
from frames import rle as face_frame
from PIL import Image
D = Path('E:/UltimaOffline/Assets/UltimaVII-Steam/STATIC')
U = Path('E:/UltimaOffline/Assets/UO-Classic')
def member(b, i):
    start,size = flex_directory(b)[i]
    return b[start:start+size]
def load_catalog():
    seed = (D/'INITGAME.DAT').read_bytes()
    seedhash = hashlib.sha256(seed).hexdigest()
    tfa = (D/'TFA.DAT').read_bytes()
    names = (D/'TEXT.FLX').read_bytes()
    result = defaultdict(list)
    def add(shape,frame,x,y,z,source,offset):
        if 944<=x<1112 and 2112<=y<2272:
            result[shape,frame].append((x,y,z,source,offset))
    for rid in (99,100):
        filename=f'U7IFIX{rid:02X}'
        for o in fixed_inventory((D/filename).read_bytes(),rid,seedhash)['objects']:
            add(o['shape'],o['frame'],o['x'],o['y'],o['lift'],filename,o['offset'])
        name=f'u7ireg{rid:02x}'
        _,start,size=seed_directory(seed)[name]
        for o in decode_member(seed[start:start+size],tfa,start,seedhash,rid)[0]:
            if 'world_xy' in o: add(o['shape'],o['frame'],*o['world_xy'],o['lift'],name,o['offset'])
    terr=TerrainSource((D/'U7MAP').read_bytes(),(D/'U7CHUNKS').read_bytes())
    for y in range(2112,2272):
        for x in range(944,1112):
            o=terr.tile(x,y);add(o['shape'],o['frame'],x,y,0,'U7CHUNKS',o['chunks_offset'])
    return result,{i:member(names,i).rstrip(b'\0').decode('cp437') for i in set(k[0] for k in result)}
shapes=(D/'SHAPES.VGA').read_bytes()
palette=member((D/'PALETTES.FLX').read_bytes(),0)
@lru_cache(None)
def u7(shape,frame):
    raw=member(shapes,shape)
    if int.from_bytes(raw[:4],'little') in (len(raw),len(raw)-1):
        size,=struct.unpack_from('<I',raw); raw=raw[:size]
        w,h,p,_,origin=face_frame(raw,frame&31)
        reflect=frame>=32
    else:
        w=h=8; p=raw[frame*64:frame*64+64];origin=(7,7); reflect=False
        assert len(p)==64
    image=Image.new('RGBA',(w,h))
    image.putdata([(0,0,0,0) if i is None else (*[c*255//63 for c in palette[3*i:3*i+3]],255) for i in p])
    if reflect: image=image.transpose(Image.Transpose.TRANSPOSE);origin=origin[::-1]
    return image,origin
tiledata=(U/'tiledata.mul').read_bytes()
def tile(i):
    off=512*964+i//32*1316+4+i%32*41
    return tiledata[off+21:off+41].split(b'\0')[0].decode('cp1252','replace').strip(),tiledata[off+20]
art_file=open(U/'artLegacyMUL.uop','rb')
archive=mmap.mmap(art_file.fileno(),0,access=mmap.ACCESS_READ)
entries=_directory(archive,5)[2]
@lru_cache(None)
def uo(i):
    off,header,len_stored,original,key,_,flag=entries[art_key(0x4000+i)]
    data=archive[off+header:off+header+len_stored]
    if flag==1: data=zlib.decompress(data)
    assert len(data)==original,(i,flag)
    _,w,h=struct.unpack_from('<IHH',data)
    assert w*h and w<=2048 and h<=2048
    im=Image.new('RGBA',(w,h));pix=im.load()
    for y in range(h):
        pos=8+h*2+struct.unpack_from('<H',data,8+y*2)[0]*2
        x=0
        while True:
            skip,count=struct.unpack_from('<HH',data,pos);pos+=4
            if not (skip or count):break
            x+=skip;assert x+count<=w
            for color, in struct.iter_unpack('<H',data[pos:pos+count*2]):
                pix[x,y]=tuple(((color>>k)&31)*255//31 for k in (10,5,0))+(255,)
                x+=1
            pos+=count*2
    return im
if __name__=='__main__':
    cat,names=load_catalog()
    for i,n in sorted(names.items()):print(i,n,','.join(str(f) for s,f in sorted(cat) if s==i))


