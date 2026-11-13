"""Pixel offsets are presentation offsets on one scene anchor, positive right/down."""
from PIL import Image
from town import uo,tile
import pose867
from functools import lru_cache
# The same six pieces and blood graphic are used by ModernUO Corpse.Carve.
def pieces(s,f):
    if (s,f&31)==(414,26):
        parts=[(0x141,0,11),(0x122d,0,14),(0x1d9f,0,0),(0x1da3,-8,8),(0x1da4,8,9),(0x1da1,-10,-7),(0x1da2,10,-8),(0x1da0,0,-15)]
    else:
        raise ValueError((s,f))
    return [(i,-x if f>=32 else x,y) for i,x,y in parts]
@lru_cache(None)
def render(s,f):
    if s==867 and f in (0,32):return pose867.render(f)
    layers=[]
    for i,x,y in pieces(s,f):
        im=uo(i);im=im.crop(im.getbbox())
        layers.append((im,x-im.width//2,y-im.height//2))
    left=min(x for _,x,y in layers);top=min(y for _,x,y in layers)
    out=Image.new('RGBA',(max(x+im.width for im,x,y in layers)-left,max(y+im.height for im,x,y in layers)-top))
    for im,x,y in layers:out.alpha_composite(im,(x-left,y-top))
    return out
def description(s,f):
    if s==867 and f in (0,32):return pose867.description(f)
    p=pieces(s,f)
    return ('scene '+ ' + '.join(f'0x{i:04X}@({x},{y})px' for i,x,y in p),', '.join(dict.fromkeys(tile(i)[0] for i,x,y in p)))

