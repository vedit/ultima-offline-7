"""Build the dream's private runtime assets from local retail data and authored art."""
import argparse
import hashlib
import json
import struct
import wave
from pathlib import Path
from PIL import Image, ImageDraw

HERE = Path(__file__).resolve().parent
ART = HERE / 'art'
CROP = (60, 40, 1010, 1390)
SIZE = (104, 148)
CLAY = ART / 'painted-clay'
# The accepted interim set has four whole-head poses. Rounded cues reuse medium;
# eyelid rows repeat the same pose rather than reintroducing rejected artwork.
MOUTHS = ['master', 'u7-frame-06', 'u7-frame-05', 'u7-frame-03', 'u7-frame-05']
BLUE_SIZE = (320, 200)
BLUE_COLUMNS = 13
BLUE_FRAMES = 78

def blue_wall(static, out):
    # Original monitor bitmap: ENDSHAPE 19, single RLE frame with a flagged offset.
    # Reuse the project's decoder after stripping the offset's high-byte flags.
    import sys
    sys.path.insert(0, str(HERE.parent / 'atlas'))
    from frames import rle
    raw = bytearray(member((static/'ENDSHAPE.FLX').read_bytes(), 19))
    offset = struct.unpack_from('<I', raw, 4)[0] & 0xFFFFFF
    if offset != 8: raise ValueError('Expected one monitor frame')
    struct.pack_into('<I', raw, 4, offset)
    w,h,pixels,_,origin = rle(raw,0)
    if (w,h,origin)!=(320,200,(0,0)) or any(v is None for v in pixels):
        raise ValueError('Invalid original monitor pattern')
    palette = member((static/'INTROPAL.DAT').read_bytes(), 2)
    if len(palette)==1536: palette=palette[::2]
    if len(palette)!=768 or max(palette)>63: raise ValueError('Invalid monitor palette')
    colors=[tuple(v*255//63 for v in palette[i:i+3])+(255,) for i in range(0,768,3)]
    width,height=BLUE_SIZE
    # Full original bitmap. The client fills its world viewport with this layer;
    # transparent mouth apertures reveal it at the same coordinates and phase.
    atlas=Image.new('RGBA',(width*BLUE_COLUMNS,height*6))
    for phase in range(BLUE_FRAMES):
        frame=Image.new('RGBA',BLUE_SIZE)
        # Original speech loop: palette.rotate(93,16,1), inclusive range.
        frame.putdata([colors[16+(i-16-phase)%78 if 16<=i<=93 else i] for i in pixels])
        atlas.paste(frame,((phase%BLUE_COLUMNS)*width,(phase//BLUE_COLUMNS)*height))
    atlas.save(out/'blue-static.png')
    return dict(shape=19,palette=2,cycle=[93,16],frames=78,fps=20,
                sourceSize=[320,200],frameSize=BLUE_SIZE,columns=BLUE_COLUMNS,
                placement='World viewport backdrop',source='Original U7 monitor bitmap and palette',
                original={n:hashlib.sha256((static/n).read_bytes()).hexdigest() for n in ('ENDSHAPE.FLX','INTROPAL.DAT')})

def member(data, index):
    if len(data) < 128 or index >= struct.unpack_from('<I', data, 84)[0]:
        raise ValueError('Invalid Flex member')
    start, length = struct.unpack_from('<II', data, 128 + 8*index)
    if start < 128 or start + length > len(data):
        raise ValueError('Invalid Flex range')
    return data[start:start+length]

def read_voc(data):
    if not data.startswith(b'Creative Voice File\x1a'):
        raise ValueError('Expected original Creative Voice file')
    pos = struct.unpack_from('<H', data, 20)[0]
    if data[pos] != 1:
        raise ValueError('Unsupported intro voice block')
    length = int.from_bytes(data[pos+1:pos+4], 'little')
    if length < 2 or pos + 4 + length > len(data) or data[pos+5] != 0:
        raise ValueError('Invalid 8-bit PCM intro voice')
    rate = round(1_000_000/(256-data[pos+4]))
    samples = data[pos+6:pos+4+length]
    if not 8000 <= rate <= 48000 or not samples:
        raise ValueError('Invalid intro voice rate')
    return rate, samples

def prepare(static, out):
    out.mkdir(parents=True, exist_ok=True)
    sources = {name: Image.open(CLAY / (name+'.png')).convert('RGBA') for name in set(MOUTHS)}
    if any(im.size != (1122,1402) for im in sources.values()):
        raise ValueError('Painted clay sources must retain their source canvas')
    for im in sources.values():
        im.putalpha(im.getchannel('A').point(lambda a: 0 if a < 16 else a))
    atlas = Image.new('RGBA', (SIZE[0]*5, SIZE[1]*3))
    transparent_counts = []
    for eye in range(3):
        for mouth in range(5):
            image = sources[MOUTHS[mouth]].crop(CROP).resize(SIZE, Image.Resampling.NEAREST)
            atlas.paste(image, (mouth*SIZE[0],eye*SIZE[1]))
            if eye == 0:
                region = image.crop((30,90,90,120)).getchannel('A')
                transparent_counts.append(sum(a == 0 for a in region.getdata()))
    assert transparent_counts[3] > transparent_counts[2] > transparent_counts[1] > transparent_counts[0]
    atlas.save(out/'guardian.png')
    atlas.resize((atlas.width*3,atlas.height*3),Image.Resampling.NEAREST).save(out/'guardian-review.png')
    blue = blue_wall(static,out)

    mains = (static/'MAINSHP.FLX').read_bytes()
    cue_bytes = member(mains,15)
    if len(cue_bytes)%3: raise ValueError('Invalid facial cue stream')
    cues = [list(c) for c in struct.iter_unpack('<HB',cue_bytes)]
    assert all(0 <= code <= 22 for _,code in cues)
    # Preserve file order, including the original late out-of-order cue.
    lines = [line.strip() for line in member(mains,13).decode('cp437').splitlines()]
    if len(lines)!=14: raise ValueError('Expected the 14 original Guardian speech lines')
    rate,samples = read_voc((static/'INTROSND.DAT').read_bytes())
    pcm = b''.join(struct.pack('<h',(sample-128)*256) for sample in samples)
    with wave.open(str(out/'guardian.wav'),'wb') as wav:
        wav.setnchannels(1);wav.setsampwidth(2);wav.setframerate(rate);wav.writeframes(pcm)
    payload = dict(version=1,width=SIZE[0],height=SIZE[1],duration=len(samples)/rate,
                   cues=cues,lines=lines,textTimes=[.25,1.7,5.25,8.2,10.55,12.9,16,19.95,22.7,27.2,32.4,36.4,39.65,42.4,44])
    (out/'intro.json').write_text(json.dumps(payload),encoding='utf8')
    receipt=dict(source='Local original U7 speech/cues/blue monitor; painted interim clay poses with transparent mouths',
                 crop=CROP,size=SIZE,transparentMouthPixels=transparent_counts,blue=blue,
                 mouthSources=MOUTHS,eyeStates='open only (interim)',
                 originalCues=len(cues),seconds=len(samples)/rate,
                 authored={n:hashlib.sha256((CLAY/(n+'.png')).read_bytes()).hexdigest() for n in sources},
                 original={n:hashlib.sha256((static/n).read_bytes()).hexdigest() for n in ('INTROSND.DAT','MAINSHP.FLX')})
    (out/'manifest.json').write_text(json.dumps(receipt,indent=2)+'\n',encoding='utf8')
    print(json.dumps(receipt,indent=2))
    return receipt

if __name__=='__main__':
    import sys
    sys.path.insert(0,str(HERE.parent))
    from install_paths import INSTALL, RUNTIME
    p=argparse.ArgumentParser()
    p.add_argument('--static',type=Path,default=INSTALL/'Assets/UltimaVII-Steam/STATIC')
    p.add_argument('--out',type=Path,default=RUNTIME/'intro-assets')
    a=p.parse_args();prepare(a.static,a.out)
