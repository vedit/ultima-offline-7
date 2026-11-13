from functools import lru_cache
import struct
from PIL import Image,ImageOps
from town import U,tile,tiledata

HUES=(U/'hues.mul').read_bytes()
CONVERT={}
for line in (U/'Equipconv.def').read_text(errors='replace').splitlines():
    cols=line.split('#')[0].split()
    if len(cols)>=5 and all(v.isdecimal() for v in cols[:5]):
        b,e,g,_,h=map(int,cols[:5]);CONVERT[b,e]=(g,h)
def equip(id,base):
    off=512*964+id//32*1316+4+id%32*41
    anim=struct.unpack_from('<H',tiledata,off+14)[0]
    return CONVERT.get((base,anim),(anim,0))[0]
def rgb(v):return tuple(((v>>k)&31)*255//31 for k in (10,5,0))
def ramp(hue):
    h=hue-1;at=(h//8)*708+4+(h%8)*88
    return [rgb(v) for v, in struct.iter_unpack('<H',HUES[at:at+64])]
@lru_cache(None)
def match_hue(color,skin=False):
    domain=range(1002,1059) if skin else range(2,1001)
    return min(domain,key=lambda h:sum((x-y)**2 for x,y in zip(ramp(h)[22],color)))
COLORS={'umber':(130,82,50),'russet':(167,93,42),'saffron':(195,151,45),'blue':(48,70,164),'slate':(88,94,111),'cream':(202,188,150),'grey':(151,148,135),'gold':(223,181,74),'red':(159,47,45),'purple':(145,48,111),'green':(85,108,57),'orange':(188,105,36),'dark':(60,47,43),'white':(216,204,183)}
def gear(item,color=''):return item,match_hue(COLORS[color]) if color else 0
HAIR=0x203b;LONG=0x203c;BEARD=0x203f;PANTS=0x1539;SHIRT=0x1517;BOOTS=0x170b;SHOES=0x170f;TUNIC=0x1fa1;VEST=0x1f7b;SKIRT=0x1516;ROBE=0x1f03;CHAIN=0x13bf;HELM=0x140a;SURCOAT=0x1ffd;APRON=0x153b;LEATHER=0x13cc
# Back-to-front ClassicUO equipment passes, with outer garments drawn over the inner shirt.
WARDROBES={
318:('Klog / sage',400,[(PANTS,'umber'),(SHOES,'dark'),(ROBE,'umber'),(LONG,'russet')]),
319:('Petre / stablekeeper',400,[(PANTS,'umber'),(BOOTS,'dark'),(SHIRT,'cream'),(VEST,'saffron'),(HAIR,'dark')]),
445:('Chantu / healer',400,[(PANTS,'umber'),(SHOES,'dark'),(ROBE,'umber'),(LONG,'grey'),(BEARD,'grey')]),
447:('Wounded man',400,[(0x152e,'umber'),(SHIRT,'white'),(HAIR,'umber')]),
451:('Finnigan / mayor',400,[(PANTS,'slate'),(BOOTS,'dark'),(SHIRT,'white'),(TUNIC,'blue'),(HAIR,'grey')]),
452:('Caroline / Ellen',401,[(SHOES,'dark'),(SHIRT,'cream'),(SKIRT,'umber'),(LONG,'russet')]),
454:('Apollonia / innkeeper',401,[(SHOES,'dark'),(SHIRT,'cream'),(SKIRT,'orange'),(APRON,'russet'),(LONG,'umber')]),
455:('Dell / Gargan',400,[(PANTS,'umber'),(BOOTS,'dark'),(SHIRT,'orange'),(VEST,'russet'),(HAIR,'dark')]),
462:('Markus / fighter',400,[(PANTS,'slate'),(BOOTS,'umber'),(CHAIN,''),(APRON,'russet'),(HAIR,'umber')]),
465:('Iolo',400,[(PANTS,'umber'),(BOOTS,'dark'),(SHIRT,'cream'),(LEATHER,'umber'),(LONG,'grey'),(BEARD,'grey')]),
489:('Spark',400,[(0x152e,'green'),(SHOES,'umber'),(SHIRT,'saffron'),(VEST,'umber'),(HAIR,'gold')]),
720:('Johnson / Gilberto',400,[(PANTS,'slate'),(BOOTS,'dark'),(CHAIN,''),(SURCOAT,'purple'),(HELM,'')]),
721:('Avatar',400,[(PANTS,'slate'),(BOOTS,'dark'),(CHAIN,''),(SURCOAT,'red'),(LONG,'gold')]),
806:('Doug / Bob',400,[(PANTS,'slate'),(BOOTS,'dark'),(CHAIN,''),(SURCOAT,'purple'),(HELM,'')])}
SKIN=match_hue((186,139,103),True)
def clothing(s):return [gear(i,c) for i,c in WARDROBES[s][2]]
def itemname(i):return {0x203b:'short hair',0x203c:'long hair',0x203f:'short beard'}.get(i,tile(i)[0])
@lru_cache(None)
def frame(anim,act,d,phase,hue):
    rec=35000+(anim-400)*175+act*5+d
    with (U/'anim.idx').open('rb') as fd:
        fd.seek(12*rec);off,n,_=struct.unpack('<iii',fd.read(12))
    if off<0 or n<524: raise ValueError(f'Missing equipped frame {anim}/{act}/{d}')
    with (U/'anim.mul').open('rb') as fd:fd.seek(off);buf=fd.read(n)
    pal=[rgb(v) for v, in struct.iter_unpack('<H',buf[:512])]
    if hue:
        colors=ramp(hue);pal=[colors[r>>3] for r,g,b in pal]
    count,=struct.unpack_from('<I',buf,512)
    pos=512+struct.unpack_from('<I',buf,516+4*(phase%count))[0]
    cx,cy,w,h=struct.unpack_from('<4h',buf,pos);pos+=8
    if w<=0 or h<=0:raise ValueError(f'Empty silhouette {anim}/{act}/{d}')
    im=Image.new('RGBA',(w,h));pix=im.load()
    while True:
        tag,=struct.unpack_from('<I',buf,pos);pos+=4
        if tag==0x7fff7fff:break
        x=cx+(((tag>>22)&1023)^512)-512;y=cy+h+(((tag>>12)&1023)^512)-512
        for j in range(tag&4095):pix[x+j,y]=(*pal[buf[pos+j]],255)
        pos+=tag&4095
    return im,(-cx,-cy-h)
@lru_cache(None)
def costume(s,f):
    name,b,_=WARDROBES[s];d,mir=[(3,False),(1,False),(3,True),(1,True)][f//16%4]
    pose=f%16
    act=[4,0,0,7,9,9,9,12,12,12,4,32,32,21,16,16][pose]
    phase=[0,1,3,0,0,2,4,0,2,4,0,2,3,-1,2,3][pose]
    layers=[(b,SKIN)]+[(equip(i,b),h) for i,h in clothing(s)]
    try:pieces=[frame(anim,act,d,phase,hue) for anim,hue in layers]
    except ValueError:
        act,phase=4,0
        pieces=[frame(anim,act,d,phase,hue) for anim,hue in layers]
    left=min(x for _,(x,y) in pieces);top=min(y for _,(x,y) in pieces)
    right=max(x+im.width for im,(x,y) in pieces);bottom=max(y+im.height for im,(x,y) in pieces)
    out=Image.new('RGBA',(right-left,bottom-top))
    for im,(x,y) in pieces:out.alpha_composite(im,(x-left,y-top))
    return (ImageOps.mirror(out) if mir else out),act,d,phase,mir
def costume_desc(s):
    return ', '.join(f'{color+" " if color else ""}{itemname(i)}' for i,color in WARDROBES[s][2])
def costume_ids(s):
    return f'body 0x{WARDROBES[s][1]:04X} hue 0x{SKIN:04X} · '+', '.join(f'0x{i:04X}/0x{h:04X}' for i,h in clothing(s))


