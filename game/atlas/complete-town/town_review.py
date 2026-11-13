"""Stock-art recipes for the eighteen reviewed, town-referenced U7 frames."""
from functools import lru_cache
from PIL import Image, ImageDraw, ImageChops, ImageOps
from town import uo
from costumes import match_hue,ramp

PLATE=0x09D7
GROUPS={
    'Lights':[(336,f) for f in (0,4,6,11,12,13)],
    'Broken dishes':[(546,f) for f in (2,3,4,10,11,15)],
    'Other items':[(178,0),(474,0),(675,9),(675,16),(756,0),(997,2)]
}
KEPT={(178,0):0x14EB,(336,4):0x0B1D}
# Shard masks in trimmed plate coordinates. Keep or scatter subsets for each frame.
SHARDS={
    'left':[(0,1),(6,1),(8,5),(5,8),(8,11),(5,15),(0,15)],
    'top':[(6,0),(17,0),(17,5),(13,6),(10,4),(8,5)],
    'right':[(10,5),(13,7),(17,6),(17,14),(12,14),(9,10),(10,8),(8,6)],
    'base':[(6,9),(9,7),(8,10),(11,14),(5,14),(8,11)]}
# Each piece has a top-left position and a rotation after masking.
DISHES={
    2:('pewter',[('left',0,1,13),('top',4,0,-8)]),
    3:('clay',[('left',0,0,0),('top',5,0,0),('right',8,5,0)]),
    4:('cobalt',[('top',6,0,-26),('left',0,7,11)]),
    10:('ochre',[('left',0,0,-31),('base',6,7,22)]),
    11:('ochre',[('top',1,0,-35),('right',0,12,18)]),
    15:('cobalt',[('base',6,0,32),('right',15,0,17),('top',0,10,-24),('left',12,12,47)])}
HUES={'clay':(173,103,76),'ochre':(187,125,65),'cobalt':(90,92,215),'gold':(187,144,55),'blue':(114,123,230),'ash':(125,120,142)}
LABELS={(336,0):'Short lit candle',(336,6):'Cold candle end',(336,11):'Lit hand torch',(336,12):'Blue-flame taper',(336,13):'Brass taper',(474,0):'Sling cord and pouch',(675,9):'Wooden blotter',(675,16):'Hand mirror',(756,0):'Loose caltrops',(997,2):'Spent candle stub'}
NOTES={(336,0):'A small lit candle keeps the contained item visible in inventory.',(336,6):'The source has a dark rim and pale center. Use a low unlit wax end at its world position.',(336,11):'A lit torch gives the handle and flame the same diagonal as the U7 sprite.',(336,12):'A brass shaft and cool flame distinguish this light from the other hand torches.',(336,13):'A brass shaft carries a warm stock torch flame.',(474,0):'Keep the stock cord loop, remove its weighted ends and fit one leather pouch.',(675,9):'A shallow wooden box forms the base. The top of a stock globe supplies the grip.',(675,16):'A small mirror face and brass grip read as a handheld dressing item.',(756,0):'Three clusters of crossed stock spike tips give a loose, portable trap.',(997,2):'Use an ash-tinted candle end with a dark wick. This is the spent state.'}
def trim(im):
    box=im.getchannel('A').getbbox()
    if not box:raise ValueError('Empty stock cutout')
    return im.crop(box)
@lru_cache(None)
def stock(item):return trim(uo(item))
def dyed(im,name):
    palette=ramp(match_hue(HUES[name]))
    result=im.copy()
    def pixel(r,g,b,a):
        if not a:return (0,0,0,0)
        lum=(r+g+b)/3;rgb=palette[min(31,round(lum/8))]
        glaze=max(0,(lum-130)/95) if name in ('clay','ochre','cobalt','blue') else 0
        return tuple(round(v+(255-v)*min(.85,glaze)) for v in rgb)+(a,)
    result.putdata([pixel(*rgba) for rgba in im.getdata()])
    return result
