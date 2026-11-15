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
CROP = (216, 284, 868, 1165)
MOUTH = (330, 805, 826, 1146)
EYES = ((420, 650, 615, 750), (680, 568, 800, 683))
SIZE = (104, 140)
MOUTHS = ['guardian-bare-master', 'mouth-cut-small', 'mouth-cut-medium', 'mouth-cut-wide', 'mouth-cut-oval']
EYELIDS = ['guardian-bare-master', 'eyes-half', 'eyes-closed']

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
    sources = {name: Image.open(ART / (name+'.png')).convert('RGBA') for name in set(MOUTHS+EYELIDS)}
    if any(im.size != (1043,1508) for im in sources.values()):
        raise ValueError('Relief sources must retain their registered source canvas')
    for im in sources.values():
        # Remove low-opacity export noise; keep authored edges and real apertures.
        im.putalpha(im.getchannel('A').point(lambda a: 0 if a < 16 else a))
    atlas = Image.new('RGBA', (SIZE[0]*5, SIZE[1]*3))
    transparent_counts = []
    for eye in range(3):
        for mouth in range(5):
            image = sources['guardian-bare-master'].copy()
            if mouth:
                image.paste(sources[MOUTHS[mouth]].crop(MOUTH), MOUTH)
            if eye:
                for box in EYES:
                    image.paste(sources[EYELIDS[eye]].crop(box), box)
            image = image.crop(CROP).resize(SIZE, Image.Resampling.NEAREST)
            atlas.paste(image, (mouth*SIZE[0],eye*SIZE[1]))
            # These pixels lie inside the mouth area, not the outer transparent border.
            if eye == 0:
                region = image.crop((23,86,95,126)).getchannel('A')
                transparent_counts.append(sum(a == 0 for a in region.getdata()))
    assert transparent_counts[2] > transparent_counts[0]
    assert transparent_counts[3] > transparent_counts[2]
    atlas.save(out/'guardian.png')
    atlas.resize((atlas.width*3,atlas.height*3),Image.Resampling.NEAREST).save(out/'guardian-review.png')

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
    receipt=dict(source='Local original U7 speech/cues; custom relief with transparent mouth apertures',
                 crop=CROP,mouth=MOUTH,eyes=EYES,size=SIZE,transparentMouthPixels=transparent_counts,
                 originalCues=len(cues),seconds=len(samples)/rate,
                 authored={n:hashlib.sha256((ART/(n+'.png')).read_bytes()).hexdigest() for n in sources},
                 original={n:hashlib.sha256((static/n).read_bytes()).hexdigest() for n in ('INTROSND.DAT','MAINSHP.FLX')})
    (out/'manifest.json').write_text(json.dumps(receipt,indent=2)+'\n',encoding='utf8')
    print(json.dumps(receipt,indent=2))
    return receipt

if __name__=='__main__':
    p=argparse.ArgumentParser()
    p.add_argument('--static',type=Path,default=Path('E:/UltimaOffline/Assets/UltimaVII-Steam/STATIC'))
    p.add_argument('--out',type=Path,default=HERE/'bin/assets')
    a=p.parse_args();prepare(a.static,a.out)
