# Frame-specific exceptions uncovered while inspecting the complete town.
from targets import *
def treatment(s,f,image,recorded):
    if not image.getbbox():
        return 'Engine markers',('hidden',),'No visible art','Empty source frame','This SHAPES.VGA frame has no visible pixels.'
    key=f&31 if s not in bodyids and counts[s]<0 and f>=32 else f
    family,spec,grade,method,note=classify(s,key,image)
    if s in (620,474,756):
        grade='Custom art'
        note={620:'The stock pitchfork gives the handle scale. Draw the transverse head and row of rake teeth.',474:'This stock bow is a ranged-weapon reference. Draw the leather sling pouch and cords.',756:'Floor spikes give the metal finish. Draw portable caltrops at the source footprint.'}[s]
    if s==675:
        notes={0:'Draw a wooden gavel. Stock hammer supplies the striking-tool silhouette.',1:'Stock quill and ink set includes an extra inkwell.',2:'Separate the inkpot from the stock writing set.',6:'Use the parchment surface and retain the document mark.',9:'Draw a handled desk blotter.',10:'Draw the parrot figure itself. A stock perch supplies only its mounting reference.',11:'Stock abacus has the correct function. Check its table footprint.',13:'Use the parchment surface and retain the document mark.',16:'The mirror is handheld. Recreate its handle and small tabletop scale.'}
        if key in notes:note=notes[key];grade='Stock candidate' if key==11 else 'Custom art'
    if s==377:
        alts={2:0x9ea,3:0x9e9,5:0x1041,6:0x1041,10:0x9b7,12:0x9cc,13:0x9cc,15:0x9f1,22:0xc69,23:0x9f1,24:0x9b5,25:0x97c,26:0x97c,27:0x97e,28:0x97e,29:0x1602,30:0x97b,31:0x9d8}
        if key in alts:spec=('static',alts[key])
        if key in (3,6,15,22,25,28,29,30,31):grade='Custom art';note='Use the displayed food as a palette or serving reference. Preserve the named food, color and number of pieces.'
    if s==453 and key>=6:note='Alternate tree frame. Stock layers give scale. Preserve the source silhouette, trunk base and foliage.'
    if not recorded and method=='Stock family comparison' and abs(counts[s])>4 and s not in (377,388):
        grade='Custom art';note='This alternate frame shares a stock object-family reference. Reproduce its pose, contents or orientation before using it in play.'
    if s in (633,847,890,971,1000,1003,1018,713) and max(((tfa[3*s+2]&7)+1),(((tfa[3*s+2]>>3)&7)+1))>1:
        grade='Custom art';note='Build the full native span from stock components or draw a custom assembly. The comparison shows one component.'
    return family,spec,grade,method,note

