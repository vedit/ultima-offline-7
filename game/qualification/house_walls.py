"""Project timber and masonry house walls from native wall runs onto the compact grid."""
import re
from collections import defaultdict

# The stock faces terminate at a common vertex. Bits denote a west or north arm.
WALL_ART = {'wood': (9, 7, 8, 6), 'stone': (0x1d, 0x1c, 0x1b, 0x1a),
            'plaster': (0x12a, 0x133, 0x134, 0x132)}
WINDOW_ARM = {14: 1, 15: 2, 0x22: 1, 0x23: 2, 0x13a: 1, 0x13b: 2}

def wall_face(row):
    """Read the first stock piece from a static or assembled atlas recipe."""
    match = re.match(r'(?:static|assembly) 0x([0-9a-fA-F]+)\b', row['uo_id'])
    if not match:
        return None
    return int(match[1], 16)


def compact_house_walls(refs, rows):
    # Index the material and axis of every native run before any division by two.
    runs = defaultdict(dict)
    posts = {}
    sockets = set()
    cells = defaultdict(set)
    for r in refs:
        shape, frame = int(r['shape']), int(r['frame'])
        row = rows[shape, frame]
        x, y, lift = (int(r[k]) for k in ('x', 'y', 'lift'))
        w, d = map(int, row['footprint'].split('\u00d7'))
        if r['layer'] == 'World object' and row['method'] == 'Door leaf':
            # Native doors exchange footprint axes when they swing open. The
            # mounting opening stays in the wall even for an initially open door.
            if shape in (270,376) and frame % 4 == 1:
                closed_shape = 376 if shape == 270 else 270
                w, d = map(int, rows[closed_shape,frame-1]['footprint'].split('\u00d7'))
            arm = 1 if w > d else 2
            sockets.update((x-a, y-b, lift, arm) for a in range(w) for b in range(d))
            continue
        if r['layer'] not in ('Terrain', 'Fixed') or row['source_name'] != 'wall':
            continue
        post = w == d == 1
        graphic = wall_face(row)
        if post:
            if row['method'] == 'Source wall material':
                posts[x, y, lift] = next(m for m, art in WALL_ART.items() if art[0] == graphic)
            else:
                # Earlier atlases represented posts with full wall leaves.
                timber = shape == 497 or (shape == 879 and (frame & 31) in (5, 6, 7, 16))
                posts[x, y, lift] = 'wood' if timber else 'stone'
        else:
            arm = 1 if w > d else 2
            material = next(m for m, art in WALL_ART.items() if art[arm] == graphic)
        for a in range(w):
            for b in range(d):
                point = x-a, y-b, lift
                cells[(x-a)//2, (y-b)//2, lift].add(point)
                if not post:
                    runs[point][arm] = material

    result = {}
    for cell, points in cells.items():
        arms = {}
        for x, y, z in sorted(points):
            for arm, dx, dy in ((1, 1, 0), (2, 0, 1)):
                other = x-dx, y-dy, z
                if (other[0]//2, other[1]//2, z) == cell:
                    continue
                here = runs.get((x,y,z), {}).get(arm)
                there = runs.get(other, {}).get(arm)
                if not (here or (x,y,z) in posts):
                    continue
                if there or other in posts or (*other, arm) in sockets:
                    arms[arm] = here or there or posts[x,y,z]
        if not arms:
            # An outward turn or an end cap has no incoming face. Pick the
            # original post material, falling back to the run at an exposed end.
            material = next((posts[p] for p in sorted(points) if p in posts), None)
            if material is None:
                material = next(iter(runs[min(points)].values()))
            result[cell] = (WALL_ART[material][0],)
        elif len(arms) == 2 and arms[1] == arms[2]:
            result[cell] = (WALL_ART[arms[1]][3],)
        else:
            result[cell] = tuple(WALL_ART[material][arm] for arm,material in sorted(arms.items()))
    return result


def fit_house_window(graphics, window, replacement):
    """Replace just the matching face, preserving the other arm of a corner."""
    arm = WINDOW_ARM[window]
    result = []
    for graphic in graphics:
        if graphic in WINDOW_ARM:
            result.append(graphic)
            continue
        art = next(art for art in WALL_ART.values() if graphic in art)
        mask = art.index(graphic)
        if mask & arm:
            if mask != arm:
                result.append(art[mask ^ arm])
            if replacement:
                result.append(replacement)
        else:
            result.append(graphic)
    return result
