from pathlib import Path
from PIL import Image,ImageDraw,ImageFont
import csv
def render(out):
    with (out/'mapping.csv').open(encoding='utf-8-sig') as h:rows={(int(r['shape']),int(r['frame'])):r for r in csv.DictReader(h)}
    im=Image.new('RGB',(1040,620),'#182125');d=ImageDraw.Draw(im)
    font=lambda n,s:ImageFont.truetype('C:/Windows/Fonts/'+n+'.ttf',s)
    d.text((28,18),'Trinsic  /  Town-wide comparisons',font=font('georgia',34),fill='#f1efdf')
    d.text((30,68),'Original Forge sprites alongside stock UO references',font=font('segoeui',17),fill='#b5ccc4')
    for j,(name,k) in enumerate([('North and south gates',(272,0)),('Finnigan',(451,16)),('Dungeon wall',(828,0)),('Murder scene',(867,0)),('Orange dress',(249,1)),('Cloak',(285,0))]):
        r=rows[k];x=24+(j%3)*332;y=104+(j//3)*250
        d.rounded_rectangle((x,y,x+318,y+234),radius=6,fill='#263237')
        d.text((x+10,y+8),name,font=font('georgia',19),fill='#edf1e8')
        for n,field in enumerate(['source_image','target_image']):
            sprite=Image.open(out/'images'/(r[field]+'.png')).convert('RGBA');sprite=sprite.crop(sprite.getbbox());scale=min(130/sprite.width,110/sprite.height,5);sprite=sprite.resize((max(1,round(sprite.width*scale)),max(1,round(sprite.height*scale))),Image.Resampling.NEAREST)
            xx=x+10+150*n;d.rectangle((xx,y+40,xx+144,y+162),fill='#354247')
            im.paste(sprite,(xx+(145-sprite.width)//2,y+40+(123-sprite.height)//2),sprite)
            label='U7 '+str(k[0])+'/'+str(k[1]) if n==0 else 'UO '+r['uo_id'].split(' ·')[0].split('@')[0].replace('assembly ','').replace('static ','').replace('land ','').split(' hue')[0]
            d.text((xx,y+169),label,font=font('consola',14),fill='#c6d8ce')
        d.text((x+10,y+201),r['status'],font=font('segoeuib',15),fill='#efb88f' if r['status']=='Custom art' else '#a6d9b8')
    im.save(out/'preview.png')
    

if __name__=='__main__':render(Path(__file__).resolve().parent/'atlas')
