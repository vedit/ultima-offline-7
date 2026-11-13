"""Black Gate actor-to-corpse pairs from bg/bodies.txt and the Trinsic scene."""
from functools import lru_cache

from PIL import Image, ImageChops, ImageDraw, ImageOps

from costumes import frame, ramp
from targets import body, uo

# Source actor shape -> (winged, ordinary dead shape/frame).
BODIES = {
    226: (True, (892, 29)),
    274: (True, (414, 2)),
    473: (True, (414, 1)),
    475: (False, (892, 4)),
    480: (True, (414, 14)),
    805: (False, (892, 4)),
    883: (False, (762, 1)),
}
WINGED_DEAD = {key for winged, key in BODIES.values() if winged}
WINGLESS_DEAD = {key for winged, key in BODIES.values() if not winged}
# 414/3 has the same SHAPES.VGA pixels as both wingless corpse keys.
WINGLESS_DEAD.add((414, 3))
SKIN = 0x27
NEAREST = Image.Resampling.NEAREST


def trim(image):
    return image.crop(image.getbbox())


def red(image):
    colors = ramp(SKIN)
    result = image.copy()
    result.putdata([(*colors[min(31, max(r, g, b) * 5 // 32)], alpha)
                    for r, g, b, alpha in image.getdata()])
    return result


@lru_cache(None)
def face():
    # Crop the horned face from the front-facing gargoyle, excluding its wings.
    head = body(4, 1, 0, 0, False).crop((42, 30, 55, 48))
    mask = Image.new('L', head.size)
    ImageDraw.Draw(mask).polygon([(2, 5), (5, 4), (10, 1), (9, 7), (11, 9),
                                  (10, 13), (8, 17), (4, 16), (1, 13), (0, 9)], fill=255)
    head.putalpha(ImageChops.multiply(mask, head.getchannel('A')))
    return red(head).resize((10, 12), NEAREST)


def living(shape, moving=False):
    if BODIES[shape][0]:
        action = 19 if shape == 226 else (0 if moving else 1)
        return trim(red(body(4, action, 1, 2 if moving else 0, False)))
    actor = trim(red(frame(400, 0 if moving else 4, 0, 2 if moving else 0, 0)[0]))
    head_box = actor.crop((0, 0, actor.width, 4)).getbbox()
    out = Image.new('RGBA', (actor.width, actor.height + 2))
    out.alpha_composite(actor, (0, 2))
    out.alpha_composite(face(), ((head_box[0] + head_box[2]) // 2 - 5, 0))
    return trim(out)


@lru_cache(None)
def prone():
    # Human death action 22 ends face-down, head left and both legs extended.
    actor = trim(red(frame(400, 22, 2, -1, 0)[0]))
    head = face().rotate(85, NEAREST, expand=True)
    actor.alpha_composite(head, (0, 6))
    return trim(actor)


def ordinary_dead(shape, source_frame):
    key = (shape, source_frame & 31)
    if key in WINGED_DEAD:
        action = 2 if key in ((414, 1), (892, 29)) else 3
        image = trim(red(body(4, action, 3, -1, False)))
    elif key in WINGLESS_DEAD:
        image = prone()
    else:
        raise ValueError(key)
    return ImageOps.mirror(image) if source_frame >= 32 else image


@lru_cache(None)
def inamo(source_frame):
    if source_frame not in (26, 58):
        raise ValueError(source_frame)
    out = Image.new('RGBA', (70, 96))
    pool = trim(uo(0x122A)).resize((46, 19), NEAREST)
    pool.putdata([(r * 3 // 4, g // 2, b // 3, a) for r, g, b, a in pool.getdata()])
    out.alpha_composite(pool, (12, 71))
    # Rotate the intact actor independently so the feet hang above level blood.
    actor = trim(prone().rotate(-78, NEAREST, expand=True))
    out.alpha_composite(actor, (20, 8))
    # Stock tines point into the upper torso. Leave the projecting handle
    # full length so its outline stays visible against the planks.
    fork = trim(uo(0x0E87))
    out.alpha_composite(fork, (0, 27))
    sprite = trim(out)
    return ImageOps.mirror(sprite) if source_frame == 58 else sprite


def recipe(shape, source_frame):
    key = (shape, source_frame & 31)
    suffix = ' · mirrored' if source_frame >= 32 else ''
    skin = 'hue 0x0027'
    if key == (414, 26):
        return ('scene floor blood 0x122A · body 0x0190 action 22, dir 2, final frame · '
                f'gargoyle face 0x0004 · {skin} · pitchfork 0x0E87' + suffix,
                'Inamo · wingless gargoyle pinned to the wall with a pitchfork')
    if key in WINGLESS_DEAD:
        return ('scene wingless corpse · body 0x0190 action 22, dir 2, final frame · '
                f'gargoyle face 0x0004 · {skin}' + suffix, 'Wingless gargoyle remains')
    if key in WINGED_DEAD:
        action = 2 if key in ((414, 1), (892, 29)) else 3
        return (f'scene winged corpse · body 0x0004 action {action}, dir 3, final frame · '
                + skin + suffix, 'Winged gargoyle remains')
    raise ValueError(key)
