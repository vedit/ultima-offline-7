"""Inspect the generated Trinsic art and placement records used by ClassicUO."""
import json
import struct
from town_atlas import COMPACT,ROOT,table,fitted_window
from town_scale import BOUNDS,map_offset,portcullis_channels
from play import BIN
from install_paths import GAME_SOURCE
from town_facing import wall_joins,stair_runs,fence_joins,roof_tiles


def graphic_table(folder,name):
    rows=(list(map(int,line.split())) for line in (folder/name).read_text().splitlines())
    return {tuple(row[:-1]):row[-1] for row in rows}


def verify(output=COMPACT):
    assert fitted_window({'uo_id':'assembly 0x0007@(0,0,0)'})==14
    assert fitted_window({'uo_id':'static 0x0241'}) is None
    assert fitted_window({'uo_id':'unmapped'}) is None and fitted_window(None) is None
    frames=graphic_table(output,'graphics.tsv')
    placed=graphic_table(output,'world-facings.tsv')
    carried=graphic_table(output,'carried-graphics.tsv')
    rows={(int(r['shape']),int(r['frame'])):r for r in table('mapping.csv')}
    refs=table('references.csv')
    original={tuple(v[:2]):v[2] for v in (list(map(int,line.split())) for line in
              (ROOT/'town-data/graphics.tsv').read_text().splitlines())}
    # The reviewed gargoyle corpses formerly existed only as animation previews.
    gargoyle_corpses={(414,base+reflection) for base in (1,2,3,14) for reflection in (0,32)}
    assert frames.keys()==original.keys()|gargoyle_corpses
    # Stock lookup in the installed client tells us the direction the character actually sits.
    chairs={}
    for line in (BIN/'Data/Client/chair.txt').read_text().splitlines():
        fields=line.split(',')
        if fields and fields[0].isdecimal():chairs[int(fields[0])]=int(fields[1])
    for shape in (873,292):
        for frame in range(16):
            assert chairs[frames[shape,frame]]==2*(frame&3)
    assert frames[800,0]==frames[522,0]==0xE43 and frames[800,1]==frames[522,1]==0xE42
    assert frames[696,0]!=frames[1011,0] and frames[696,0]==frames[1011,32]
    assert frames[949,0]!=frames[950,0]
    assert len({frames[787,f] for f in range(4)})==4
    assert frames[713,1]==0x2D1D and frames[379,3]!=frames[379,8]

    # Read the compiled facet at each placement to catch discarded recipes or flipped axes.
    idx=(output/'staidx0.mul').read_bytes()
    statics=(output/'statics0.mul').read_bytes()
    def tile(x,y,z,graphic):
        start,count,_=struct.unpack_from('<iii',idx,12*((x//8)*512+y//8))
        return start>=0 and any((i,tx,ty,h)==(graphic,x%8,y%8,z) for i,tx,ty,h,hue
                                in struct.iter_unpack('<HBBbH',statics[start:start+count]))
    joins=wall_joins(refs,rows)
    fittings=graphic_table(output,'window-fittings.tsv')
    channels=portcullis_channels(refs,rows)
    deck=set()
    source_rim=set()
    for r in refs:
        row=rows[int(r['shape']),int(r['frame'])]
        ground=r['layer']=='Terrain' and row['source_name']=='fortress'
        rail=r['layer']=='Fixed' and row['source_name']=='crenellations'
        if not (ground or rail):continue
        x,y,lift=map(int,(r['x'],r['y'],r['lift']))
        w,d=map(int,row['footprint'].split('×'))
        points=((x-a,y-b) for a in range(w) for b in range(d))
        if ground:deck.update((xx//2,yy//2,4*(lift+int(row['native_height']))) for xx,yy in points)
        else:source_rim.update((xx,yy,4*lift) for xx,yy in points)
    bases={(int(r['x']),int(r['y']),int(r['lift'])):rows[int(r['shape']),int(r['frame'])]
           for r in refs if r['layer'] in ('Fixed','Terrain')
           and rows[int(r['shape']),int(r['frame'])]['source_name']=='wall'}
    bays={}
    for r in refs:
        key=int(r['shape']),int(r['frame'])
        row=rows[key]
        if r['layer'] not in ('Fixed','Terrain'):continue
        x,y,lift=(int(r[k]) for k in ('x','y','lift'))
        if row['source_name']=='window' and fitted_window(bases.get((x,y,lift-2))) is not None:
            bay=x//2,y//2,lift-2
            matches=[i for i in (14,15,34,35) if tile(bay[0],bay[1],bay[2]*4,i)]
            assert len(matches)==1,(bay,matches)
            bays[bay]=matches[0]
        if row['source_name']=='crenellations':
            w,d=map(int,row['footprint'].split('×'))
            rail=0x2d if w==d else 0x78 if w>d else 0x79
            for a in range(w):
                for b in range(d):
                    cell=(x-a)//2,(y-b)//2,lift*4
                    if cell not in deck:assert tile(*cell,rail)==(cell not in channels)
    for (x,y,lift,opened),closed in fittings.items():
        bays[x//2,y//2,lift-2]=0
        assert opened in (14,15,34,35) and (output/'Art/Statics'/f'{closed}.art').is_file()
    for x,y,lift in bays:
        assert not any(tile(x,y,lift*4,i) for i in (7,8,27,28))
    for (key,x,y,z),graphic in joins.items():
        if (x//2,y//2,z) in bays and graphic in (7,8,27,28):continue
        assert tile(x//2,y//2,z*4,graphic)
    roofs=list(roof_tiles(refs,rows,ROOT.parents[1]/'Assets/UO-Classic',2))
    data=(output/'tiledata.mul').read_bytes()
    for frame in (26,58):
        graphic=frames[414,frame]
        offset=512*964+graphic//32*1316+4+graphic%32*41
        assert not (struct.unpack_from('<Q',data,offset)[0] & 0x08), ('translucent Inamo', frame)
    def roof_at(x,y,z,graphic):
        if tile(x,y,z,graphic):return True
        start,count,_=struct.unpack_from('<iii',idx,12*((x//8)*512+y//8))
        for i,tx,ty,h,_ in struct.iter_unpack('<HBBbH',statics[start:start+count]):
            if tx!=x%8 or ty!=y%8 or h>z or i<0xbd00:continue
            off=512*964+i//32*1316+4+i%32*41
            if 'roof' in data[off+21:off+41].decode('ascii','ignore') and (output/'Art/Statics'/f'{i}.art').exists():
                return True
        return False
    for x,y,z,graphic in roofs:
        if 464<=x<560 and 1040<=y<1176:assert roof_at(x,y,z,graphic)
    assert not tile(541,1096,38,11329) and roof_at(541,1096,38,11329)
    # The square stable has two continuous banks and one ridge along X.
    stable={(x,y):(z,i) for x,y,z,i in roofs if 528<=x<=541 and 1090<=y<=1103}
    assert len(stable)==14*14
    for y in range(1090,1104):
        course={stable[x,y] for x in range(528,542)}
        assert course=={(20+3*min(y-1090,1103-y),11329 if y<=1096 else 11328)}
    baked={tuple(map(int,line.split())) for line in (output/'baked-world.tsv').read_text().splitlines()}
    assert (170,1,1071,2207,5) in baked and all(t[0]!=641 for t in baked)
    with (output/'map0.mul').open('rb') as facet:
        facet.seek(map_offset(1068//2,2197//2))
        assert 0x75<=struct.unpack('<H',facet.read(2))[0]<=0x78
    # Every quadrant combination seen on the uncompressed reference facet
    # must map consistently, even when the transition appears in a different block.
    from town_atlas import OUT as full
    with (full/'map0.mul').open('rb') as old,(output/'map0.mul').open('rb') as reduced:
        mapping={}
        x0,y0,x1,y1=BOUNDS
        for y in range(y0,y1,2):
            for x in range(x0,x1,2):
                four=[]
                for dy in (0,1):
                    for dx in (0,1):
                        old.seek(map_offset(x+dx,y+dy))
                        four.append(struct.unpack('<Hb',old.read(3)))
                reduced.seek(map_offset(x//2,y//2))
                g,z=struct.unpack('<Hb',reduced.read(3))
                assert z==max(h for _,h in four)
                ids=tuple(i for i,h in four)
                assert mapping.setdefault(ids,g)==g
                if len(set(ids))==1:assert g==ids[0]
                elif g not in ids:assert (output/'Art/Land'/f'{g}.art').stat().st_size==2024
    assert frames[376,16]!=frames[270,17] and not any(v[:2]==(376,16) for v in baked)
    key=frames[641,0]
    assert key>=0xbd00 and carried.get((641,0),key)==key
    header=(output/'Art/Statics'/f'{key}.art').read_bytes()
    assert struct.unpack_from('<HH',header,4)==(26,15)

    steps=list(stair_runs(refs,rows)); fences=list(fence_joins(refs,rows))
    victim=(867,0,1072,2199,0)
    assert set(placed)=={key+pos for key,pos,parts in steps+fences}|{victim}
    assert placed[victim]!=frames[867,0]
    # Compare the shipped pose directly to the reviewed image, around its center.
    from PIL import Image
    from town_atlas import ATLAS,encode_sprite
    import sys
    sys.path.insert(0,str(GAME_SOURCE/'atlas'))
    from source import uo
    from town_facing import pack,piece,span
    from functools import lru_cache
    @lru_cache(None)
    def paving_bytes(wall):
        paver=uo(0x51a).copy()
        if wall:
            masonry=uo(wall)
            dy=paver.height+80-masonry.height
            for y in range(max(0,dy),paver.height):
                for x in range(paver.width):
                    if masonry.getpixel((x,y-dy))[3]:
                        paver.putpixel((x,y),(0,0,0,0))
        return encode_sprite(paver)
    @lru_cache(None)
    def art_bytes(g):
        return (output/'Art/Statics'/f'{g}.art').read_bytes() if g>=0xbd00 else encode_sprite(uo(g))
    deck_art={0x51a}
    deck_art.update(i for i in range(0xbd00,0xf400)
                    if data[(p:=512*964+i//32*1316+4+i%32*41)+21:p+33].startswith(b'stone pavers'))
    for x,y,z in deck:
        east=(x+1,y,z) not in deck
        south=(x,y+1,z) not in deck
        wall=0x1a if east and south else 0x1b if east else 0x1c if south else 0
        if wall:assert tile(x,y,z-20,wall)
        elif tile(x,y,z-20,0x1d):wall=0x1d
        start,count,_=struct.unpack_from('<iii',idx,12*((x//8)*512+y//8))
        paving=[g for g,xx,yy,h,_ in struct.iter_unpack('<HBBbH',statics[start:start+count])
                if (xx,yy,h)==(x%8,y%8,z) and g in deck_art]
        assert len(paving)==1 and art_bytes(paving[0])==paving_bytes(wall),(x,y,z,wall,paving)
        # Inspect each exposed edge of this cell independently of the converter.
        for dx,dy,g in ((-1,0,0x79),(1,0,0x79),(0,-1,0x78),(0,1,0x78)):
            if (x+dx,y+dy,z) in deck:continue
            border=[(2*x+a,2*y+b,z) for a in (0,1) for b in (0,1)
                    if (dx<0 and a==0 or dx>0 and a==1 or dy<0 and b==0 or dy>0 and b==1)]
            edge=(x-(dx<0),y-(dy<0),z)
            if any(p in source_rim for p in border) and edge not in channels:
                assert tile(*edge,g) or tile(*edge,0x2d),edge
    # Stock end post at the northern convex turn, joined corner at the return,
    # and no V-shaped post interrupting the straight western wall.
    assert tile(466,1074,20,0x30) and tile(474,1074,20,0x2d)
    assert tile(476,1076,0,0x1a) and not tile(467,1080,20,0x2d)
    from town_scale import compact_parts
    # The top board must face uphill on every row, including the top row
    # with no next neighbour. Check the installed art for all six flights.
    for x,y,dx,dy,blocks,graphic in (
        (1089,2206,1,0,(385,386,387,973,974),0x73c),
        (1089,2227,1,0,(385,386,387,973,974),0x73c),
        (1007,2110,0,-1,range(426,431),0x7a4),(1026,2110,0,-1,range(426,431),0x7a4),
        (1007,2321,0,1,range(426,431),0x7a6),(1026,2321,0,1,range(426,431),0x7a6)
    ):
        for i,shape in enumerate(blocks):
            w,d=map(int,rows[shape,0]['footprint'].split('×'))
            pieces=compact_parts(span(graphic,w,d,max(0,4*(i+1)-5)))
            expected=pack(pieces,lambda g,h:uo(g))
            gid=placed[shape,0,x+i*dx,y+i*dy,0]
            assert (output/'Art/Statics'/f'{gid}.art').read_bytes()==encode_sprite(expected)
    assert len(channels)==6
    for (x,y,z),mask in channels.items():
        start,count,_=struct.unpack_from('<iii',idx,12*((x//8)*512+y//8))
        top=[g for g,xx,yy,h,_ in struct.iter_unpack('<HBBbH',statics[start:start+count])
             if (xx,yy,h)==(x%8,y%8,z)]
        # Stock stone fills only the two source quadrants outside the grille.
        assert 0x51a not in top and 0x78 not in top and 0x79 not in top
        assert not tile(x,y,z-4,0x51a)
        expected=uo(0x51a).copy()
        for py in range(44):
            for px in range(44):
                quadrant=(px+py>=43)+2*(py>=px)
                if mask&(1<<quadrant):expected.putpixel((px,py),(0,0,0,0))
        assert sum((output/'Art/Statics'/f'{g}.art').read_bytes()==encode_sprite(expected)
                   for g in top if g>=0xbd00)==1
    door_art=output/'Art/Statics'
    for family,base_frame in ((0x675,16),(0x6a5,8),(0x6d5,0)):
        # Compare the shipped closed doors pixel for pixel with the two stock leaves.
        for shape,closed_parts,opened in (
            (270,(piece(family,-1,0),piece(family+2)),376),
            (376,(piece(family+10,0,-1),piece(family+8)),270)
        ):
            closed=frames[shape,base_frame]
            expected=pack(closed_parts,lambda graphic,hue:uo(graphic))
            assert (door_art/f'{closed}.art').read_bytes()==encode_sprite(expected)
            assert frames[shape,base_frame+2]==frames[shape,base_frame+3]==closed
            opened_art=(door_art/f'{frames[opened,base_frame+1]}.art').read_bytes()
            assert frames[opened,base_frame+1]!=closed
            # A scan line halfway up both open leaves must contain two disjoint runs.
            _,w,h=struct.unpack_from('<IHH',opened_art)
            row=struct.unpack_from('<H',opened_art,8+2*(h//2))[0]
            offset=8+2*h+2*row
            _,first=struct.unpack_from('<HH',opened_art,offset)
            gap,second=struct.unpack_from('<HH',opened_art,offset+4+first*2)
            assert 0<first<w and 0<second<w and gap>=12
    assert (door_art/f'{frames[211,2]}.art').read_bytes()==encode_sprite(uo(0x6dd))
    with Image.open(ATLAS/'images'/(rows[867,0]['target_image']+'.png')) as source:
        turn=source.convert('RGBA').rotate(-45,Image.Resampling.NEAREST,expand=True)
        height=(source.height+turn.height)//2+44
        expected=Image.new('RGBA',(turn.width,height))
        expected.alpha_composite(turn)
    assert (output/'Art/Statics'/f'{placed[victim]}.art').read_bytes()==encode_sprite(expected)
    for key in gargoyle_corpses | {(414,26),(414,58)}:
        with Image.open(ATLAS/'images'/(rows[key]['target_image']+'.png')) as source:
            assert (door_art/f'{frames[key]}.art').read_bytes()==encode_sprite(source)
    assert placed[426,0,1007,2110,0]!=placed[426,0,1007,2321,0]
    for key,pos,parts in fences:assert placed[key+pos]==parts[0][0]
    assert len({frames[873,f] for f in range(4)})==4
    assert carried[994,3]==0xFBB and frames[994,3]!=carried[994,3]

    art=output/'Art/Statics'
    private={int(p.stem):p for p in art.glob('*.art')}
    # The ten approved rake faces and eighteen approved matches keep their original pixels.
    approved=[k for k,r in rows.items() if r['method'] in
              ('Approved stock rake','Approved stock match','Approved stock treatment','Empty plate fragments')]
    assert len(approved)==28
    for key in approved:
        old,new=original[key],frames[key]
        if old>=0xBD00:
            assert private[new].read_bytes()==(ROOT/'town-data/Art/Statics'/f'{old}.art').read_bytes()
        else:assert old==new
    # Validate every compiled art reference in the live object table (including placement overrides).
    for id in set(frames.values())|set(placed.values()):
        if 0xBD00<=id<0xF400:assert id in private
    world=[r for r in refs if r['layer'] in ('World object','Fixed','Terrain')]
    results={'placements_examined':len(world),'source_frames_placed':len({(r['shape'],r['frame']) for r in world}),
             'wall_joins':len(joins),'placed_stair_rows':len(steps),'connected_fence_posts':len(fences),
             'roof_cells':len(roofs),'preserved_approved_art':len(approved),'mapped_object_frames':len(frames)}
    print(json.dumps(results,indent=2))
    return results


if __name__=='__main__':
    import argparse
    from pathlib import Path
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out',type=Path,default=COMPACT,help='compact map directory to check')
    verify(parser.parse_args().out)
