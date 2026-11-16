"""U7 867/0 assembled from stock UO parts. Angles are counterclockwise in image space."""
from functools import lru_cache
from PIL import Image
from town import uo,tile
from costumes import ramp,match_hue
# Center offsets in pixels. Draw order goes from ground to foreground.
PARTS=(
    (0x122a, 0,  4,   0),
    (0x122b, 0,-20,   0),  # Ground pool separates brown hair from the stable floor.
    (0x1dad, 0, -2,  32),  # Opposite stock torso faces toward the head.
    (0x1cef, 0,  8,   0),
    (0x1ce1, 0,-20,   0),
    (0x1da2,-18,-16,-34),
    (0x1db0, 18,-16, 34),
    (0x1db1,-18, 22, 43),
    (0x1da3, 18, 22,-43),
)
# Folded cloth supplies the white sleeve remnants and the blue trouser remnants.
# These are resized cutouts in the composite, with stock hue ramps.
WRAPS=((0x1767,-15,-14,-39,'white'),(0x1767,15,-14,39,'white'),
       (0x1767,-20,23,44,'blue'),(0x1767,20,23,-44,'blue'))
HUES={'white':match_hue((218,216,198)),'blue':match_hue((50,67,193))}
def wrap(item,hue):
    im=uo(item);im=im.crop(im.getbbox()).resize((12,8),Image.Resampling.NEAREST)
    palette=ramp(hue);im.putdata([(*palette[min(31,8+(r>>3))],a) if a else (0,0,0,0) for r,g,b,a in im.getdata()])
    return im
@lru_cache(None)
def render(frame):
    layers=[]
    for item,x,y,angle in PARTS:
        im=uo(item)
        im=im.crop(im.getbbox()).rotate(angle,Image.Resampling.NEAREST,expand=True)
        im=im.crop(im.getbbox());layers.append((im,x-im.width//2,y-im.height//2))
    for item,x,y,angle,color in WRAPS:
        im=wrap(item,HUES[color]).rotate(angle,Image.Resampling.NEAREST,expand=True)
        im=im.crop(im.getbbox());layers.append((im,x-im.width//2,y-im.height//2))
    l=min(x for _,x,y in layers);t=min(y for _,x,y in layers)
    out=Image.new('RGBA',(max(x+i.width for i,x,y in layers)-l,max(y+i.height for i,x,y in layers)-t))
    for im,x,y in layers:out.alpha_composite(im,(x-l,y-t))
    return out.transpose(Image.Transpose.TRANSPOSE) if frame==32 else out
def description(frame):
    ids=' + '.join(f'0x{i:04X}@({x},{y})px rot {a:+d}°' for i,x,y,a in PARTS)
    ids+=' + '+ ' + '.join(f'0x{i:04X}@({x},{y})px cloth 12×8px hue 0x{HUES[c]:04X} +8 ramp steps rot {a:+d}°' for i,x,y,a,c in WRAPS)
    if frame==32:ids+=' · transpose finished sprite on its top-left to bottom-right diagonal'
    return 'scene '+ids,', '.join(dict.fromkeys(tile(i)[0] for i,x,y,a in PARTS))+', white and blue cloth'