def place(canvas,im,xy):canvas.alpha_composite(im,xy)
def size(im,w,h):return im.resize((w,h),Image.Resampling.NEAREST)
def rot(im,deg):return trim(im.rotate(deg,Image.Resampling.NEAREST,expand=True))
def dish(f):
    color,parts=DISHES[f];plate=stock(PLATE)
    assert plate.size==(18,15)
    if color!='pewter':plate=dyed(plate,color)
    canvas=Image.new('RGBA',(36,32))
    for name,x,y,angle in parts:
        mask=Image.new('L',plate.size);ImageDraw.Draw(mask).polygon(SHARDS[name],fill=255)
        fragment=plate.copy();fragment.putalpha(ImageChops.multiply(plate.getchannel('A'),mask))
        place(canvas,rot(trim(fragment),angle),(x,y))
    return trim(canvas)
@lru_cache(None)
def render(s,f):
    if s==546:return dish(f)
    if s==336 and f==0:return rot(size(stock(0x142C),5,9),38)
    if s==336 and f==6:return rot(size(stock(0x142F),7,8),32)
    if s==997:return rot(size(dyed(stock(0x142F),'ash'),6,10),38)
    if s==336 and f==11:return rot(size(stock(0x0A12),6,25),40)
    if s==336:
        shaft=stock(0x14F5).transpose(Image.Transpose.FLIP_LEFT_RIGHT)
        shaft=size(shaft,17,17)
        canvas=Image.new('RGBA',(25,25))
        flame=trim(stock(0x0A12).crop((0,0,stock(0x0A12).width,7)))
        if f==12:flame=dyed(flame,'blue')
        place(canvas,shaft,(4,4));place(canvas,rot(flame,36),(0,0))
        return trim(canvas)
    canvas=Image.new('RGBA',(34,34))
    if s==474:
        loop=stock(0x26ac).crop((0,0,15,23));place(canvas,size(trim(loop),10,13),(2,0))
        place(canvas,size(stock(0xe79),8,7),(3,10))
    elif (s,f)==(675,9):
        place(canvas,size(stock(0x9aa),13,7),(0,3))
        place(canvas,size(trim(stock(0x1047).crop((0,0,21,17))),4,4),(5,0))
    elif (s,f)==(675,16):
        handle=rot(stock(0x14f5),45)
        place(canvas,size(handle,3,9),(4,6))
        face=rot(stock(0x4044),-18)
        # Brighten the existing glass pixels while preserving the frame.
        face=face.copy()
        face.putdata([(min(255,r+96),min(255,g+98),min(255,b+118),a) if a and max(r,g,b)-min(r,g,b)<20 else (r,g,b,a) for r,g,b,a in face.getdata()])
        place(canvas,size(face,10,10),(0,0))
    elif s==756:
        tip=trim(stock(0x119a).crop((21,22,30,31)))
        prong=size(tip,6,6)
        prong.putdata([(min(255,round(r*1.35)+24),min(255,round(g*1.35)+24),min(255,round(b*1.35)+24),a) for r,g,b,a in prong.getdata()])
        for x,y in ((0,2),(9,0),(6,9)):
            for angle,dx,dy in ((0,0,0),(90,2,0),(165,1,1)):
                place(canvas,rot(prong,angle),(x+dx,y+dy))
    else:raise ValueError((s,f))
    return trim(canvas)
IDS={(336,0):'0x142C',(336,6):'0x142F',(336,11):'0x0A12',(336,12):'0x14F5 + 0x0A12',(336,13):'0x14F5 + 0x0A12',(474,0):'0x26AC + 0x0E79',(675,9):'0x09AA + 0x1047',(675,16):'0x4044 + 0x14F5',(756,0):'0x119A',(997,2):'0x142F'}
def describe(s,f):
    if s==546:
        color,parts=DISHES[f]
        transform=', '.join(f'{n}@({x},{y}) {a:+d}°' for n,x,y,a in parts)
        return f'0x09D7 · empty plate · {color} · '+transform,color.capitalize()+' plate fragments'
    return IDS[s,f],LABELS[s,f]
def treatment(s,f,category):
    key=s,f
    if key in KEPT:
        return category,('static',KEPT[key]),'Stock candidate','Approved stock match','Keep the stock map for the item icon.' if s==178 else 'Keep the stock candelabra for this branched fixture.'
    if s==546 and f in DISHES:
        return category,('revised',s,f),'Stock assembly','Empty plate fragments','Cut pieces from the stock empty plate, preserving its rim and glaze. '+describe(s,f)[0].split(' · ',2)[2]+'.'
    if key in IDS:
        return category,('revised',s,f),'Stock assembly','Approved stock treatment',NOTES[key]

