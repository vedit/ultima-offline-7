"""Build a private ClassicUO overlay from the reviewed Trinsic atlas."""
import csv
import hashlib
import json
import re
import shutil
import struct
import sys
from house_walls import compact_house_walls, fit_house_window, wall_face
from functools import lru_cache
from town_facing import layout, pack, roof_tiles, sign_sprite, stair_runs, reflected_sprite, wall_joins, fence_joins, tool_sprite, key_sprite, roof_edge_art
from collections import defaultdict
from town_scale import BOUNDS, LANDSCAPE, compact_parts, deck_paver, door_leaf, portcullis_channels, rampart_paver, rampart_statics, reduce_land
from pathlib import Path

from PIL import Image
from play import ROOT, RELEASE
from install_paths import ATLAS_OUTPUT as ATLAS, GAME_SOURCE

BASE = RELEASE/'assets'
OUT = ROOT/'town-stables-data'
HEIGHT_BLOCKS = 512
TILE_START = 512 * 964

def table(name):
    with (ATLAS/name).open(encoding='utf-8-sig',newline='') as stream:
        return list(csv.DictReader(stream))

def encode_sprite(image):
    image=image.convert('RGBA')
    w,h=image.size
    pixels=image.load()
    offsets,words=[],[]
    for y in range(h):
        offsets.append(len(words))
        x=end=0
        while x<w:
            while x<w and not pixels[x,y][3]: x+=1
            start=x
            colors=[]
            while x<w and pixels[x,y][3]:
                r,g,b,_=pixels[x,y]
                colors.append(0x8000 | (r>>3)<<10 | (g>>3)<<5 | (b>>3))
                x+=1
            if colors:
                words.extend((start-end,len(colors),*colors))
                end=x
        words.extend((0,0))
    return struct.pack('<Ihh',0,w,h)+struct.pack(f'<{len(offsets)+len(words)}H',*offsets,*words)

def stable_victim_sprite(sprite):
    # ClassicUO anchors static art at bottom center. Keep the rotation pivot
    # at the body's center, then move it up one 44-pixel compact land diamond.
    turned=sprite.rotate(-45,Image.Resampling.NEAREST,expand=True)
    padding=44-(turned.height-sprite.height)//2
    out=Image.new('RGBA',(turned.width,turned.height+padding))
    out.alpha_composite(turned,(0,0))
    return out

