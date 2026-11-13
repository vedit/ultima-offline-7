"""Publish the 18 review pairs from the same generated catalog that feeds the town atlas."""
import base64,io
from html import escape
from PIL import Image,ImageDraw,ImageFont
from town_review import GROUPS,KEPT,trim

FILES=('revised-matches.html','revised-lights.png','revised-dishes.png','revised-items.png')
def font(name,size):return ImageFont.truetype('C:/Windows/Fonts/'+name+'.ttf',size)
def data_uri(im):
    data=io.BytesIO();im.save(data,'PNG')
    return 'data:image/png;base64,'+base64.b64encode(data.getvalue()).decode('ascii')
def build(out,rows):
    lookup={(r['shape'],r['frame']):r for r in rows}
    assert sum(map(len,GROUPS.values()))==18
    html=['''<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Trinsic · Revised stock matches</title><style>
*{box-sizing:border-box}body{margin:0;background:#192427;color:#f1f2df;font:16px/1.45 "Segoe UI",sans-serif}main{max-width:1230px;margin:auto;padding:25px clamp(14px,4vw,50px)}h1,h2,h3{font-family:Georgia,serif;font-weight:400;line-height:1.15}h1{font-size:clamp(32px,4vw,52px);margin:20px 0 8px}h2{font-size:30px;margin:28px 0 12px}h3{font-size:22px;margin:0}section{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(330px,100%),1fr));gap:12px}article{background:#29363a;padding:14px;border-radius:6px}small,figcaption{color:#c7d9d0}a{color:#ade0cf}figure{margin:0;min-width:0;flex:1}figure div{display:grid;place-items:center;height:118px;background:#405055}img{image-rendering:pixelated;max-width:100%;height:auto}aside{display:flex;gap:5px;margin:12px 0}figcaption{margin:5px 0;font-size:13px;overflow-wrap:anywhere}article p{margin:9px 0 0}nav{display:flex;gap:18px;flex-wrap:wrap}</style><main><a href="index.html">← Town atlas</a><h1>Revised stock matches</h1><p>18 town-referenced frames. Each pair uses the same pixel scale. All 18 matches are approved, including the six broken dishes made from the stock empty plate.</p><nav><a href="#lights">Lights</a><a href="#broken-dishes">Broken dishes</a><a href="#other-items">Other items</a></nav>''']
    for (group,keys),filename in zip(GROUPS.items(),FILES[1:]):
        html.append(f'<h2 id="{group.lower().replace(" ","-")}">{escape(group)}</h2><p><a href="{filename}">Open comparison sheet</a></p><section>')
        sheet=Image.new('RGB',(888,650),'#192427');pen=ImageDraw.Draw(sheet)
        pen.text((16,4),group,font=font('georgia',30),fill='#f6f2dc')
        pen.text((16,46),'U7 original on the left   /   Revised UO match on the right   /   Same pixel scale within each pair',font=font('segoeui',15),fill='#baccc7')
        for n,key in enumerate(keys):
            r=lookup[key];s,f=key
            assert r['evidence']=='Town records'
            kept=key in KEPT
            state='Approved'
            label=r['uo_name'] if kept or s!=546 else r['uo_name'].split(' plate')[0]+' shards'
            short=r['uo_id'].replace('static ','').split(' · ')[0]
            name=r['name'][:1].upper()+r['name'][1:]
            x=16+n%2*432;y=81+n//2*185
            pen.rounded_rectangle((x,y,x+421,y+175),radius=5,fill='#29363a')
            pen.text((x+10,y+4),name+'   '+str(s)+'/'+str(f),font=font('segoeuib',17),fill='#ecf1e7')
            pen.text((x+405,y+6),state,anchor='ra',font=font('segoeui',14),fill='#b3d9be')
            html.append(f'<article id="pair-{s}-{f}"><small>{state} · U7 {s}/{f}</small><h3>{escape(name)}</h3><aside>')
            imgs=[]
            for field in ('source_image','target_image'):
                with Image.open(out/'images'/(r[field]+'.png')) as image:imgs.append(trim(image.convert('RGBA')))
            scale=min(7,165/max(im.width for im in imgs),92/max(im.height for im in imgs))
            for j,im in enumerate(imgs):
                w,h=round(im.width*scale),round(im.height*scale)
                caption='U7 original' if not j else label
                html.append(f'<figure><div><img alt="{escape(caption)}" width="{w}" src="{data_uri(im)}"></div><figcaption>{escape(caption)}'+(f' · {escape(short)}' if j else f' · {s}/{f}')+'</figcaption></figure>')
                l=x+10+j*204;t=y+33;pen.rectangle((l,t,l+196,t+100),fill='#405055')
                im=im.resize((w,h),Image.Resampling.NEAREST);sheet.paste(im,(l+(196-w)//2,t+(100-h)//2),im)
                pen.text((l,y+136),caption,font=font('segoeui',14),fill='#dfeddf')
                if j:pen.text((l,y+154),short,font=font('consola',12),fill='#bfccc6')
            html.append(f'</aside><p>{escape(r["note"])}</p><small><a href="index.html#{s}/{f}">Town record {s}/{f}</a></small></article>')
        sheet.save(out/filename);html.append('</section>')
    (out/FILES[0]).write_text(''.join(html)+'</main></html>','utf8')

