"""Check the emitted wall faces against source edges at every house and lift."""
import struct
from collections import Counter, defaultdict


def verify_house_walls(refs, rows, idx, statics, fittings):
    walls = set()
    axes = [set(), set()]
    materials = [defaultdict(set), defaultdict(set)]
    post_materials = defaultdict(set)
    for r in refs:
        shape, frame = int(r['shape']), int(r['frame'])
        row = rows[shape, frame]
        wall = r['layer'] in ('Fixed', 'Terrain') and row['source_name'] == 'wall'
        door = r['layer'] == 'World object' and row['method'] == 'Door leaf'
        if not (wall or door):
            continue
        if door and shape in (270,376) and frame % 4 == 1:
            closed_shape = 376 if shape == 270 else 270
            row = rows[closed_shape, frame-1]  # Both native shapes close at the same anchor.
        w,d = map(int, row['footprint'].split('\u00d7'))
        x,y,z = (int(r[k]) for k in ('x','y','lift'))
        points = {(x-a,y-b,z) for a in range(w) for b in range(d)}
        if wall:
            walls.update(points)
            assert row['method'] == 'Source wall material', ('unreviewed placed wall', shape, frame)
            material = 'wooden wall' if row['uo_name'] == 'wooden post' else row['uo_name']
            if w == d == 1:
                post_materials[x,y,z].add(material)
            else:
                for point in points:
                    materials[int(d>w)][point].add(material)
        if w >= d:
            axes[0].update(points)
        if d >= w:
            axes[1].update(points)

    # Walk the source in the positive directions: a segment crossing a compact
    # boundary belongs to the receiving vertex. In a doorway only the wall end
    # owns masonry; the door remains a live item in its own cell.
    expected = {(x//2,y//2,z): set() for x,y,z in walls}
    finishes = defaultdict(set)
    for axis, points in enumerate(axes):
        for p in points:
            x,y,z = p
            end = x+int(axis==0), y+int(axis==1), z
            if p[axis]%2 and end in walls and end in points:
                cell = end[0]//2,end[1]//2,z
                expected[cell].add(axis)
                finishes[cell,axis].update(materials[axis][end] or materials[axis][p] or post_materials[end])

    # Include each interactive shutter as the full-height window it draws.
    windows = defaultdict(list)
    for x,y,z,graphic in fittings:
        windows[x//2,y//2,z-2].append(graphic)
    directions = {6:(0,1), 26:(0,1), 7:(0,), 28:(0,), 8:(1,), 27:(1,),
                  14:(0,), 34:(0,), 15:(1,), 35:(1,), 9:(), 29:(),
                  0x132:(0,1), 0x133:(0,), 0x134:(1,), 0x13a:(0,), 0x13b:(1,), 0x12a:()}
    finish = {g: label for label, ids in (
        ('stone wall',(26,27,28,29,34,35)),
        ('wooden wall',(6,7,8,9,14,15)),
        ('plaster wall',(0x132,0x133,0x134,0x13a,0x13b,0x12a))) for g in ids}
    errors = []
    for (x,y,z), wanted in sorted(expected.items()):
        offset,size,_ = struct.unpack_from('<iii', idx, 12*((x//8)*512+y//8))
        sprites = list(windows[x,y,z])
        for g,dx,dy,h,_ in struct.iter_unpack('<HBBbH', statics[offset:offset+size]):
            if g in directions and (dx,dy,h)==(x%8,y%8,z*4):
                sprites.append(g)
        arms = Counter(axis for g in sprites for axis in directions[g])
        posts = sum(not directions[g] for g in sprites)
        if arms != Counter(wanted) or posts != int(not wanted):
            errors.append(((x,y,z), sorted(wanted), sprites))
        for g in sprites:
            for axis in directions[g]:
                allowed = finishes[(x,y,z),axis]
                assert finish[g] in allowed, ('wall material',(x,y,z),axis,hex(g),allowed)
    assert not errors, ('house wall geometry',len(errors),errors[:12])
    return len(expected)