def ground_art(rows,base,output,tiledata):
    """Project native grass, soil and cobble boundaries onto stock land textures."""
    import zlib
    from source import entries,archive,art_key
    from u7uo.shore import PROJECTION
    radar=bytearray((base/'radarcol.mul').read_bytes())
    folder=output/'Art/Land'
    folder.mkdir(parents=True,exist_ok=True)
    def address(i):return (i//32)*964+4+(i%32)*30
    available=iter(i for i in range(0x3000,0x4000) if art_key(i) not in entries and
                   not any(tiledata[address(i):address(i)+30]))
    @lru_cache(None)
    def texture(graphic):
        off,head,size,_,_,_,compressed=entries[art_key(graphic)]
        raw=archive[off+head:off+head+size]
        if compressed:raw=zlib.decompress(raw)
        return struct.unpack('<1012H',raw[:2024])
    result={}
    private={}
    for (shape,frame),row in rows.items():
        name=row['source_name']
        if name not in ('grass','mud','dirt','grassy mud','cobblestone') or not row['uo_id'].startswith('land '):continue
        with Image.open(ATLAS/'images'/(row['source_image']+'.png')) as im:
            rgb=list(im.convert('RGB').getdata())
        if len(rgb)!=64:continue
        # The atlas contains blank frames as well. Preserve their original fallbacks.
        if not any(any(p) for p in rgb):continue
        variant=(shape+frame)%4
        grass,soil,stone=3+variant,0x75+variant,0x3EB
        mask=tuple(grass if g>r and g>b else stone if name=='cobblestone' and
                   max(r,g,b)-min(r,g,b)<16 and r>0 else soil for r,g,b in rgb)
        values=set(mask)
        if len(values)==1:
            result[shape,frame]=mask[0]
            continue
        if mask not in private:
            id=next(available)
            colors=[texture(mask[src])[i] for i,(_,src) in enumerate(PROJECTION)]
            (folder/f'{id}.art').write_bytes(struct.pack('<1012H',*colors))
            src=address(int(row['uo_id'].split()[1],16))
            dest=address(id)
            tiledata[dest:dest+30]=tiledata[src:src+30]
            avg=sum((sum((v>>k)&31 for v in colors)//len(colors))<<k for k in (0,5,10))
            struct.pack_into('<H',radar,id*2,avg)
            private[mask]=id
        result[shape,frame]=private[mask]
    (output/'radarcol.mul').write_bytes(radar)
    return result


COMPACT=ROOT/'town-battlement-data'

def fitted_window(base):
    """Fit the stock window for the backing wall's material and axis."""
    if base is None:return None
    return {7:14,8:15,0x1b:0x23,0x1c:0x22,0x133:0x13a,0x134:0x13b}.get(wall_face(base))

def build(output=OUT,compact=False):
    # Read the same stock archive as the review atlas. Suppress caches in its source folder.
    sys.dont_write_bytecode=True
    sys.path.insert(0,str(GAME_SOURCE/'atlas'))
    from source import uo, U
    hues=(U/'hues.mul').read_bytes()
    @lru_cache(None)
    def stock(graphic,hue=0):
        im=uo(graphic)
        if not hue:return im
        h=hue-1
        palette=struct.unpack_from('<32H',hues,(h//8)*708+4+(h%8)*88)
        rgb=[tuple(((v>>k)&31)*255//31 for k in (10,5,0)) for v in palette]
        result=im.copy()
        result.putdata([(*rgb[r>>3],a) if a else (0,0,0,0) for r,g,b,a in im.getdata()])
        return result

    output.mkdir(exist_ok=True)
    art=output/'Art/Statics'
    art.mkdir(parents=True,exist_ok=True)
    manifest=json.loads((ATLAS/'sources.json').read_bytes())
    for name in ('mapping.csv','references.csv','outfits.csv'):
        assert hashlib.sha256((ATLAS/name).read_bytes()).hexdigest()==manifest['output_sha256'][name]
    rows=table('mapping.csv')
    by_key={(int(r['shape']),int(r['frame'])):r for r in rows}
    refs=table('references.csv')
    tiledata=bytearray((BASE/'tiledata.mul').read_bytes())
    def address(i): return TILE_START+(i//32)*1316+4+(i%32)*41
    # Use unused entries within the stock archive index range. Never replace a named tile.
    spare=iter(i for i in range(0xbd00,0xf400) if not any(tiledata[address(i):address(i)+41]))
    catalog={}
    private={}
    geometries={}
    land=ground_art(by_key,BASE,output,tiledata)
    carried={}
    open_doors={}
    # Sort displaced art at its painted ground contact. A split is measured in
    # sprite columns, so both the renderer and pixel picker can use the same cut.
    depth_profiles={}
    def private_art(sig,template,name,height,parts=(),pixels=None,digest=None):
        if sig not in private:
            graphic=next(spare)
            private[sig]=graphic
            if pixels is None:
                if parts:pixels=pack(parts,stock)
                else:
                    image=ATLAS/'images'/(digest+'.png')
                    assert hashlib.sha256(image.read_bytes()).hexdigest().startswith(digest)
                    with Image.open(image) as png:pixels=png.convert('RGBA')
            (art/f'{graphic}.art').write_bytes(encode_sprite(pixels))
            addr=address(graphic)
            base=address(template)
            tiledata[addr:addr+41]=tiledata[base:base+41]
            flags=int.from_bytes(tiledata[addr:addr+8],'little') & ~(1<<24)
            tiledata[addr:addr+8]=flags.to_bytes(8,'little')
            tiledata[addr+20]=int(height)*4
            tiledata[addr+21:addr+41]=name.encode('ascii','replace')[:19].ljust(20,b'\0')
        return private[sig]

    for row in rows:
        key=int(row['shape']),int(row['frame'])
        ident=row['uo_id']
        match=re.search(r'0x([0-9a-fA-F]+)',ident)
        template=int(match[1],16) if match else 0
        layers=[(int(i,16),int(x),int(y),int(z),int(h or '0',16))
                for i,x,y,z,h in re.findall(r'0x([0-9A-Fa-f]+)@\((-?\d+),(-?\d+),(-?\d+)\)(?:/hue 0x([0-9A-Fa-f]+))?',ident)]
        if ident.startswith('land '):
            land.setdefault(key,template)
            continue
        if not row['target_image'] or ident.startswith('body '): continue
        original=tuple(layers)
        parts=layout(row,original)
        if compact and row['source_name']=='crenellations':
            w,d=map(int,row['footprint'].split('×'))
            rail=0x2d if w==d else 0x78 if w>d else 0x79
            parts=tuple((rail,-a,-b,0,0) for a in range(w) for b in range(d))
        sign=sign_sprite(row,stock)
        tool=tool_sprite(row,by_key.get((key[0],0),row),ATLAS/'images')
        mirrored=None
        if key[1]>=32 and sign is None and tool is None and not original and not parts:
            mirrored=reflected_sprite(row,by_key.get((key[0],key[1]-32)),ATLAS/'images')
        if compact and key[0] in (211,270,376):
            template,pixels=door_leaf(row,stock)
            span=max(map(int,row['footprint'].split('×')))
            signature=('compact door',template,span)
            if key[1]%4==1:
                # Allocate the new open poses after the existing overlay entries.
                # Keep the frame in the catalog for the grid and baked-world passes.
                open_doors[key]=(signature,template,pixels)
                catalog[key]=template
                continue
        elif compact and key[0]==810 and key[1]%32==2:
            # The original stable bucket contains blood. Keep the stock UO handle
            # and hoops, changing only the water pixels in the filled barrel.
            bucket=stock(0xffa).copy()
            empty=stock(0x14e0)
            for yy in range(bucket.height):
                for xx in range(bucket.width):
                    r,g,b,a=bucket.getpixel((xx,yy))
                    if a and b>r and bucket.getpixel((xx,yy))!=empty.getpixel((xx,yy)):
                        bucket.putpixel((xx,yy),(min(235,62+b),13+g//7,18+b//9,a))
            cut=bucket.crop(bucket.getbbox()).resize((20,32),Image.Resampling.NEAREST)
            pixels=Image.new('RGBA',(44,44))
            pixels.alpha_composite(cut,(12,4))
            signature=('blood bucket',)
        elif key[0]==641:
            pixels=key_sprite(template)
            signature=('key',template)
        elif tool is not None:
            carried[key]=template
            pixels=tool
            signature=('tool',key)
        elif mirrored is not None:
            if ident.startswith('static 0x') and ' + ' not in ident:carried[key]=template
            pixels=mirrored
            signature=('reflected',row['target_image'])
        elif sign:
            template,pixels=sign
            signature=('sign',key)
        elif parts:
            geometries[key]=parts
            if compact:
                if row['source_name']=='table':
                    w,d=map(int,row['footprint'].split('\u00d7'))
                    parts=((0xB90 if w>d else 0xB7D,0,0,0,0),)
                    geometries[key]=parts
                elif row['source_name']!='bed':
                    parts=compact_parts(parts)
            template=parts[0][0]
            if len(parts)==1 and parts[0][1:]==(0,0,0,0):
                catalog[key]=template
                continue
            pixels=None
            signature=('parts',parts)
        elif re.fullmatch(r'static 0x[0-9a-fA-F]+',ident) or ident.startswith('item '):
            catalog[key]=template
            continue
        else:
            pixels=None
            signature=('atlas',row['target_image'])
        sig=signature,template,row['native_height']
        graphic=private_art(sig,template,row['name'],row['native_height'],parts,pixels,row['target_image'])
        catalog[key]=graphic
    assert sum(r['method']=='Approved stock rake' for r in rows)==10
    assert sum(r['method'] in ('Approved stock match','Approved stock treatment','Empty plate fragments') for r in rows)==18
    mapfile=bytearray((BASE/'map0.mul').read_bytes())
    idx=bytearray((BASE/'staidx0.mul').read_bytes())
    data=bytearray((BASE/'statics0.mul').read_bytes())
    blocks=defaultdict(bytearray)
    compact_statics=set()
    source_land={}
    joins={} if compact else wall_joins(refs,by_key)
    placements=[]
    for key,position,parts in (*stair_runs(refs,by_key),*fence_joins(refs,by_key)):
        row=by_key[key]
        if compact:parts=compact_parts(parts)
        template=parts[0][0]
        sig=('parts',parts),template,row['native_height']
        graphic=(template if len(parts)==1 and parts[0][1:]==(0,0,0,0) else
                 private_art(sig,template,row['name'],row['native_height'],parts))
        placements.append((*key,*position,graphic))
    # Fixed scenery also appears in the native observation stream. Each roof tile
    # is already baked into the facet. Exclude only those exact fixed source objects.
    fixed_roofs=[r for r in refs if r['layer']=='Fixed' and
                 by_key[int(r['shape']),int(r['frame'])]['source_name'] in ('wood roof','tile roof','slate roof')]
    (output/'fixed-roofs.tsv').write_text(''.join(
        '\t'.join(r[k] for k in ('shape','frame','x','y','lift'))+'\n' for r in fixed_roofs),encoding='ascii')
    if compact:
        grid=[k for k in catalog if (by_key[k]['category'] in ('Architecture','Doors') or
              by_key[k]['source_name'] in ('fence','table','stairs','bed','floor','crenellations','crossbeam'))]
        (output/'grid-frames.tsv').write_text(''.join(f'{s}\t{f}\n' for s,f in grid),encoding='ascii')
        fixed=[r for r in refs if r['layer']=='Fixed' or
               (r['layer']=='Terrain' and (int(r['shape']),int(r['frame'])) in catalog)]
        (output/'baked-world.tsv').write_text(''.join(
            '\t'.join(r[k] for k in ('shape','frame','x','y','lift'))+'\n' for r in fixed),encoding='ascii')
    # Native windows sit two lifts up on an intact base wall. A UO window
    # already includes that wall from sill to roof. Replace one compact bay.
    window_bays=defaultdict(dict)
    fittings=[]
    if compact:
        bases={(int(r['x']),int(r['y']),int(r['lift'])):by_key[int(r['shape']),int(r['frame'])]
               for r in refs if r['layer'] in ('Fixed','Terrain') and
               by_key[int(r['shape']),int(r['frame'])]['source_name']=='wall'}
        for r in refs:
            row=by_key[int(r['shape']),int(r['frame'])]
            name=row['source_name']
            if name not in ('window','closed shutters','open shutters'):continue
            x,y,lift=(int(r[k]) for k in ('x','y','lift'))
            window=fitted_window(bases.get((x,y,lift-2)))
            if window is None:continue
            if name=='window':
                window_bays[x//2,y//2,lift-2][window]=window
            else:
                # Leave this bay for the actual movable shutter state in the save.
                window_bays[x//2,y//2,lift-2][window]=0
                sig=('closed shutter',window)
                if sig not in private:
                    # The timber stock window supplies a framed shutter insert.
                    # Preserve the stone or timber outline and the window frame.
                    im=stock(window).copy()
                    right=window in (15,0x23,0x13b)
                    for xx in range(44):
                        col=43-xx if right else xx
                        if not 5<=col<=18:continue
                        for v in range(20):
                            yy=29+col+v
                            if im.getpixel((xx,yy))[3]:
                                tone=(100,66,34) if (col//3)%2 else (119,78,40)
                                if v in (1,16) or col%4==0:tone=(69,44,26)
                                im.putpixel((xx,yy),(*tone,255))
                    private_art(sig,window,'closed shutters',5,pixels=im)
                fittings.append((x,y,lift,window,private[sig]))
        (output/'window-fittings.tsv').write_text(''.join(
            '\t'.join(map(str,v))+'\n' for v in fittings),encoding='ascii')
        for (x,y,lift),graphics in compact_house_walls(refs,by_key).items():
            for window,replacement in window_bays.get((x,y,lift),{}).items():
                graphics=fit_house_window(graphics,window,replacement)
            for graphic in graphics:
                blocks[x//8*HEIGHT_BLOCKS+y//8].extend(struct.pack('<HBBbH',graphic,x%8,y%8,lift*4,0))
        # Native positions just inside an exterior-facing wall can share the
        # wall's compact tile. Keep that information for wide furniture sprites.
        wall_contacts={}
        for (x,y,lift),row in bases.items():
            w,d=map(int,row['footprint'].split('\u00d7'))
            for a in range(w):
                for b in range(d):
                    xx,yy=x-a,y-b
                    for point,arm,inside in (((xx,yy-1,lift),1,w>=d and yy%2),
                                             ((xx-1,yy,lift),2,d>=w and xx%2)):
                        if inside:wall_contacts[point]=wall_contacts.get(point,0)|arm
        with (output/'furniture-walls.tsv').open('w',encoding='ascii') as stream:
            for (x,y,lift),mask in sorted(wall_contacts.items()):
                stream.write(f'{x}\t{y}\t{lift}\t{mask}\n')
    roof_base={}
    for r in fixed_roofs:
        row=by_key[int(r['shape']),int(r['frame'])]
        w,d=map(int,row['footprint'].split('\u00d7'))
        for dx in range(w):
            for dy in range(d):
                pos=int(r['x'])-dx,int(r['y'])-dy
                if compact:pos=pos[0]//2,pos[1]//2
                roof_base.setdefault(pos,[]).append((4*int(r['lift']),row['source_name']))
    for x,y,z,graphic in roof_tiles(refs,by_key,U,2 if compact else 1):
        base,material=max((v for v in roof_base[x,y] if v[0]<=z),key=lambda v:v[0])
        south=(base,material) not in roof_base.get((x,y+1),())
        east=(base,material) not in roof_base.get((x+1,y),())
        if south or east:
            sig=('roof edge',graphic,z-base,south,east,material)
            if sig not in private:
                pixels=roof_edge_art(graphic,z-base,south,east,material=='wood roof',stock)
                private_art(sig,graphic,material,0,pixels=pixels)
            graphic=private[sig]
            z=base
        blocks[x//8*HEIGHT_BLOCKS+y//8].extend(struct.pack('<HBBbH',graphic,x%8,y%8,z,0))
    channels=portcullis_channels(refs,by_key) if compact else {}
    if compact:
        rampart_deck,rampart_tiles,rampart_faces=rampart_statics(refs,by_key,channels)
        for x,y,z,graphic in sorted(rampart_tiles):
            blocks[x//8*HEIGHT_BLOCKS+y//8].extend(struct.pack('<HBBbH',graphic,x%8,y%8,z,0))
    gate_deck={}
    for row in refs:
        kind=row['layer']
        if kind not in ('Terrain','Fixed'): continue
        x,y=int(row['x']),int(row['y'])
        z=4*int(row['lift'])
        key=int(row['shape']),int(row['frame'])
        if kind=='Fixed' and by_key[key]['source_name'] in ('wood roof','tile roof','slate roof'):continue
        block=x//8*HEIGHT_BLOCKS+y//8
        if kind=='Terrain' and key in land:
            if compact:source_land[x,y]=land[key],z
            else:struct.pack_into('<Hb',mapfile,block*196+4+3*(y%8*8+x%8),land[key],z)
        elif key in catalog:
            parts=geometries.get(key,[(catalog[key],0,0,0,0)])
            name=by_key[key]['source_name']
            if compact and name=='wall':continue  # House faces were joined across the full floor.
            if compact and name=='window' and (x//2,y//2,z//4-2) in window_bays:continue
            if compact and kind=='Terrain' and name=='fortress':continue
            join=joins.get((key,x,y,z//4))
            if join is not None:parts=[(join,0,0,0,0)]
            for graphic,dx,dy,dz,hue in parts:
                xx,yy=x+dx,y+dy
                if compact:
                    xx,yy=xx//2,yy//2
                    # At each gate the parapet and grille project into the same
                    # compact cell. End the solid coping at the two gateposts.
                    if name=='crenellations' and ((xx,yy,z+dz) in channels or
                                                  (xx,yy,z+dz) in rampart_deck):continue
                    if key in ((368,26),(368,27),(368,28),(369,22),(369,23),(369,24)) and graphic==0x51a:
                        # These six Black Gate frames are the strips surrounding the
                        # portcullis. Their walking surface is the top of the strip.
                        deck_z=z+dz+int(by_key[key]['native_height'])*4
                        gate_deck[xx,yy,deck_z]=graphic
                        continue
                    placement=xx,yy,z+dz,graphic,hue
                    if placement in compact_statics:continue
                    compact_statics.add(placement)
                blocks[xx//8*HEIGHT_BLOCKS+yy//8].extend(struct.pack('<HBBbH',graphic,xx%8,yy%8,z+dz,hue))
    if compact:
        # Christopher is the candle-ring victim. The other stable body has its own pose.
        key=(867,0)
        anchor=(1072,2199,0)
        row=by_key[key]
        with Image.open(ATLAS/'images'/(row['target_image']+'.png')) as source:
            pose=stable_victim_sprite(source.convert('RGBA'))
        graphic=private_art(('stable victim',key),catalog[key],row['name'],row['native_height'],pixels=pose)
        placements.append((*key,*anchor,graphic))
        depth_profiles[graphic]=(0,-2,-2)  # 44 pixels north = two isometric depth rows.
    for key,(signature,template,pixels) in open_doors.items():
        row=by_key[key]
        catalog[key]=private_art(signature,template,row['name'],row['native_height'],pixels=pixels)
        width,depth=map(int,row['footprint'].split('\u00d7'))
        if max(width,depth)==4:
            # Open leaves occupy separate jambs two UO cells apart. Split in
            # the empty columns between their silhouettes, including reflected frames.
            alpha=pixels.getchannel('A')
            runs=[]
            for x in range(pixels.width):
                if alpha.crop((x,0,x+1,pixels.height)).getbbox():
                    if runs and runs[-1][1]==x:runs[-1][1]=x+1
                    else:runs.append([x,x+1])
            if len(runs)!=2:raise ValueError(('open door silhouettes',key,runs))
            split=(runs[0][1]+runs[1][0])//2
            depth_profiles[catalog[key]]=(split,0,-2) if width>depth else (split,-2,0)
    if compact:
        (output/'art-depth.tsv').write_text(''.join(
            f'{g}\t{cut}\t{left}\t{right}\n' for g,(cut,left,right) in sorted(depth_profiles.items())),
            encoding='ascii')
    for (x,y,z),graphic in gate_deck.items():
        mask=channels.get((x,y,z),0)
        if mask:
            graphic=private_art(('gate paving',graphic,mask),graphic,'stone pavers',0,
                                pixels=deck_paver(stock(graphic),mask))
        blocks[x//8*HEIGHT_BLOCKS+y//8].extend(struct.pack('<HBBbH',graphic,x%8,y%8,z,0))
    if compact:
        for x,y,z in sorted(rampart_deck):
            graphic=0x51a
            face=rampart_faces.get((x,y,z))
            if face:
                wall,height=face
                sig=('rampart paving',wall,height)
                if sig not in private:
                    private_art(sig,graphic,'stone pavers',0,
                                pixels=rampart_paver(stock(graphic),stock(wall),height))
                graphic=private[sig]
            blocks[x//8*HEIGHT_BLOCKS+y//8].extend(struct.pack('<HBBbH',graphic,x%8,y%8,z,0))
    x0,y0,x1,y1=BOUNDS
    if compact:
        reduce_land(mapfile,source_land,output,tiledata,land)
        x0,y0,x1,y1=(n//2 for n in LANDSCAPE)
    for bx in range(x0//8,(x1+7)//8):
        for by in range(y0//8,(y1+7)//8):
            block=bx*HEIGHT_BLOCKS+by
            items=blocks[block]
            struct.pack_into('<iii',idx,block*12,len(data) if items else -1,len(items),0)
            data.extend(items)
    (output/'world-facings.tsv').write_text(''.join('\t'.join(map(str,line))+'\n' for line in placements),encoding='ascii')
    for name,blob in [('map0.mul',mapfile),('staidx0.mul',idx),('statics0.mul',data),('tiledata.mul',tiledata)]:
        (output/name).write_bytes(blob)
    (output/'carried-graphics.tsv').write_text(''.join(f'{s}\t{f}\t{i}\n' for (s,f),i in carried.items()),encoding='ascii')
    (output/'graphics.tsv').write_text(''.join(f'{s}\t{f}\t{i}\n' for (s,f),i in catalog.items()),encoding='ascii')
    shutil.copyfile(ATLAS/'outfits.csv',output/'outfits.csv')
    actors=[(int(re.search(r'NPC (\d+)',r['owner'])[1]),r['owner'].split(' (NPC')[0]) for r in refs if r['layer']=='Actor']
    (output/'actors.tsv').write_text(''.join(f'{i}\t{name}\n' for i,name in actors),encoding='utf-8')
    print(f'{len(catalog)} object frames, {len(land)} land frames, {len(private)} private sprites; rake 620/0 = {catalog[620,0]:04x}')

if __name__=='__main__':
    import argparse
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out',type=Path,default=COMPACT,help='private compact map output directory')
    build(parser.parse_args().out.resolve(),compact=True)
