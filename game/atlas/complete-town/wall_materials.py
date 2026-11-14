"""House-wall matches reviewed against the Black Gate VGA frames.

Frame 32 is a reflection of frame 0. The projected footprint gives the axis;
the frame supplies the material. Doors, secret walls and fortress art have
separate recipes.
"""
STONE = (0x1d, 0x1c, 0x1b)
WOOD = (0x09, 0x07, 0x08)
PLASTER = (0x12a, 0x133, 0x134)

# Each column is a distinct sprite family, including the short runs under
# windows. Keep unreviewed variants on their existing atlas recipe.
FAMILIES = {
    STONE: {s: range(3) for s in (253, 273, 308, 344, 346, 348, 359, 362, 366, 899, 904, 909, 910)},
    WOOD: {345:(0,), 349:(0,), 355:(0,), 358:(0,1), 366:(3,), 371:(0,),
           374:(0,1), 497:(9,), 879:(16,), 899:(3,4), 904:(3,4), 909:(3,), 910:(3,)},
    PLASTER: {345:(1,), 349:(1,2,3), 355:(1,2,3), 366:(4,), 371:(1,), 909:(4,), 910:(4,)},
}
FAMILIES[STONE].update({425:range(5), 879:(0,1,2,3,4,8,9,10,11,12,13)})


def house_wall_art(shape, frame, width, depth):
    for family, shapes in FAMILIES.items():
        if (frame & 31) in shapes.get(shape, ()):
            return family[0 if width==depth==1 else 1 if width>depth else 2]
    return None
