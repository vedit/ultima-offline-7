"""Stock final animation frames for distinct U7 bodies."""
from functools import lru_cache
from PIL import Image,ImageOps
from costumes import frame,gear,clothing,equip,itemname,match_hue,WARDROBES
from targets import body,uo,tile

# Each entry chooses the clothes visible on the source frame.
PANTS=0x1539; SHIRT=0x1517; ROBE=0x1f03; HAIR=0x203b; LONG=0x203c; BOOTS=0x170b
GREY=(169,126,98); LIGHT=(211,162,122); TAN=(165,109,77); BROWN=(125,81,57)
# name, base, complexion, visible layers
HUMANS={
7:('Kissme',400,TAN,[(PANTS,'blue'),(SHIRT,'saffron')]),
9:('Grey-clothed body',400,GREY,[(PANTS,'slate'),(SHIRT,'grey'),(HAIR,'russet')]),
12:('Blue-clothed body',400,LIGHT,[(PANTS,'slate'),(SHIRT,'blue'),(BOOTS,'white')]),
13:('Lord British',400,LIGHT,[(ROBE,'purple'),(LONG,'gold')]),
15:('Blue-robed body',400,GREY,[(ROBE,'blue'),(HAIR,'grey')]),
16:('Batlin',400,TAN,[(PANTS,'umber'),(SHIRT,'umber')]),
17:('Thief',400,TAN,[(PANTS,'slate'),(SHIRT,'dark')]),
18:('Iolo',400,GREY,WARDROBES[465][2]),
19:('Shamino',400,TAN,[(PANTS,'umber'),(SHIRT,'green'),(BOOTS,'umber')]),
20:('Dupre',400,GREY,[(PANTS,'slate'),(0x13bf,''),(0x1ffd,'red')]),
21:('Spark',400,LIGHT,WARDROBES[489][2]),
22:('Jaana',401,LIGHT,[(0x1516,'orange'),(SHIRT,'russet'),(LONG,'umber')]),
23:('Time Lord',400,GREY,[(PANTS,'umber'),(SHIRT,'slate'),(LONG,'grey')]),
27:('Unclothed woman',401,LIGHT,[]),28:('Unclothed man',400,TAN,[]),
30:('Blue-clothed body',400,LIGHT,[(PANTS,'dark'),(SHIRT,'blue'),(BOOTS,'white')]),
31:('Blue-clothed body',400,LIGHT,[(PANTS,'dark'),(SHIRT,'blue'),(BOOTS,'white')])}
VICTIMS={
0:('Victim in white and blue',400,LIGHT,[(PANTS,'blue'),(0x13cd,'white'),(HAIR,'umber')]),
1:('Victim in torn blue clothing',400,BROWN,[(0x152e,'blue'),(HAIR,'umber')]),
2:('Victim in green clothing',401,TAN,[(0x152e,'green'),(SHIRT,'saffron'),(LONG,'russet')]),
3:('Unclothed victim',400,TAN,[]),
4:('Brown-clothed body',400,BROWN,[(PANTS,'umber'),(SHIRT,'umber')])}
CREATURE={1:('Noble gargoyle',4,2),2:('Gargoyle healer',4,3),3:('Red creature remains',4,2),6:('Honest fox · stock canine',225,8),10:('Sherry · stock rat',238,8),14:('Noble gargoyle',4,3)}
def human(s,k):return (VICTIMS if s==867 else HUMANS)[k]
def known(s,k):return s==867 or k in HUMANS or k in CREATURE
def orientation(s,f):return (21+(f&1),1 if (f&31) in (12,30) else 3,f>=32)
@lru_cache(None)
def stock(s,f):
    k=f&31;act,d,flip=orientation(s,f)
    if s==414 and k in CREATURE:
        _,b,action=CREATURE[k];return body(b,action,d,-1,flip)
    _,base,skin,items=human(s,k)
    draw=[frame(base,act,d,-1,match_hue(skin,True))]
    for i,color in items:
        _,h=gear(i,color);draw.append(frame(equip(i,base),act,d,-1,h))
    l=min(x for _,(x,y) in draw);t=min(y for _,(x,y) in draw)
    r=max(x+im.width for im,(x,y) in draw);b=max(y+im.height for im,(x,y) in draw)
    out=Image.new('RGBA',(r-l,b-t))
    if s==867 and k<4:
        stain=uo(0x122a);stain=stain.crop(stain.getbbox());out.alpha_composite(stain,((out.width-stain.width)//2,(out.height-stain.height)//2))
    for im,(x,y) in draw:out.alpha_composite(im,(x-l,y-t))
    if s==867 and k in (0,1,2,3):
        injury=uo(0x122c);injury=injury.crop(injury.getbbox())
        out.alpha_composite(injury,((out.width-injury.width)//2,(out.height-injury.height)//2))
    return ImageOps.mirror(out) if flip else out
def describe(s,f):
    k=f&31;act,d,flip=orientation(s,f)
    if s==414 and k in CREATURE:
        n,b,act=CREATURE[k];return f'body 0x{b:04X} · death action {act}, dir {d}, final frame'+(' mirrored' if flip else ''),n
    n,b,skin,items=human(s,k)
    outfit=', '.join(f'0x{i:04X}/0x{gear(i,c)[1]:04X}' for i,c in items)
    return (f'body 0x{b:04X} hue 0x{match_hue(skin,True):04X} · death action {act}, dir {d}, final frame'+(' mirrored' if flip else '')+(' · '+outfit if outfit else ' · bare base')+(' · ground blood 0x122A, injury overlay 0x122C' if s==867 and k<4 else ''),n+' · '+(', '.join((c+' '+itemname(i)).strip() for i,c in items) if items else 'no worn equipment'))

