"""Render the source-linked gargoyle body study alongside the town atlas."""
from PIL import Image, ImageDraw

from gargoyles import BODIES, inamo, living, ordinary_dead, recipe
from revised_gallery import font
from stock_study import card
from town import names, src

FILES = ('gargoyles.html', 'inamo.png', 'gargoyle-pairs.png')


def body_pairs(out):
    sheet = Image.new('RGB', (720, 540), '#192427')
    pen = ImageDraw.Draw(sheet)
    for center, label in ((180, 'Living'), (540, 'Dead')):
        pen.text((center, 12), label, font=font('georgia', 25), fill='#f1f2df', anchor='mt')

    for top, height, shape, label in ((52, 284, 274, 'Winged gargoyle warrior'),
                                      (348, 176, 883, 'Wingless gargoyle')):
        dead = BODIES[shape][1]
        pen.rectangle((12, top, 707, top + height), fill='#354448')
        pen.text((26, top + 8), label, font=font('segoeui', 17), fill='#e4ece5')
        baseline = top + height - 12
        for center, sprite in ((180, living(shape)), (540, ordinary_dead(*dead))):
            sprite = sprite.resize((sprite.width * 2, sprite.height * 2), Image.Resampling.NEAREST)
            sheet.paste(sprite, (center - sprite.width // 2, baseline - sprite.height), sprite)
    sheet.save(out/'gargoyle-pairs.png')


def build(out):
    body_pairs(out)
    sheet = Image.new('RGB', (774, 256), '#192427')
    pen = ImageDraw.Draw(sheet)
    pen.text((18, 8), 'Inamo at the Trinsic stables', font=font('georgia', 30), fill='#f1f2df')
    samples = [(src(414, 26)[0], 'Original  ·  414/26'),
               (living(883), 'Living wingless body'),
               (inamo(26), 'Inamo  ·  wall pose')]
    for idx, (sprite, label) in enumerate(samples):
        x = 17 + idx * 251
        pen.rectangle((x, 61, x+237, 203), fill='#405055')
        sprite = sprite.crop(sprite.getbbox())
        scale = min(6, 222 // sprite.width, 135 // sprite.height)
        sprite = sprite.resize((sprite.width * scale, sprite.height * scale), Image.Resampling.NEAREST)
        sheet.paste(sprite, (x + (238-sprite.width)//2, 61 + (143-sprite.height)//2), sprite)
        pen.text((x, 213), label, font=font('segoeui', 16), fill='#e4ece5')
    sheet.save(out/'inamo.png')

    page = ['''<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Trinsic · Gargoyle bodies</title><style>
*{box-sizing:border-box}body{max-width:1200px;margin:auto;padding:24px;background:#192427;color:#edf1e8;font:16px/1.5 "Segoe UI",sans-serif}
h1,h2,h3{font-family:Georgia,serif;font-weight:400}a{color:#ade0cf}section{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(355px,100%),1fr));gap:12px}
article{background:#29363a;padding:14px}aside{display:flex;gap:5px}figure{margin:0;flex:1;min-width:0}figure div{height:112px;display:grid;place-items:center;background:#405055}
img{max-width:100%;height:auto;image-rendering:pixelated}figcaption{font-size:13px}p{max-width:85ch}</style>
<main><a href="index.html">← Town atlas</a><h1>Gargoyle bodies</h1><img src="inamo.png" alt="Original wall pose, living red wingless gargoyle, and the wall-pinned body above a pool of blood">
<p>Inamo occupies shape 414, frame 26 at (1066, 2182, 0). The pitchfork, body and blood share the original selectable object. Frame 58 mirrors the wall pose.</p>
<h2 id="body-pairs">Living and ordinary dead forms</h2><img src="gargoyle-pairs.png" alt="Winged gargoyle warrior and wingless gargoyle, each standing beside its ordinary corpse at the same scale."><p>Each original actor shape is paired with its corpse frame from the Black Gate body table. The UO columns show representative living poses and the ordinary corpse.</p><section>''']
    for shape, (winged, dead) in BODIES.items():
        label = names[shape]
        page.append(card(label, [(src(shape, 16)[0], f'U7 actor {shape}/16'),
                                 (src(*dead)[0], f'U7 corpse {dead[0]}/{dead[1]}'),
                                 (living(shape), 'UO flight' if shape == 226 else 'UO standing'),
                                 (ordinary_dead(*dead), 'UO corpse'),
                                 (living(shape, True), 'UO in motion')],
                         ('Winged' if winged else 'Wingless') + ' · ' + recipe(*dead)[0]))
    (out/'gargoyles.html').write_text(''.join(page) + '</section></main></html>', encoding='utf8')
