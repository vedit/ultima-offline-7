from PIL import Image,ImageDraw,ImageFont
from town import src
from town_review import trim,size
import rake
def build(out):
    a=Image.new('RGB',(850,418),'#192427');d=ImageDraw.Draw(a)
    def txt(pos,t,n,face='segoeui',color='#f1f2df'):
        d.text(pos,t,font=ImageFont.truetype('C:/Windows/Fonts/'+face+'.ttf',n),fill=color)
    txt((22,11),'Trinsic rake',32,'georgia');txt((23,57),'620/0  ·  Recorded town frame  ·  Approved stock assembly',17,color='#c4d8d0')
    for x,label,im in [(22,'U7 original',trim(src(620,0)[0])),(433,'UO stock assembly',rake.render(0))]:
        d.rectangle((x,94,x+393,280),fill='#405055');im=size(im,im.width*6,im.height*6)
        a.paste(im,(x+197-im.width//2,187-im.height//2),im);txt((x,288),label,18)
    txt((23,333),'0x0E87  Pitchfork shaft and prong',17,color='#bfd4ce')
    txt((23,363),'0x1034  Saw blade strip forms the crossbar. Ten copies of one prong form the teeth.',17,color='#bfd4ce')
    a.save(out/'rake.png')

