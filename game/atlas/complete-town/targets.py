from town import *
import re,zlib,math
from PIL import ImageStat,ImageOps
from functools import lru_cache
from u7uo.walking import STATIC_RULES
from u7uo.shore import PROJECTION
from mapping import RULES
from install_paths import INSTALL
EXULT=INSTALL/'Tools/Exult-Source-v1.12.1/data/bg/shape_info.txt'
frame_names={}
for line in EXULT.read_text().split('%%section framenames')[1].split('%%endsection')[0].splitlines():
    if line.startswith(':'):
        row=list(map(int,line[1:].split('/')))
        if len(row)==5 and row[2:4]==[-1,0] and row[1]>=0:
            i=row[4]+0x500
            if i<len(flex_directory(text)):
                frame_names[row[0],row[1]]=member(text,i).rstrip(b'\0').decode('cp437')
def clean(name):
    if '/' in name:
        t=name.split('/')
        if len(t)==4:name=t[0]+t[1]+t[2]
    return name.strip()
def land(i):
    off,hd,n,_,_,_,flag=entries[art_key(i)]; raw=archive[off+hd:off+hd+n]
    if flag==1:raw=zlib.decompress(raw)
    assert len(raw) in (2024,2048)
    raw=raw[:2024]
    im=Image.new('RGBA',(44,44)); p=im.load()
    for (idx,_),(v,) in zip(PROJECTION,struct.iter_unpack('<H',raw),strict=True):
        p[idx%44,idx//44]=tuple(((v>>k)&31)*255//31 for k in (10,5,0))+(255,)
    return im
land=lru_cache(None)(land)
def landname(i):
    off=i//32*964+4+i%32*30
    return tiledata[off+10:off+30].split(b'\0')[0].decode('ascii','replace')
@lru_cache(None)
def body(i,action,direction,phase,mirror):
    record=(i*110 if i<200 else 22000+(i-200)*65 if i<400 else 35000+(i-400)*175)+action*5+direction
    with (U/'anim.idx').open('rb') as idx:
        idx.seek(record*12);off,n,_=struct.unpack('<iii',idx.read(12))
    if off<0 or n<524:raise ValueError('Empty body group')
    with (U/'anim.mul').open('rb') as data:
        data.seek(off);b=data.read(n)
    colors=[tuple(((v>>k)&31)*255//31 for k in (10,5,0))+(255,) for v, in struct.iter_unpack('<H',b[:512])]
    count,=struct.unpack_from('<I',b,512); phase%=count
    pos=512+struct.unpack_from('<I',b,516+4*phase)[0]
    cx,cy,w,h=struct.unpack_from('<4h',b,pos);im=Image.new('RGBA',(w,h));pix=im.load();pos+=8
    while True:
        v,=struct.unpack_from('<I',b,pos);pos+=4
        if v==0x7fff7fff:break
        x=(v>>22)&1023;y=(v>>12)&1023;n=v&4095
        x=cx+(x^512)-512;y=cy+h+(y^512)-512
        for j in range(n):pix[x+j,y]=colors[b[pos+j]]
        pos+=n
    return ImageOps.mirror(im) if mirror else im
bodyids={318:400,319:400,445:400,447:400,451:400,452:401,454:401,455:400,462:400,465:400,489:400,495:201,496:217,720:400,721:400,727:200,806:400,970:207}
def actor_target(s,f):
    i=bodyids[s]
    # Pick a three-quarter direction for each of the four source banks.
    d,flip=[(1,False),(1,True),(3,True),(3,False)][(f//16)%4]
    action= (4 if i>=400 else 2) if f%16==0 else 0
    if f%16>=3:action=4 if i>=400 else 2
    phase=1 if f%16==2 else 0
    return ('body',i,action,d,phase,flip)
def target(spec):
    kind,*ids=spec
    if kind=='body':return body(*ids)
    if kind=='land':return land(ids[0])
    if kind=='hidden':return None
    ims=[uo(i) for i in ids]
    w=max(im.width for im in ims);h=max(im.height for im in ims);im=Image.new('RGBA',(w,h))
    for p in ims:im.alpha_composite(p,((w-p.width)//2,h-p.height))
    return im
def idtext(spec):
    kind,*ids=spec
    if kind=='body':return f'body 0x{ids[0]:04X} · action {ids[1]}, dir {ids[2]}, frame {ids[3]}'+(' mirrored' if ids[4] else '')
    if kind=='hidden':return 'No visible UO item'
    return kind+' '+' + '.join(f'0x{i:04X}' for i in ids)
def title(s,f):
    return clean(frame_names.get((s,f&31),names[s])) or 'Unnamed terrain'
# Target candidates chosen by meaning; multiple IDs represent alternate stock sprites.
pools={}
def pool(shapes,ids):
    for s in shapes.split():pools[int(s)]=tuple(int(i,16) for i in ids.split())
pool('178','14EB');pool('211','6A5 6AD');pool('232','1586 1590');pool('249','E14 E15');pool('264','821 822');pool('276 277','129 12A');pool('285','1515 1530');pool('336 338 997','A0F A26 B1D');pool('257','16C 18A');pool('272','6F5');pool('314','CB0 CC7');pool('340','F06 F07 F08 F09 F0A F0B F0C F0D')
pool('361 379','BCF BD0 B9B B9C');pool('378 420 421 422 538','839 83A 85C 85D');pool('388','9F8 9E2 9F9 9A3');pool('407','B49 B4A');pool('414 867','2006 1D9F 1DA0');pool('415','10EE 10EF 10F0 10F1');pool('416','A2C A30');pool('426 427 428 429 430','7A3 7A4 7A5');pool('431','197A 1986');pool('444','1515 1718');pool('474','13B2');pool('522','E42 E43');pool('539','13BB');pool('542 1004','140A 1408 1DB9');pool('543','1B73');pool('546','9D7 9D8');pool('561 591 594','F51 F52');pool('569','13CC');pool('572','1B7A');pool('574','13CB');pool('579','13C6');pool('580','1414');pool('582','13C7');pool('584','153B');pool('585','170F');pool('586','1413');pool('587 588','170B 170C');pool('589','E87');pool('590','13B4');pool('593','F49');pool('595','F6B');pool('596 659','F5C 143B');pool('597','13B2');pool('598','F50');pool('599','F60 13B9');pool('600','1439');pool('601','1443');pool('614','EC3');pool('615','EC4');pool('616','F0E F0F 99B');pool('620','F39');pool('622','166E');pool('623','102A 13E3');pool('625','F39 0F3A');pool('627','14FB');pool('628','995 9CA 9EF');pool('633 847 890 971 1000 1003 1018','B7C B7D B7E B8F B90');pool('640','108A');pool('641','100E 100F 1010');pool('642','FEF FF0 FF1 FF2');pool('644','EED EEE EEF');pool('646','1BE9');pool('650','1057');pool('668','1BF4');pool('675','FBF FB1 FF1 E34');pool('677','1039');pool('696 1011','A7D A82 A5B A63');pool('697','B49 B4A');pool('710','1034');pool('713','9 17');pool('717','9D7');pool('719','B41 B42');pool('722','F3F');pool('723','1BFB');pool('736 737 738 739','DE3');pool('738','1539 152E');pool('739','DE3 DE9');pool('756','F7E');pool('760','F16 F18 F21 F26');pool('787','108C 108D');pool('797','EF3 E34');pool('798 799','9A8 E80');pool('800','E42 E43');pool('801','E75');pool('802','E76');pool('803','9B1');pool('804','E3C E3D');pool('810','14E0');pool('824','9D6');pool('827','E21');pool('828 845 366','1B 6');pool('851','1766 1767');pool('863','9D7 9E3 9F3');pool('872 986','930 92B');pool('873 897 292','B2C B2D B4E B4F B50 B51 B5E B5F');pool('885','E89');pool('893','1797 1798');pool('907 911 1020 1022 736 737','1797 1798');pool('912','122A 122B 122C 122D');pool('937 955','1088 1089');pool('944','9E0 9F3 9DF');pool('949 950','1EAC');pool('982','8D6 8D7');pool('991','FAF FB0');pool('995','974');pool('164','595');pool('724','1D98');pool('740','14E7');pool('470','AA25')
# A simple treatment for derived material-only references.
architecture={'wall','fortress','crenellations','pillar','pedestal','slate roof','tile roof','wood roof','chimney','window','stairs','crossbeam','floor','fence','post'}
def feature(im):
    im=im.crop(im.getbbox()).convert('RGBA');w,h=im.size
    weights=im.getchannel('A')
    mean=ImageStat.Stat(im.convert('RGB'),weights).mean
    return (math.log(w/h),*[v/255 for v in mean])
@lru_cache(None)
def target_feature(spec):return feature(target(spec))
def closest(im,specs):
    key=feature(im)
    return min(specs,key=lambda spec:sum((a-b)**2 for a,b in zip(key,target_feature(spec))))
LAND={2:0xa8,8:0xa8,19:0xa8,20:0xa8,26:0xa8,64:0xa8,65:0xa8,4:3,35:3,45:3,46:3,146:3,147:3,148:3,118:0x16,119:0x16,120:0x16,121:0x16,122:0x16,124:0x16,130:0x16,**{s:0x79 for s in range(134,146)},149:0x79,23:0x79,25:0x79,24:0x3e9,10:0x16,17:0x296,18:0x201,21:0x201,48:1}
def classify(s,f,im):
    prev=RULES.get((s,f))
    if prev and prev[1]:
        category,ids,grade,note=prev
        return category,('static',*ids),grade,'First atlas · visual review',note
    if s in (275,607):
        return 'Engine markers',('hidden',),'No visible art','Native marker','Keep as a trigger or route marker. The diagnostic shape is visible here for identification.'
    if s in bodyids:
        animal=s in (495,496,727,970)
        return 'Actors',actor_target(s,f),'Stock candidate' if animal and f%16<3 else 'Custom art','Body reference','Stock animal body and approximate pose.' if animal else 'Stock human animation supplies scale and facing. Match the native costume, body and pose with layers or custom frames.'
    if s in LAND:
        first=LAND[s];n=1 if s==48 else 4
        available=[('land',i) for i in range(first,first+n) if art_key(i) in entries]
        choice=closest(im,available)
        mixed=s in {2,19,20,26,64,65,25,46,118,119,120,121,122,124,130,*range(134,146)}
        return 'Terrain',choice,'Custom art' if mixed else 'Stock candidate','Material and color comparison','Preserve the original transition mask, rut or pixel pattern in projected land art.' if mixed else 'Selected among stock tiles of the same material. Compare the tiling pattern in scene.'
    if s in (0,27,47):
        return 'Textiles',('static',0x0ac9),'Custom art','Material reference','Project the original weave, pattern and edge connection. A stock carpet tile supplies the material reference.'
    if s==453:
        choice={6:(0xd9c,0xd9e),7:(0xcd0,0xcd1),8:(0xcd3,0xcd4)}[f]
        return 'Trees',('static',*choice),'Custom art','Variant reference','No initial placement here. Match the canopy, trunk and roots of this alternate frame.'
    byframe={(388,0):0x9f8,(388,8):0x9a3,(388,10):0x9a5,
             (675,0):0x102a,(675,1):0xfbf,(675,2):0xfbf,(675,6):0xe34,(675,9):0xe34,(675,10):0x2fb6,(675,11):0x2936,(675,13):0xe34,(675,16):0x4044}
    ids=(byframe[s,f],) if (s,f) in byframe else pools.get(s)
    if s==377:
        ids=food_ids(s,f)
    if ids is None and any(k[0]==s for k in RULES):
        ids=tuple(dict.fromkeys(a for k,v in RULES.items() if k[0]==s for a in v[1]))
        if not ids:ids=(0x1d98,) if s==724 else (0x14e7,)

    if not ids and s in STATIC_RULES:ids=(STATIC_RULES[s][1],)
    if not ids and (s,f) in RULES:raise ValueError((s,f))
    if not ids:raise ValueError(('unmapped shape',s,names[s]))
    specs=tuple(('static',i) for i in ids if art_key(0x4000+i) in entries)
    choice=closest(im,specs)
    if s in (270,376):return 'Doors',choice,'Custom art','Alternate leaf','Draw the full native span and matching panel hardware for this alternate state.'
    if s in (724,740):return 'Decorations',choice,'Custom art','Reference only',RULES[s,f][3] if (s,f) in RULES else 'Preserve the source silhouette and attachment.'
    if s in (211,257,271,272):return 'Doors',choice,'Custom art','Reference only','Recreate the native opening, broken leaf or grille footprint and preserve anchor and state.'
    if names[s] in architecture:
        return 'Architecture',choice,'Custom art','Material reference','Match the native span, orientation and join at the neighbouring tile. Stock art supplies the construction material.'
    custom_shapes={178,232,620,697,249,264,336,338,361,379,414,444,474,546,584,588,622,668,675,696,710,739,756,837,851,863,867,885,893,907,911,937,949,950,986,997,1011,1020,1022,736,737}
    grade='Custom art' if s in custom_shapes else 'Stock candidate'
    return 'Objects',choice,grade,'Stock family comparison',('A stock reference for material or use. Recreate the frame-specific design or assembly.' if grade=='Custom art' else 'Stock item candidate selected within its object family. Confirm facing and proportions in scene.')


pool('616','F0E 99B 9C7');pool('620','E87');pool('625','F39 F3A');pool('584','2790');pool('756','119A');pool('249','E14');pool('1004','1DB9');pool('542','140A 1408');pool('276 277','12A');pool('873','B4E B4F B50 B51');pool('388','9A3 9A5 9F8');pool('675','FBF E34 FF1');pool('378 420 421 422 538','85C 85D');pool('426 427 428 429 430','7A4 7A5');pool('164','595')
LABELS=defaultdict(list)
for item in range(0x4000):
    label=tile(item)[0].lower().replace('%s%','').strip()
    if label and art_key(0x4000+item) in entries:LABELS[label].append(item)
def food_ids(s,f):
    label=title(s,f).lower()
    if label in LABELS:return tuple(LABELS[label][:4])
    return ({'bread':(0x103b,0x98c),'mutton':(0x160a,),'beef':(0x9f1,),'sausages':(0x9c0,),'rolls':(0x9ea,),
        'ham':(0x9c9,),'meat':(0x9f1,),'fish':(0x97a,),'food item':(0x9d8,)}.get(label,(0x9d8,)))
pool('575','13BE');pool('583','A58 A59');pool('602','F5E 13B9')
