from costumes import equip, match_hue
from town import tile,tiledata

ITEMS={249:0x1517,285:0x1530,444:0x278e,539:0x13bb,542:0x140a,543:0x1b73,569:0x13cc,572:0x1b7a,574:0x13cb,575:0x13be,579:0x13c6,580:0x1414,582:0x13c7,584:0x2790,585:0x170f,586:0x1413,587:0x170b,588:0x170b,640:0x108a,738:0x1539,801:0xe75,937:0x1089,955:0x1088,1004:0x1db9}
SLOTS={2:'shield hand',3:'feet',4:'pants',5:'shirt',6:'head',7:'hands',8:'finger',10:'neck',12:'waist',13:'torso',17:'outer torso',19:'arms',20:'cloak',21:'backpack',22:'robe',23:'skirt',24:'legs'}
def wearable(s,f):
    k=f&31;i=ITEMS[s];h=0
    if s==249:
        i=0x1517 if k==0 else 0x1f01;h=match_hue([(86,116,53),(198,98,33),(55,76,188)][k])
    if s==285 and k in (0,1):h=match_hue((130,130,130) if k==0 else (66,102,54))
    if s==955 and k==1:i=0xa429
    return ('wearable',i,h)
def data(i):
    layer=tiledata[512*964+i//32*1316+4+i%32*41+9]
    assert layer>0 and equip(i,400)>0,(i,layer)
    return layer,SLOTS.get(layer,str(layer)),equip(i,400)
def detail(i,h):
    layer,slot,animation=data(i)
    return f'item 0x{i:04X} · layer {layer} ({slot}), animation 0x{animation:04X}'+(f', hue 0x{h:04X}' if h else ''),tile(i)[0]

