"""Build the standalone stock construction and wardrobe reference."""
import base64, csv, io, json, struct
from pathlib import Path
from html import escape
from costumes import WARDROBES, clothing, equip, itemname, SKIN, costume, costume_desc
from reuse import assemble, part
from town import BASE, U, src, uo, digest, tiledata, tile

WRONG = Path('E:/UltimaOffline/Tools/ModernUO/Distribution/Data/Decoration/Britannia/_wrong.cfg')
def witness():
    doors = {}
    group = None
    for line in WRONG.read_text().splitlines():
        words=line.strip().split()
        if not words or words[0].startswith('#'):continue
        if words[0][0].isalpha():
            group = int(words[1],16) if words[0] in ('BarredMetalDoor','SecretDungeonDoor') else None
        elif group is not None and group not in doors:
            doors[group]=tuple(map(int,words[:3]))
    assert {0x685,0x687,0x68d,0x68f,0x693,0x318,0x31a}<=doors.keys()
    walls={0x241:(5786,551,10),0x242:(5785,545,10),0x243:(5786,552,10),0x244:(5796,558,10)}
    with (U/'staidx0.mul').open('rb') as idx,(U/'statics0.mul').open('rb') as dat:
        for item,(x,y,z) in walls.items():
            idx.seek(12*(x//8*512+y//8));off,length,_=struct.unpack('<iii',idx.read(12))
            dat.seek(off)
            assert (item,x%8,y%8,z) in [a[:4] for a in struct.iter_unpack('<HBBbH',dat.read(length))]
    return doors,walls
def pic(im,label):
    im=im.crop(im.getbbox());b=io.BytesIO();im.save(b,format='PNG')
    data=base64.b64encode(b.getvalue()).decode()
    return f'<figure><div><img alt="{escape(label)}" width="{round(im.width*min(4,130/im.width,103/im.height))}" src="data:image/png;base64,{data}"></div><figcaption>{escape(label)}</figcaption></figure>'
def card(name,figures,description):
    return f'<article><h3>{escape(name)}</h3><aside>{"".join(pic(i,l) for i,l in figures)}</aside><p>{escape(description)}</p></article>'
def build(out):
    from scene_parts import render,description
    from remains import stock,describe
    doors,walls=witness()
    doc=['<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Trinsic · Stock outfits and dungeon pieces</title><style>*{box-sizing:border-box}body{margin:0;background:#182125;color:#edf1e8;font:16px/1.45 Segoe UI,sans-serif}main{max-width:1350px;margin:auto;padding:24px clamp(14px,4vw,56px)}h1,h2,h3{font-family:Georgia,serif;font-weight:400}h1{font-size:clamp(34px,4vw,52px);margin:16px 0}h2{font-size:30px}section{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(290px,100%),1fr));gap:14px}article{background:#263237;border-radius:7px;padding:14px}article p,figcaption{color:#bfcecb}h3{font-size:23px;margin:0 0 9px}aside{display:flex;gap:6px}figure{margin:0;flex:1;min-width:0}figure div{background:#354247;display:grid;place-items:center;height:110px}img{max-width:100%;object-fit:contain;image-rendering:pixelated}figcaption{font:13px/1.5 Consolas,monospace}a{color:#adddd1}p{max-width:86ch}</style><main><a href="index.html">← Town atlas</a><h1>Trinsic in stock UO art</h1><h2>Gates and dungeon construction</h2><p>Trinsic’s portcullises lift. Wrong’s barred doors swing. The two families have different movement and placement rules. Coordinates below identify examples in the local UO data.</p><section>']
    for s,id in [(271,0x6f6),(272,0x6f5)]:
        dx,dy=(1,4) if s==271 else (4,1)
        panels=tuple(part(id,-x,-y) for x in range(dx) for y in range(dy))
        doc.append(card('Lifting portcullis',[(src(s,0)[0],f'U7 {s}/0'),(assemble(panels),f'UO 4 × 0x{id:04X}')],'Use four linked sections and raise them together.'))
    for id in (0x685,0x68d):
        doc.append(card('Hinged cell door',[(uo(id),f'Closed 0x{id:04X}'),(uo(id+1),f'Open 0x{id+1:04X}')],f'Wrong at {doors[id]}. Use this pair for a hinged iron grille.'))
    for id,n in ((0x241,'Dungeon wall'),(0x242,'Return wall'),(0x243,'Wall corner'),(0x244,'Pillar')):
        doc.append(card(n,[(uo(id),f'UO 0x{id:04X}')],f'Installed map static in Wrong at {walls[id]}.'))
    doc.extend([card('Fixed iron enclosure',[(uo(i),f'0x{i:04X}') for i in (0x821,0x822,0x823)],'Two directions and a corner form a fixed enclosure. The U7 object named “iron bars” is loose scrap.'),
                card('Concealed dungeon door',[(uo(0x318),'Closed 0x0318'),(uo(0x319),'Open 0x0319')],f'Masonry-faced hinged door. Wrong uses 0x0318 at {doors[0x318]}.'),
                '</section><h2>Human bodies and outfits</h2><p>Each pair shows U7 frame 16 and a UO body wearing stock equipment on the same animation anchor. Residents sharing a U7 shape share a recipe. Spark uses an adult body. Seated and prone poses use representative animations. <a href="outfits.csv">Download body, equipment, animation and hue IDs</a>.</p><section>'])
    heading=doc.pop().split('</section><h2>Human bodies and outfits</h2>')
    doc.append('</section><h2 id="corpses">The murder scene</h2><p>The UO corpse-carving implementation places a torso, head, both arms, both legs and blood in the world. The floor victim uses opposing stock limb facings, rotated into the spread pose, with dyed cloth remnants. Its recipe lists each sprite in draw order with counterclockwise rotation in degrees. Rotate each cropped piece before placing its center. Frame 32 transposes the finished composition to follow the U7 reflection. The mounted victim uses a tighter arrangement over timber. Other frames use a human or creature death pose, with skin tone and worn equipment chosen per frame. Pixel offsets are measured from each cropped sprite’s center, positive right and down, relative to the scene anchor.</p><section>')
    doc.append(card('Mounted remains · recorded in town',[(src(414,26)[0],'U7 414/26'),(render(414,26),'UO carved parts on timber')],description(414,26)[0]))
    doc.append(card('Dismembered remains on the floor · recorded in town',[(src(867,0)[0],'U7 867/0'),(render(867,0),'UO ground arrangement')],description(867,0)[0]))
    for s,f in [(867,1),(867,2),(867,3),(414,18),(414,27),(414,28),(414,2)]:
        ids,name=describe(s,f)
        doc.append(card(name.split(' · ')[0],[(src(s,f)[0],f'U7 {s}/{f}'),(stock(s,f),'UO final death frame')],'Available variant. '+ids))
    doc.append('</section><h2>Human bodies and outfits</h2>'+heading[1])
    with (out/'outfits.csv').open('w',encoding='utf-8-sig',newline='') as f:
        writer=csv.writer(f);writer.writerow(['u7_shape','character','body','skin_hue','draw_order','layer','item','equipment_animation','name','hue'])
        for s,(name,b,_) in WARDROBES.items():
            doc.append(card(name,[(src(s,16)[0],f'U7 {s}/16'),(costume(s,16)[0],f'UO body 0x{b:04X}')],costume_desc(s)))
            for j,(i,h) in enumerate(clothing(s),1):
                at=512*964+i//32*1316+4+i%32*41
                writer.writerow([s,name,f'0x{b:04X}',f'0x{SKIN:04X}',j,tiledata[at+9],f'0x{i:04X}',f'0x{equip(i,b):04X}',itemname(i),f'0x{h:04X}'])
    doc.append('</section><p><a href="stock-sources.json">Dungeon placements and source fingerprints</a></p></main></html>')
    (out/'stock-study.html').write_text(''.join(doc),'utf8')
    evidence={'doors_from_decoration':{hex(i):pos for i,pos in doors.items()},'walls_from_statics':{hex(i):pos for i,pos in walls.items()},'input_sha256':{str(p):digest(p) for p in [WRONG,WRONG.parents[4]/'Projects/UOContent/Items/Misc/Corpses/Corpse.cs',U/'staidx0.mul',U/'statics0.mul']}}
    (out/'stock-sources.json').write_text(json.dumps(evidence,indent=2)+'\n','utf8')
if __name__=='__main__':build(BASE/'atlas')
