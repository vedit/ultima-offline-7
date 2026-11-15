"""Map Trinsic presentation onto stock UO bodies, equipment and modular scenery."""
import math
from wall_materials import house_wall_art
import equipment,scene_parts,town_review,rake
from functools import lru_cache
import numpy as np
from PIL import Image,ImageOps
from targets import uo,land,landname,tile,entries,art_key,names,tfa,counts,src,bodyids,title
from costumes import WARDROBES,costume,costume_ids,costume_desc,match_hue,ramp

def layout(*pieces):return ('layout',*pieces)
def part(i,x=0,y=0,z=0,hue=0):return (i,x,y,z,hue)
@lru_cache(None)
def painted(i,hue):
    im=uo(i)
    if not hue:return im
    palette=ramp(hue);out=im.copy()
    out.putdata([(*palette[r>>3],a) if a else (0,0,0,0) for r,g,b,a in im.getdata()])
    return out
@lru_cache(None)
def assemble(components):
    # Same-tile layers retain author order. Tile offsets use the ClassicUO 44 px diamond.
    images=[]
    for i,x,y,z,h in sorted(components,key=lambda p:(p[1]+p[2],p[3])):
        im=painted(i,h);left=(x-y)*22-im.width//2;top=(x+y)*22-4*z-im.height
        images.append((im,left,top))
    l=min(x for _,x,y in images);t=min(y for _,x,y in images)
    dest=Image.new('RGBA',(max(x+i.width for i,x,y in images)-l,max(y+i.height for i,x,y in images)-t))
    for im,x,y in images:dest.alpha_composite(im,(x-l,y-t))
    return dest
def draw(spec):
    if spec[0]=='rake':return rake.render(spec[1])
    if spec[0]=='revised':return town_review.render(*spec[1:])
    if spec[0]=='wearable':return painted(*spec[1:])
    if spec[0]=="remains":
        from remains import stock
        return stock(*spec[1:])
    if spec[0]=='scene':return scene_parts.render(*spec[1:])
    if spec[0]=='outfit':return costume(*spec[1:])[0]
    return assemble(spec[1:])
def describe(spec):
    if spec[0]=='rake':return rake.describe(spec[1])
    if spec[0]=='revised':return town_review.describe(*spec[1:])
    if spec[0]=='wearable':return equipment.detail(*spec[1:])
    if spec[0]=='remains':
        from remains import describe as corpse_recipe
        return corpse_recipe(*spec[1:])
    if spec[0]=='scene':return scene_parts.description(*spec[1:])
    if spec[0]=='outfit':
        s,f=spec[1:];_,action,direction,phase,mirror=costume(s,f)
        return costume_ids(s)+f' · action {action}, dir {direction}, frame {phase}'+(' mirrored' if mirror else ''),costume_desc(s)
    ids=[];labels=[]
    for i,x,y,z,h in spec[1:]:
        ids.append(f'0x{i:04X}@({x},{y},{z})'+(f'/hue 0x{h:04X}' if h else ''))
        if tile(i)[0] not in labels:labels.append(tile(i)[0])
    return 'assembly '+' + '.join(ids),', '.join(labels)
def span(i,dx,dy):return layout(*(part(i,-x,-y) for x in range(dx) for y in range(dy)))
def extent(s,f):
    fp=tfa[3*s+2];dx,dy=(fp&7)+1,(fp>>3&7)+1
    return (dy,dx) if f>=32 and counts[s]<0 else (dx,dy)
def tint(im):
    a=np.array(im.convert('RGBA'));pix=a[:,:,:3][a[:,:,3]>0]
    vivid=pix[(pix.max(axis=1).astype(int)-pix.min(axis=1)>42)&(pix.max(axis=1)>70)]
    if len(vivid)<3:return 0
    return match_hue(tuple(np.median(vivid,axis=0)))
def features(a):
    # Local color samples distinguish which side of the tile carries sand or vegetation.
    return np.array(Image.fromarray(a).resize((4,4),Image.Resampling.BOX)).astype(float)/255
@lru_cache(None)
def landbank(materials):
    bank=[]
    for i in range(1,0x400):
        if landname(i).lower() not in materials or art_key(i) not in entries:continue
        im=land(i);p=im.load();a=np.empty((8,8,3),dtype='uint8')
        for y in range(8):
            for x in range(8):
                px=round(21.5+(x-y)*2.75);py=round((1+x+y)*2.75-0.5);a[y,x]=p[px,py][:3]
        bank.append((i,features(a)))
    return tuple(i for i,a in bank),np.stack([a for i,a in bank])
@lru_cache(None)
def terrain(s,f):
    water=s in {2,8,19,20,26,64,65}
    mats=('water',) if water else ('dirt',) if s==25 else ('sand','grass') if s in (118,119,120,121,122,124,130) else ('dirt','grass')
    ids,bank=landbank(mats);a=features(np.array(src(s,f)[0].convert('RGB')))
    return ('land',ids[int(np.mean((bank-a)**2,axis=(1,2,3)).argmin())])
