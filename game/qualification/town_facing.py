"""Resolve native town facings before baking UO statics or selectable world sprites."""
import csv
import math
from PIL import Image, ImageDraw


def piece(graphic, x=0, y=0, z=0, hue=0):
    return graphic, x, y, z, hue


def span(graphic, width, depth, z=0):
    return tuple(piece(graphic,-x,-y,z) for x in range(width) for y in range(depth))


def layout(row, original):
    shape,frame=int(row['shape']),int(row['frame'])
    base=frame & 31
    w,d=map(int,row['footprint'].split('\u00d7'))
    along_x=w>d
    reflected=frame>=32
    name=row['source_name']
    hue=original[0][4] if original else 0
    if shape in (873,292):
        # DoWorkSit takes the low two bits. Reflecting the drawing interchanges N/W and E/S.
        face=(3-(base%4)) if reflected else base%4
        if shape==292 and base>=16: return (piece(0xB5E),)
        chairs=(0xB50,0xB4E,0xB4F,0xB51) if shape==873 else (0xB31,0xB2F,0xB2E,0xB30)
        return (piece(chairs[face]),)
    if shape==897:
        # Bench end/centre variants have different content. The long member itself runs on X or Y.
        across=base in (3,5,6,12,13)
        return (piece(0xB2D if across!=reflected else 0xB2C),)
    if name=='fence':
        return span(0x85F if (w,d)==(1,1) else (0x85D if along_x else 0x85E),w,d)
    if name=='stairs':
        stone=bool(base&1) or shape in (426,427,428,429,430)
        top=int(row['native_height'])*4
        return span(0x7A3 if stone else 0x738,w,d,max(0,top-10))
    if name in ('wall','fortress') and (w,d)==(1,1):
        # A diagonal streak in native projection is a vertical column. Full wall leaves at these
        # positions make every second wall and all exposed corners turn through ninety degrees.
        timber=shape==497 or (shape==879 and base in (5,6,7,16))
        return (piece(0x0009 if timber else 0x001D),)
    if name=='crenellations':
        return span(0x0073 if (w,d)==(1,1) else (0x0075 if along_x else 0x0074),w,d)
    if name=='crossbeam':
        return span(0x142 if along_x else 0x143,w,d)
    if shape in (270,376,211):
        material=0x675 if base//8==2 or base%8>=4 else 0x6A5 if base//8==1 else 0x6D5
        opened=base%4==1
        # The native open operation swaps shape AND footprint. The open stock sprite also turns.
        return span(material+(8 if (not along_x)^opened else 0)+int(opened),w,d)
    if shape in (522,800):
        return (piece(0xE43 if (base==0)!=reflected else 0xE42),)
    if shape in (290,291,322,372):
        return (piece((0x24F4 if along_x else 0x24F7) if name=='closed shutters'
                      else (0x26D1 if along_x else 0x26D5)),)
    if shape in (696,1011):
        parts=((0xA5D,-1,0),(0xA62,0,0)) if along_x else ((0xA63,0,-1),(0xA5C,0,0))
        return tuple(piece(i,x,y,0,hue) for i,x,y in parts)
    if shape in (633,847,890,971,1000,1003,1018) and w!=d:
        return span(0xB90 if along_x else 0xB7D,w,d)
    if shape in (949,950):
        return (piece((0x1EA8 if along_x else 0x1EAC)+base%4),)
    if shape==719:
        return ((piece(0xB43,-1,0),piece(0xB44)) if along_x
                else (piece(0xB41,0,-1),piece(0xB42)))
    if shape==787:
        # Four native lever positions. Opposed mounts have separate stock animations.
        return (piece(((0x1093,0x1095,0x108E,0x108C) if reflected
                       else (0x108E,0x108C,0x1093,0x1095))[base%4]),)
    if shape==407:
        return (piece(0xB4A if along_x else 0xB49),)
    if shape==991:
        return (piece(0xFB0 if along_x else 0xFAF),)
    if shape==713:
        return (piece(0x2D1D),)
    return original


