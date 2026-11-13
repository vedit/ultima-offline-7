"""Assemble all U7 rake facings from texture cutouts of the installed UO art."""
from functools import lru_cache
from PIL import Image
from town_review import stock, trim, rot, size

PITCHFORK=0x0E87
SAW=0x1034
RECIPE='0x0E87 pitchfork shaft and repeated prong + 0x1034 saw blade crossbar'
def components():
    fork=rot(stock(PITCHFORK),45)
    shaft=trim(fork.crop((3,15,8,61)))
    tooth=trim(fork.crop((4,0,6,8))).transpose(Image.Transpose.FLIP_TOP_BOTTOM)
    saw=rot(stock(SAW),-45)
    rail=trim(saw.crop((0,1,18,4)))
    return shaft,tooth,rail
@lru_cache(None)
def render(frame):
    if frame>=32:return render(frame-32).transpose(Image.Transpose.TRANSPOSE)
    shaft,tooth,rail=components()
    head=Image.new('RGBA',(20,5))
    for x in range(1,20,2):head.alpha_composite(size(tooth,1,3),(x,2))
    head.alpha_composite(size(rail,20,2),(0,0))
    if frame in (0,1):
        out=Image.new('RGBA',(34,26))
        handle=rot(size(shaft,3,34),-46)
        out.alpha_composite(handle,(9,0))
        out.alpha_composite(head,(0,21))
        return out if frame==0 else out.transpose(Image.Transpose.ROTATE_270)
    out=Image.new('RGBA',(20,17))
    out.alpha_composite(size(shaft,3,14),(9,0));out.alpha_composite(head,(0,12))
    if frame==2:return size(out.transpose(Image.Transpose.ROTATE_180),20,18)
    if frame==3:return size(out.transpose(Image.Transpose.ROTATE_90),19,20)
    if frame==4:return out
    raise ValueError(frame)
def describe(frame):
    return RECIPE+f' · facing 620/{frame}', 'Rake with a ten-tooth crossbar'