def simplify(s,f,im,original):
    category,spec,grade,method,note=original
    if grade=='No visible art':return original
    revision=town_review.treatment(s,f,category)
    if revision:return revision
    k=f&31
    if s in equipment.ITEMS:
        spec=equipment.wearable(s,f)
        return 'Equipment',spec,'Stock equipment','Equipment role','Use the listed stock UO item in its native equipment layer. The thumbnail identifies the item. Preserve the U7 name, properties and effects.'
    if s in WARDROBES:
        return 'Actors',('outfit',s,f),'Stock outfit','Equipped animation','Wear the listed stock layers on the common body anchor.'+(' Spark uses the adult base body; stature is approximate.' if s==489 else '')+(' This frame uses a representative stock seated, bowed or reclining pose.' if k%16 in (10,11,12,13) else '')
    if s in bodyids:return 'Actors',spec,'Stock candidate','Animal animation','Use the stock animal body and closest pose for this frame.'
    if category=='Terrain' and grade=='Custom art':
        return category,terrain(s,f),'Stock candidate','Terrain transition','Closest stock material pattern by local color and edge direction. Check adjacent tiles for continuity.'
    if s in (271,272):
        dx,dy=extent(s,f);i=0x6f5 if dx>dy else 0x6f6
        return 'Doors',span(i,dx,dy),'Stock assembly','Lifting gate','Repeat the portcullis panel over the native span. All four sections lift together with one host object.'
    if s in (270,376,211):
        dx,dy=extent(s,f);base=(0x675 if k//8==2 or k%8>=4 else 0x6a5 if k//8==1 else 0x6d5)
        opened=k%4==1
        i=base+(8 if (dy>dx)^opened else 0)+int(opened)
        return 'Doors',span(i,dx,dy),'Stock assembly','Door leaf','Repeat the stock leaf art across the source span. Apply the host open, closed and locked states to the assembly.'+(' A damaged leaf is represented by ordinary door hardware.' if s==211 else ' A hinged cell grille can use the barred metal doors in the stock study.' if k//8==1 else '')
    if s==257:
        dx,dy=extent(s,f);cross=k%2==0
        pieces=[part(0x2b if cross else 0x2a),part(0x2c if cross else 0x29,-(dx-1) if cross else 0,0 if cross else -(dy-1))]
        return 'Doors',layout(*pieces),'Stock assembly','Gateway surround','Place stock stone arch ends on opposite jambs. Keep the central passage clear for the separate gate.'
    if s==264:
        return 'Objects',('static',0x1bef if k<3 else 0x1876),'Stock candidate','Loose metal','Use an iron ingot or coil for the loose bent metal. This source shape is debris.'
    dx,dy=extent(s,f)
    if category=='Architecture':
        name=names[s];id=spec[1];tx,ty=dx,dy
        if name in ('wall','fortress'):
            reviewed=house_wall_art(s,f,tx,ty) if name=='wall' else None
            if reviewed is not None:
                return category,span(reviewed,tx,ty),'Stock assembly','Source wall material','Match the material of the original Black Gate wall frame across its native span.'
            if s in (828,845) and k>=16:id=0x051a
            elif s in (828,845):id=0x241 if tx>=ty else 0x242
            elif tile(id)[0]=='wooden wall':id=0x7 if tx>=ty else 0x8
            else:id=0x1c if tx>=ty else 0x1b
        elif name=='crenellations':id=0x72 if tx>=ty else 0x75
        elif name=='crossbeam':id=0x141 if tx>=ty else 0x142
        elif name=='pillar':tx=ty=1
        if name in ('wall','fortress') and dx>1 and dy>1 and id!=0x51a:
            # Adjacent walls share the corner; no solid infill across walkable interior.
            second={0x241:0x242,0x242:0x241,0x7:0x8,0x8:0x7,0x1b:0x1c,0x1c:0x1b}[id]
            obj=layout(*(part(id,-x,0) for x in range(dx)),*(part(second,0,-y) for y in range(1,dy)))
        else:obj=span(id,tx,ty)
        return category,obj,'Stock assembly' if len(obj)>2 else 'Stock candidate','Modular scenery','Use the displayed stock parts at the listed tile offsets. The source controls elevation and collision; check joins where this piece meets its neighbour.'
    if s in (633,847,890,971,1000,1003,1018):
        return category,span(spec[1],dx,dy),'Stock assembly','Furniture modules','Repeat a stock tabletop over the native footprint; use one selectable table.'
    if s==675 and k==10:
        return category,('static',0xa2cc),'Stock candidate','Parrot figure','Use the stock parrot silhouette on the desk. Its plumage and flying pose differ from the ornament.'
    if s==998:
        if k<=4:return category,('static',0xfb6),'Stock candidate','Smithing prop','Use stock horseshoes for the unheated orientations. Keep the underlying U7 frame.'
        if k==5:return category,layout(part(0xfb6,hue=match_hue((211,82,42)))),'Stock assembly','Heated horseshoes','Apply a hot-metal hue to the same horseshoes.'
        if k in (6,7):return category,('static',0x3755 if k==6 else 0x372d),'Review substitute','Smithing effect','Use a stock sparkle or smoke burst for the transient frame. Check effect size and timing in the smithy.'
    if s==724:
        return category,('static',0xa42a if f>=32 else 0xa429),'Stock candidate','Fellowship emblem','Use the stock Fellowship medallion as the visible symbol and keep the U7 icon interaction. The stock piece includes a cord and needs a mounting-position check.'
    if s==474:
        return category,('static',0x26ac),'Review substitute','Corded throwing weapon','Use the stock bolas as the inventory and ground silhouette for a corded throwing weapon. Keep the sling name, ammunition and combat behavior. Check whether the pouch reads at inventory scale.'
    if s==620:
        return category,('rake',f),'Stock assembly','Approved stock rake','Fit a strip of the stock saw blade across the pitchfork shaft. Repeat a cropped pitchfork prong ten times along its edge.'

    if s in (414,867):
        from remains import known,CREATURE
        if s==867 and k==0:
            return category,('scene',s,f),'Stock assembly','Corpse parts','Use a single precomposed ground sprite at the U7 anchor. The head sits between raised arms, the legs spread downward, and white and blue stock cloth marks the sleeves and trousers. The recipe gives the center, angle and draw order of each piece.'
        if known(s,k):
            return category,('remains',s,f),'Stock assembly' if s==867 or k not in CREATURE else 'Stock candidate','Death pose','Use the final stock death-animation frame and the listed body, hue and visible layers. The source supplies victim identity and inspection behavior.' if s==867 or k not in CREATURE else 'Use the final stock creature death frame. Preserve the source species and identity.'
        if k in (4,5):return category,('static',0x1363),'Stock candidate','Stone remains','Use stock rubble for this stone body.'
        if k in (24,25):return category,('static',0x122a),'Review substitute','Scorched outline','Use the stock ground stain as a silhouette reference. Check it against the dark source outline.'
        if k==26:
            return category,('scene',s,f),'Stock assembly','Pinned gargoyle','Inamo hangs against the stable wall. A pitchfork pins his upper body above a pool of blood on the floor. The complete pose shares one selectable object at the original stable anchor.'
        return category,spec,'Review substitute','Alternate corpse state','The recorded scene uses loose corpse parts. This alternate source silhouette needs its own pose or body-family check.'
    if s==470:return category,('static',0xa300 if f<32 else 0xa301),'Stock candidate','Complete well','Use the stocked well with stone opening and timber superstructure.'
    if s==740:return category,layout(part(0x141),part(0x14f8,0,0,2)),'Stock assembly','Well fittings','Use a timber beam and rope at the source fitting anchor. Omit duplicate supports if the paired well already supplies them.'
    if s in (290,291,322,372):
        id=(0x24f4 if s in (290,291) else 0x24f5) if s in (290,322) else (0x26d0 if s==291 else 0x26d1)
        return category,('static',id),'Stock candidate','Shuttered wall module','Use the stock window-and-shutter module for this state. Replace the backing wall section when integrating it.'
    if s==453 and grade=='Custom art':
        return category,spec,'Stock assembly','Canopy and trunk','Stack the stock foliage and trunk on one tile. Let native state determine fruit and interaction.'
    if s in (293,849,657,678,188,483,0,27,47,232,851,696,1011):
        return category,layout(part(spec[1],hue=tint(im))),'Stock assembly','Stock textile and hue','Use the existing textile or furnishing with the recorded stock hue. Preserve facing and instance identity.'
    if s==837 and k not in (0,):
        return category,layout(part(0xf66),part(0xea0,0,0,7)),'Stock assembly','Easel and painting','Combine stock easel and painting at the canvas location. Use the source frame to select the work in progress.'
    if grade=='Custom art':
        if note.startswith('This alternate frame shares') or s in (178,336,546,756,997) or (s==675 and k in (9,16)):
            return category,spec,'Review substitute','State or silhouette check','The stock family is a candidate. Check the depicted state, scale or identifying detail before accepting it. '+({178:'Check whether the cloth map must be readable.',336:'Verify the light emitter and fixture visibility.',546:'The current plate does not show breakage.',756:'The stock spikes are mounted. Verify that the portable trap reads clearly.',997:'Use an unlit fixture for a spent light.'}.get(s,''))
        if s==668:spec=('static',0xf60)
        
        if s==675 and k==0:spec=('static',0x102a)
        if s==361:spec=layout(part(0xb9b),part(0xbcf,0,0,-3))
        return category,spec,'Stock assembly' if spec[0]=='layout' else 'Stock candidate','Stock substitution','Use the displayed stock form for this object and keep the source name, frame and interaction. Differences in finish or pose are acceptable for this match.'
    return original

