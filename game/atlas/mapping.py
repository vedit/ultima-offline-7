# Each assignment is a visual judgement for one U7 shape/frame.
from source import *
CATEGORY = {}
RULES = {}
def add(category,shape,frames,targets,grade,note):
    for f,ids in zip(frames,targets,strict=True):
        RULES[shape,f]=(category,tuple(ids) if isinstance(ids,tuple) else (ids,) if ids is not None else (),grade,note)
def decor(s,frames,targets,grade,note): add('Decorations',s,frames,targets,grade,note)
stock='Stock candidate'
custom='Custom art'
for s,other in [(270,376),(376,270)]:
    for family in (0,8,16):
        base={0:0x6d5,8:0x6a5,16:0x675}[family]
        for state in (0,1):
            f=family+state
            axis=0 if s==270 else 8
            art=base+axis if not state else base+(8-axis)+1
            note='The U7 leaf spans four native tiles. The UO leaf is a one-tile reference. Draw a full-width leaf on the host anchor. '
            note+=['Iron straps cross the planks.','Preserve the small upper grille.','Preserve the gold crossbars on the dark panel.'][family//8]
            add('Doors',s,[f],[art],custom,note)
add('Doors',270,[2],[0x6d5],custom,'Locked version of the strapped leaf. Retain the four-tile span and let native state control the lock.')
add('Doors',271,[0],[0x6f6],custom,'The stock grille has the right material and facing. Extend the grille across the native four-tile opening and retain its vertical travel.')
add('Doors',257,[1],[None],custom,'Masonry gateway surround. Build the arch to fit the native opening independently of the movable grille.')
for f,arts,note in [
 (0,(0xccd,0xccf),'Bright orange oval crown. Use autumn leaves over a trunk. Stock foliage is darker and less uniform.'),
 (1,(0xcd3,0xcd5),'Broad ochre crown. This second autumn combination keeps the first two variants distinguishable.'),
 (2,(0x1b7e,),'Narrow dark evergreen. The single stock tree keeps the pointed silhouette.'),
 (3,(0xcfb,0xcfc),'Second evergreen. Stock cypress has a wider, tiered crown and more visible branches.'),
 (4,(0xd94,0xd96),'Red fruit reads clearly. Use the fruit-bearing apple canopy on its trunk.'),
 (5,(0xd9c,0xd9e),'Stock peach foliage suggests fruit, but the source has a broad low canopy and unusually prominent roots. Preserve that outline in custom art.')]:
    add('Trees',453,[f],[arts],custom if f==5 else stock,note)
decor(268,[0],[0x4045],stock,'An oval framed mirror. The stock frame is more ornate. Check the wall mount in scene.')
decor(848,[0],[0x4044],stock,'Opposite wall-facing oval mirror. The stock glass and frame are darker.')
decor(282,[0,1,3],[0xec9,0xea5,0xea5],custom,'Retain the painting subject, frame outline and wall-facing version. Stock art supplies scale and framing only.')
decor(821,[1],[0xe9f],custom,'Repaint the portrait in its narrow gold frame and keep its wall orientation.')
for s in (293,849):
    decor(s,[0,1,2],[0xeaa if s==293 else 0xeab]*3,custom,'Retain the gold motif and the blue, red and purple variants. Stock tapestry supplies a hanging reference.')
for s,fs in [(657,[0,2,6]),(678,[6,10])]:
    decor(s,fs,[0x435 if s==657 else 0x432]*len(fs),custom,'Use the stock tieback as a shape guide. Recreate the patterned fabric and matching wall-facing variants.')
for s,art in [(290,0x24f4),(291,0x24f4),(322,0x24f5),(372,0x24f5)]:
    decor(s,[0,1],[art,art],custom,'U7 has separate shutter leaves. UO includes the surrounding wall and window. Draw the shutters alone for each facing and state.')
decor(361,[7,9],[0xb9b,0xb9c],custom,'The projecting iron sign has a distinctive cutout. A metal bracket alone loses the sign silhouette.')
decor(379,[0,1,2,3,8,9],[0xbd0]*4+[0xbcf]*2,custom,'Use a narrow wood plaque with the source markings. Preserve frame and sign text separately.')
decor(314,[1,3,5],[0xcb0,0xcc7,0xcb0],stock,'Small ground weed. Stock shapes vary in spread and can share the host ground anchor.')
decor(331,[4,8],[0x1773,0x1771],stock,'Small grey ground stone. Compare the footprint in scene before accepting the stock size.')
decor(435,[0,1],[0xa07]*2,stock,'Lit wall torch. The two source flame phases can use stock torch animation.')
decor(535,[0],[0xa05],stock,'Spent wall torch. Preserve the bracket and unlit wooden handle.')
decor(336,[4],[0xb1d],custom,'Distinctive multi-arm fixture. The upright stock candelabrum has a different mounting and silhouette.')
decor(336,[6,11,12,13],[0xa26,0xa26,0xa26,0xa26],custom,'Keep the unlit wick and each holder profile. Stock candle is only a material reference.')
decor(338,[6,9,15],[0xa0f]*3,stock,'Lit candle and holder. The stock flame and wax are usable substitutes with differing holder detail.')
decor(188,[0,1],[0x11e6,0xab3],custom,'The source has a woven fill and a separate gold-bordered variant. Create matching floor tiles at the native footprint.')
decor(483,[0],[0xab3],custom,'Deep blue rug with a narrow gold border. Stock rug lacks that color and edge treatment.')
decor(470,[0],[0xaa25],custom,'Source is an uncovered circular stone well. The damaged roofed UO well serves only as a masonry reference.')
decor(740,[0],[None],custom,'Separate timber well apparatus. Keep its native anchor relative to the stone opening.')
decor(718,[0],[0x1223],custom,'Low square stepped plinth. Stock pedestal is tall and narrows in the middle.')
decor(724,[0],[None],custom,'Recreate the Fellowship emblem and mount. It identifies the organization in the scene.')
decor(823,[1,2],[0xfc1,0x42c6],stock,'Artist tools. The stock paint set groups the palette and brush. Keep native instances distinct.')
decor(837,[0,2,15],[0xf66]*3,stock,'An easel with a blank canvas matches this frame.') 
for f in (2,15):
    decor(837,[f],[0xf66],custom,'The source canvas shows a painting. Keep the stock easel geometry and replace the canvas face.')
decor(854,[4],[0x139c],custom,'The source figure raises a sword above a square base. The stock human statue has an extended arm and a different plinth.')
decor(889,[0],[0xb21],stock,'Unlit street lamp. Stock post is slimmer with a different lantern housing.')
decor(994,[0],[0xfbb],stock,'Small smithy tongs. Bind to the source item at its native lift so the same instance can be picked up.')
decor(998,[0,1,2,3,4],[0xfb6]*5,custom,'The source depicts individual smithing stages. The stock graphic groups three shoes and loses the stage distinction.')
decor(999,[0,1,2,3],[0x11cc,0x11ca,0x11cb,0x11c8],stock,'Small potted plant. Match the foliage or bloom color and place the base on its original surface.')
decor(1023,[4,5],[0xf36]*2,custom,'The stock sheaf supplies straw color. Draw the distinct stack profiles for the two native placements.')