def sign_sprite(row,stock):
    shape=int(row['shape']); frame=int(row['frame']); base=frame&31
    if shape==379:
        # UO boards include a tall invisible stem for hanging on UO brackets. The U7
        # board already has an independent lift, and its post is a separate object.
        on_x=(base>=7) != (frame>=32)
        graphic=0xBCF if on_x else 0xBD0
        im=stock(graphic)
        im=im.crop(im.getbbox())
        # Centre the attachment at the native post. A fork uses two separate boards.
        out=Image.new('RGBA',(44,im.height))
        out.alpha_composite(im,((44-im.width)//2,0))
        return graphic,out
    if shape==361:
        on_x=frame>=32
        board=0xBCF if on_x else 0xBD0
        # The lifted native signs stand in the street, with no wall to carry the bracket.
        # Build one ground-anchored sprite. The two short hangers meet the top of the board.
        def trim(graphic):
            im=stock(graphic)
            return im.crop(im.getbbox())
        beam,plate=trim(0xB9C),trim(0xBD0)
        pole=trim(0x2D1D).resize((8,71),Image.Resampling.NEAREST)
        out=Image.new('RGBA',(80,91))
        out.alpha_composite(pole,(36,2))
        out.alpha_composite(beam,(7,6))
        board_x,board_y=10,24
        draw=ImageDraw.Draw(out)
        for x in (board_x+3,board_x+plate.width-3):
            beam_y=beam.crop((x-7,0,x-6,beam.height)).getbbox()[3]+5
            board_top=plate.crop((x-board_x,0,x-board_x+1,plate.height)).getbbox()[1]+board_y
            draw.line((x,beam_y,x,board_top),fill=(54,45,29,255),width=2)
            draw.line((x,beam_y,x,board_top),fill=(153,131,82,255))
        out.alpha_composite(plate,(board_x,board_y))
        if on_x:out=out.transpose(Image.Transpose.FLIP_LEFT_RIGHT)
        return board,out


def pack(parts,stock):
    # ClassicUO draws static art bottom-centred on the object's tile, including pixel picking.
    # Keep the actual anchor inside transparent padding when a row extends to one side.
    layers=[]
    for g,x,y,z,h in sorted(parts,key=lambda p:(p[1]+p[2],p[3])):
        im=stock(g,h)
        layers.append((im,22*(x-y)-im.width//2,22*(x+y)-4*z-im.height))
    radius=max(max(-x,x+im.width) for im,x,y in layers)
    top=min(y for im,x,y in layers)
    bottom=max(y+im.height for im,x,y in layers)
    if bottom>0:
        # A negative z on the first tread is one UO lift unit below its anchor.
        # Trim the below-ground pixels only; all visible surfaces retain their elevation.
        if bottom>4: raise ValueError(('assembly extends below native tile',parts,bottom))
    out=Image.new('RGBA',(2*radius,-top))
    for im,x,y in layers: out.alpha_composite(im,(x+radius,y-top))
    return out


def roof_tiles(refs,rows,stock_dir,scale=1):
    # Direction and ridge pieces are named by the UO client in roof.txt. A continuous
    # native roof at one lift has local eaves on its perimeter, including at L-shaped bays.
    with (stock_dir/'roof.txt').open(encoding='cp1252') as stream:
        next(stream)
        styles={r['Comment']:r for r in csv.DictReader(stream,delimiter='\t') if r['Style']=='0'}
    material={'wood roof':'Wooden Shingles','tile roof':'Tile Roof','slate roof':'Stone Roof'}
    tiles={}
    for r in refs:
        if r['layer']!='Fixed':continue
        row=rows[int(r['shape']),int(r['frame'])]
        if row['source_name'] not in material:continue
        x,y,z=int(r['x']),int(r['y']),4*int(r['lift'])
        w,d=map(int,row['footprint'].split('\u00d7'))
        for xx in range(x-w+1,x+1):
            for yy in range(y-d+1,y+1):
                tiles[xx//scale,yy//scale,z]=material[row['source_name']]
    # Give each roof wing a single gable. Use a fixed course across its length.
    # Trinsic has rectangular buildings as well as wings adjoining at right angles.
    # Group identical contiguous row spans so a missing corner cannot turn every course.
    from collections import defaultdict
    scanlines=defaultdict(list)
    for (x,y,z),style in tiles.items():
        scanlines[style,z,y].append(x)
    wings=defaultdict(list)
    for (style,z,y),xs in scanlines.items():
        xs.sort()
        start=prev=xs[0]
        for x in xs[1:]:
            if x!=prev+1:
                wings[style,z,start,prev].append(y)
                start=x
            prev=x
        wings[style,z,start,prev].append(y)
    for (style,z,left,right),ys in wings.items():
        ys.sort()
        north=ys[0]
        for i,south in enumerate(ys):
            if i+1<len(ys) and ys[i+1]==south+1:continue
            across_y=(south-north)<=(right-left)
            for y in range(north,south+1):
                for x in range(left,right+1):
                    a,b=(y-north,south-y) if across_y else (x-left,right-x)
                    if a==b:part='EWCrosspiece' if across_y else 'NSCrosspiece'
                    elif across_y:part='North' if a<b else 'South'
                    else:part='West' if a<b else 'East'
                    yield x,y,z+3*min(a,b),int(styles[style][part])
            if i+1<len(ys):north=ys[i+1]


def roof_edge_art(graphic, rise, south, east, timber, stock):
    """Close the visible eave or gable from the shingle edge to the wall plate."""
    roof=stock(graphic)
    width,height=roof.width,roof.height+4*rise
    result=Image.new('RGBA',(width,height))
    for side,enabled in ((-1,south),(1,east)):
        if not enabled:continue
        board=stock((7 if side<0 else 8) if timber else (0x1C if side<0 else 0x1B))
        for u in range(22):
            dx=u-22 if side<0 else u
            x=width//2+dx
            column=roof.crop((x,0,x+1,roof.height)).getbbox()
            # At most two outer pixels of a stock shingle are transparent above the fascia.
            if column is None:
                neighbour=x+1 if side<0 else x-1
                column=roof.crop((neighbour,0,neighbour+1,roof.height)).getbbox()
            if column is None:continue
            edge=height-abs(dx)-4
            for y in range(column[3]-2,edge+1):
                sample=24+((y-edge+32)%36)+22-abs(dx)
                result.putpixel((x,y),board.getpixel((22+dx,sample)))
    result.alpha_composite(roof)
    return result


def stair_runs(refs,rows):
    stairs={}
    for r in refs:
        key=int(r['shape']),int(r['frame'])
        if rows[key]['source_name']=='stairs' and r['layer']=='World object':
            pos=int(r['x']),int(r['y']),int(r['lift'])
            stairs[pos]=key
    surfaces={(x,y):z+int(rows[key]['native_height']) for (x,y,z),key in stairs.items()}
    for (x,y,z),key in stairs.items():
        row=rows[key]
        width,depth=map(int,row['footprint'].split('\u00d7'))
        ax,ay=(0,1) if width>depth else (1,0)
        top=z+int(row['native_height'])
        # At a landing the next tread can be absent or level. Look along
        # the same flight for a change of elevation on each side.
        def slope(sign):
            xx,yy=x+sign*ax,y+sign*ay
            while (xx,yy) in surfaces:
                delta=surfaces[xx,yy]-top
                if delta:return sign*(1 if delta>0 else -1)
                xx+=sign*ax
                yy+=sign*ay
            return 0
        directions=[d for d in (slope(-1),slope(1)) if d]
        stone=bool(key[1]&1) or key[0] in (426,427,428,429,430)
        block=0x7A3 if stone else 0x738
        if len(set(directions))!=1:
            # A shared summit between opposite flights has a flat walking surface.
            yield key,(x,y,z),span(block,width,depth,max(0,(top-z)*4-5))
            continue
        up=directions[0]
        # stairs.txt lists North, West, South, East in consecutive graphic slots.
        graphic=block+((4 if up>0 else 2) if ax else (3 if up>0 else 1))
        yield key,(x,y,z),span(graphic,width,depth,max(0,(top-z)*4-5))


def reflected_sprite(row,other,images):
    # U7 transposes its native projection across X=Y. In the UO diamond this same
    # world transform is a horizontal reflection, leaving vertical features upright.
    # Verify against the source pixels: some shapes store genuine frames above 31.
    if (not other or row['category'] in ('Terrain','Actors','Trees','Equipment') or
        row['target_image']!=other['target_image'] or
        row['source_image']==other['source_image'] or row['method'].startswith('Approved')):
        return None
    with Image.open(images/(other['source_image']+'.png')) as im:
        expected=im.convert('RGBA').transpose(Image.Transpose.TRANSPOSE)
    with Image.open(images/(row['source_image']+'.png')) as im:
        actual=im.convert('RGBA')
        if actual.size!=expected.size or actual.tobytes()!=expected.tobytes():return None
    with Image.open(images/(row['target_image']+'.png')) as im:
        return im.convert('RGBA').transpose(Image.Transpose.FLIP_LEFT_RIGHT)


def wall_joins(refs,rows):
    occupied=set()
    for r in refs:
        row=rows[int(r['shape']),int(r['frame'])]
        if r['layer'] not in ('Terrain','Fixed','World object'):continue
        if row['source_name'] not in ('wall','fortress','closed shutters','open shutters') and row['method']!='Door leaf':continue
        x,y,z=int(r['x']),int(r['y']),int(r['lift'])
        w,d=map(int,row['footprint'].split('\u00d7'))
        occupied.update((x-dx,y-dy,z) for dx in range(w) for dy in range(d))
    joins={}
    for r in refs:
        key=int(r['shape']),int(r['frame'])
        row=rows[key]
        if r['layer'] not in ('Terrain','Fixed') or row['source_name']!='wall' or row['footprint']!='1 \u00d7 1':continue
        x,y,z=int(r['x']),int(r['y']),int(r['lift'])
        along_x=(x-1,y,z) in occupied or (x+1,y,z) in occupied
        along_y=(x,y-1,z) in occupied or (x,y+1,z) in occupied
        west=(x-1,y,z) in occupied
        north=(x,y-1,z) in occupied
        wood=key[0]==497 or (key[0]==879 and (key[1]&31) in (5,6,7,16))
        south,east,corner,post=(0x7,0x8,0x6,0x9) if wood else (0x1C,0x1B,0x1A,0x1D)
        # UO walls extend towards negative coordinates from the shared corner.
        graphic=(corner if west and north else south if along_x and not along_y else
                 east if along_y and not along_x else south if west else east if north else post)
        joins[key,x,y,z]=graphic
    return joins

def fence_joins(refs,rows):
    rails=set()
    posts=[]
    for r in refs:
        key=int(r['shape']),int(r['frame'])
        row=rows[key]
        if row['source_name']!='fence' or r['layer']!='World object':continue
        x,y,z=int(r['x']),int(r['y']),int(r['lift'])
        w,d=map(int,row['footprint'].split('\u00d7'))
        if w==d==1:
            posts.append((key,(x,y,z)))
        else:
            rails.update((x-dx,y-dy,z) for dx in range(w) for dy in range(d))
    for key,(x,y,z) in posts:
        west=(x-1,y,z) in rails
        north=(x,y-1,z) in rails
        if west or north:
            yield key,(x,y,z),(piece(0x85C if west and north else 0x85D if west else 0x85E),)


def tool_sprite(row,base_row,images):
    # Only the loose world sprite changes. Stock item/animation IDs remain available
    # on the paperdoll. An elongated handle gives a measurable axis in the original frame.
    shape,frame=int(row['shape']),int(row['frame'])
    if shape not in (561,589,590,591,593,594,595,596,597,598,599,600,601,602,
                     614,615,623,625,627,659,668,885,994) or frame==0:
        return None
    if not row['target_image'] or not base_row['target_image']:return None
    def axis(sprite):
        alpha=sprite.convert('RGBA').getchannel('A')
        points=[(x,y) for y in range(alpha.height) for x in range(alpha.width) if alpha.getpixel((x,y))]
        if len(points)<3:return None
        cx=sum(x for x,y in points)/len(points); cy=sum(y for x,y in points)/len(points)
        xx=sum((x-cx)**2 for x,y in points);yy=sum((y-cy)**2 for x,y in points)
        xy=sum((x-cx)*(y-cy) for x,y in points)
        if xx+yy==0 or math.hypot(xx-yy,2*xy)<0.55*(xx+yy):return None
        return math.degrees(math.atan2(2*xy,xx-yy))/2
    with Image.open(images/(row['source_image']+'.png')) as im:angle=axis(im)
    with Image.open(images/(base_row['source_image']+'.png')) as im:base=axis(im)
    if angle is None or base is None:return None
    turn=(base-angle+90)%180-90
    if abs(turn)<8:return None
    with Image.open(images/(base_row['target_image']+'.png')) as im:
        sprite=im.convert('RGBA')
        sprite=sprite.crop(sprite.getbbox()).rotate(turn,Image.Resampling.NEAREST,expand=True)
        return sprite.crop(sprite.getbbox())


def key_sprite(template):
    # A dark rim, open bow and two teeth keep the key legible against earth and leather.
    shade,metal,light={
        0x100E:('#9b5826','#efb653','#fff0a0'),
        0x100F:('#9e7327','#f3c948','#ffffa9'),
        0x1010:('#646675','#b8bdc8','#f4f3dc'),
    }[template]
    out=Image.new('RGBA',(26,15))
    pen=ImageDraw.Draw(out)
    ink='#30251c'
    pen.polygon([(7,3),(22,8),(25,9),(24,13),(22,14),(20,13),(20,11),
                 (18,10),(18,12),(15,12),(14,9),(7,7)],fill=ink)
    pen.line((8,5,23,10),fill=metal,width=3)
    pen.line((8,4,23,9),fill=light)
    pen.line((16,8,16,11),fill=shade,width=2)
    pen.line((22,10,22,13),fill=metal,width=2)
    pen.ellipse((0,0,10,10),fill=ink)
    pen.ellipse((1,1,9,9),fill=shade)
    pen.arc((1,1,9,9),155,340,fill=light,width=2)
    pen.arc((2,2,8,8),335,158,fill=metal,width=2)
    pen.ellipse((3,3,7,7),fill=ink)
    pen.ellipse((4,4,6,6),fill=(0,0,0,0))
    return out
