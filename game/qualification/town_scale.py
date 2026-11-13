"""Convert a 2x2 patch of original ground into one ClassicUO land diamond."""
import struct
import zlib
from functools import lru_cache
from PIL import Image, ImageChops

BOUNDS=(928,2080,1120,2352)
# Include the view beyond the investigation boundary at the maximum client zoom.
LANDSCAPE=(832,1984,1216,2448)
def map_offset(x,y):
    return ((x//8)*512+y//8)*196+4+3*((y%8)*8+x%8)

def reduce_land(facet,source_land,output,tiledata,land):
    from source import D,TerrainSource,archive,art_key,entries
    from u7uo.shore import PROJECTION
    art=output/'Art/Land'
    radar=bytearray((output/'radarcol.mul').read_bytes())
    def addr(i):return i//32*964+4+i%32*30
    available=iter(i for i in range(0x2000,0x4000) if not any(tiledata[addr(i):addr(i)+30])
                   and art_key(i) not in entries)
    @lru_cache(None)
    def texture(i):
        local=art/f'{i}.art'
        if local.exists():raw=local.read_bytes()
        else:
            off,head,n,_,_,_,compressed=entries[art_key(i)]
            raw=archive[off+head:off+head+n]
            if compressed:raw=zlib.decompress(raw)
        return struct.unpack('<1012H',raw[:2024])
    # Choose the source quadrant by position in the world plane, then sample
    # the matching point in its diamond. This preserves road and grass boundaries.
    lookup={xy:i for i,(xy,_) in enumerate(PROJECTION)}
    samples=[]
    for xy,_ in PROJECTION:
        x,y=xy%44,xy//44
        u=(x+y+1-22)/44
        v=(y-x+22)/44
        a,b=int(u>=0.5),int(v>=0.5)
        sx=2*x-21-22*(a-b);sy=2*y+1-22*(a+b)
        sy=min(43,max(0,sy));margin=21-sy if sy<22 else sy-22
        sx=min(43-margin,max(margin,sx))
        samples.append((a+2*b,lookup[sy*44+sx]))
    @lru_cache(None)
    def diamond(ids):
        if len(set(ids))==1:return ids[0]
        for start in (3,0x75):
            if all(start<=i<start+4 for i in ids):return ids[0]
        # Keep the scale of a stock material inside mixed grass/soil tiles.
        colors=[texture(ids[q])[sample] for q,sample in samples]
        i=next(available)
        (art/f'{i}.art').write_bytes(struct.pack('<1012H',*colors))
        dominant=max(ids,key=ids.count)
        tiledata[addr(i):addr(i)+30]=tiledata[addr(dominant):addr(dominant)+30]
        avg=sum((sum((v>>k)&31 for v in colors)//len(colors))<<k for k in (0,5,10))
        struct.pack_into('<H',radar,i*2,avg)
        return i
    terrain=TerrainSource((D/'U7MAP').read_bytes(),(D/'U7CHUNKS').read_bytes())
    def outside(x,y):
        cell=terrain.tile(x,y)
        shape,frame=cell['shape'],cell['frame']
        graphic=land.get((shape,frame),land.get((shape,frame&31)))
        if graphic is not None:return graphic,0
        if shape in (2,19,20,30,64,65):return 0xAA,0
        if shape in (49,50,51,63):return 0x75+frame%4,0
        # Under non-flat map shapes use the surrounding original ground.
        for dx,dy in ((0,-1),(-1,0),(1,0),(0,1),(-1,-1),(1,1)):
            near=terrain.tile(x+dx,y+dy)
            graphic=land.get((near['shape'],near['frame']))
            if graphic is not None:return graphic,0
        return 3+frame%4,0
    def cell(x,y):
        if BOUNDS[0]<=x<BOUNDS[2] and BOUNDS[1]<=y<BOUNDS[3]:
            return source_land.get((x,y)) or struct.unpack_from('<Hb',facet,map_offset(x,y))
        return outside(x,y)
    x0,y0,x1,y1=LANDSCAPE
    for y in range(y0,y1,2):
        for x in range(x0,x1,2):
            patch=[cell(x+dx,y+dy)
                   for dy in (0,1) for dx in (0,1)]
            ids=tuple(i for i,z in patch)
            struct.pack_into('<Hb',facet,map_offset(x//2,y//2),diamond(ids),max(z for i,z in patch))
    (output/'radarcol.mul').write_bytes(radar)

def rampart_statics(refs,rows,channels):
    # Stock wall faces run along the south/east edges of their UO tile.
    # A north/west rim uses the identical edge of the neighbouring tile.
    stone=set()
    rim=set()
    for r in refs:
        key=int(r['shape']),int(r['frame'])
        row=rows[key]
        masonry=r['layer']=='Terrain' and row['source_name']=='fortress'
        coping=r['layer']=='Fixed' and row['source_name']=='crenellations'
        if not (masonry or coping):continue
        x,y,lift=int(r['x']),int(r['y']),int(r['lift'])
        w,d=map(int,row['footprint'].split('×'))
        if masonry:
            z=lift*4
            height=int(row['native_height'])*4
            stone.update(((x-a)//2,(y-b)//2,z,height) for a in range(w) for b in range(d))
        else:
            rim.update((x-a,y-b,lift*4) for a in range(w) for b in range(d))

    deck={(x,y,z+height) for x,y,z,height in stone}
    # Keep free-standing rails (gate bridges and buildings) in their original placement.
    parapets={}
    for x,y,z in rim:
        cx,cy=x//2,y//2
        cell=(cx,cy,z)
        if cell not in deck or cell in channels:continue
        for dx,dy,bit in ((-1,0,2),(1,0,2),(0,-1,1),(0,1,1)):
            if (x+dx)//2==cx and (y+dy)//2==cy:continue
            if (cx+dx,cy+dy,z) in deck:continue
            edge=(cx-int(dx<0),cy-int(dy<0),z)
            if edge not in channels:parapets[edge]=parapets.get(edge,0)|bit

    tiles=set()
    faces={}
    for x,y,z,height in stone:
        south=(x,y+1,z,height) not in stone
        east=(x+1,y,z,height) not in stone
        if south or east:
            graphic=0x1a if south and east else 0x1c if south else 0x1b
            tiles.add((x,y,z,graphic))
            faces[x,y,z+height]=(graphic,height)
    # At a re-entrant bend both faces can extend away from their common
    # vertex. The stock post fills the seam between their far ends.
    for (x,y,top),(graphic,height) in list(faces.items()):
        if graphic not in (0x1a,0x1c):continue
        adjacent=faces.get((x-1,y+1,top))
        corner=(x-1,y,top)
        if adjacent and adjacent[0] in (0x1a,0x1b) and corner not in faces:
            tiles.add((x-1,y,top-height,0x1d))
            if corner in deck:faces[corner]=(0x1d,height)
    for (x,y,z),edges in parapets.items():
        tiles.add((x,y,z,{1:0x78,2:0x79,3:0x2d}[edges]))
        # Close the far corner when both rails extend away from this vertex.
        if edges&1 and parapets.get((x-1,y+1,z),0)&2:
            if (x-1,y,z) not in channels and (x-1,y,z) not in parapets:
                tiles.add((x-1,y,z,0x30))
    return deck,tiles,faces


def rampart_paver(paver,wall,height):
    # UO anchors both sprites at bottom centre. Preserve the stock wall cap
    # wherever it projects into the deck diamond at its actual elevation.
    offset=(paver.width//2-wall.width//2,paver.height+4*height-wall.height)
    overlap=Image.new('L',paver.size)
    overlap.paste(wall.getchannel('A'),offset)
    result=paver.copy()
    result.putalpha(ImageChops.subtract(paver.getchannel('A'),overlap))
    return result


def portcullis_channels(refs,rows):
    # The native floor boards stop one source tile short of the moving grille.
    # Each compact cell contains four source quadrants.
    channels={}
    for r in refs:
        row=rows[int(r['shape']),int(r['frame'])]
        if row['source_name']!='portcullis' or r['layer']!='World object':continue
        w,d=map(int,row['footprint'].split('×'))
        deck_z=4*(int(r['lift'])+int(row['native_height']))
        for a in range(w):
            for b in range(d):
                x,y=int(r['x'])-a,int(r['y'])-b
                cell=(x//2,y//2,deck_z)
                channels[cell]=channels.get(cell,0)|(1<<((x&1)+2*(y&1)))
    return channels


def deck_paver(sprite,channel):
    # Keep the stock diamond anchored. A missing quadrant is transparent
    # for both drawing and picking, including when the grille rises.
    out=sprite.copy()
    for y in range(44):
        for x in range(44):
            quadrant=int(x+y+1>=44)+2*int(y>=x)
            if channel&(1<<quadrant):out.putpixel((x,y),(0,0,0,0))
    return out


def compact_parts(parts):
    # Assemblies extend from their south-east anchor toward negative coordinates.
    # Match stock pieces to cells in that footprint, one representative per height.
    placed={}
    for g,x,y,z,h in parts:
        key=(int(x/2),int(y/2),z)
        placed.setdefault(key,(g,*key,h))
    return tuple(placed.values())

def door_leaf(row,stock):
    from town_facing import pack, piece
    width,depth=map(int,row['footprint'].split('×'))
    frame=int(row['frame'])&31
    family=0x675 if frame//8==2 or frame%8>=4 else 0x6A5 if frame//8==1 else 0x6D5
    along_x=width>depth
    double=max(width,depth)==4
    if frame%4!=1:
        near=family+(2 if along_x and double else 0 if along_x else 8)
        if not double:return near,stock(near)
        far=piece(family,-1,0) if along_x else piece(family+10,0,-1)
        return near,pack((far,piece(near)),stock)

    # Native open shapes already lie on the other axis. Swing each stock leaf
    # into that axis about its original outer jamb and leave the passage clear.
    near=family+(9 if along_x else 3)
    far=piece(family+11,0,-2) if along_x else piece(family+1,-2,0)
    def at_hinge(graphic,hue):
        sprite=stock(graphic,hue)
        left,top,right,bottom=sprite.getbbox()
        # Stock open frames include padding for UO's own object movement.
        # Use their visible bottom tip as the hinge in the native doorway.
        foot=sprite.getchannel('A').crop((0,bottom-1,sprite.width,bottom)).getbbox()
        hinge=(foot[0]+foot[2])//2
        radius=max(hinge-left,right-hinge)
        out=Image.new('RGBA',(2*radius,bottom-top))
        out.paste(sprite.crop((left,top,right,bottom)),(radius+left-hinge,0))
        return out
    return near,pack((far,piece(near)) if double else (piece(near),),at_hinge)
