import csv,json,hashlib,io,math
from collections import Counter
from pathlib import Path
from PIL import ImageDraw,ImageFont
from variants import variants
from reuse import simplify,draw,describe,WARDROBES
from family_notes import *
OUT=BASE/'atlas';OUT.mkdir(exist_ok=True);IMG=OUT/'images';IMG.mkdir(exist_ok=True)
def csvfile(name,fields,rows):
    with (OUT/name).open('w',newline='',encoding='utf-8-sig') as h:
        w=csv.writer(h);w.writerow(fields);w.writerows(rows)
written=set()
def sprite(im):
    dat=io.BytesIO();im.save(dat,format='PNG');data=dat.getvalue();h=hashlib.sha256(data).hexdigest()[:24]
    if h not in written:(IMG/(h+'.png')).write_bytes(data);written.add(h)
    return h
@lru_cache(None)
def target_file(spec):
    im=draw(spec) if spec[0] in ("outfit","layout","wearable","scene","remains","revised","rake") else target(spec)
    if im is None:return '',0,0
    return sprite(im),im.width,im.height
def html_data(records,inputs):
    keys=variants(records);rows=[];placements=[];layers=Counter();audit=Counter()
    for (s,f),refs in records.items():
        for x,y,z,layer,name,off,owner in refs:
            placements.append([s,f,x,y,z,layer,name,off,owner]);layers[layer]+=1
    for s,f in sorted(keys):
        refs=records.get((s,f),[]);im,origin=src(s,f)
        initial=treatment(s,f,im,bool(refs))
        family,spec,grade,method,note=simplify(s,f,im,initial)
        if refs:ev='Town records'
        elif (s,f) in RULES and s in (270,376):ev='Door transition'
        else:ev='Other frame'
        audit[ev]+=1
        tgt,tw,th=target_file(spec)
        a,fp=tfa[3*s],tfa[3*s+2];dx,dy=(fp&7)+1,((fp>>3)&7)+1
        if counts[s]<0 and f>=32:dx,dy=dy,dx
        family_label=title(s,f)
        if not names[s] and s in LAND:family_label='Unnamed water tile'
        if s==453:family_label=['Orange broadleaf','Ochre broadleaf','Slender evergreen','Tiered evergreen','Red-fruited tree','Low fruit tree','Tree variant 6','Tree variant 7','Tree variant 8'][f&31]
        if s in (270,376):family_label='Door · '+['closed','open','locked','locked'][f%4]
        if s==377:family='Food'
        label = tile(spec[1])[0] if spec[0]=='static' and len(spec)==2 else ' + '.join(tile(i)[0] for i in spec[1:]) if spec[0]=='static' else landname(spec[1]) if spec[0]=='land' else ('Human' if spec[1]>=400 else {200:'Horse',201:'Cat',207:'Sheep',217:'Dog'}.get(spec[1],'Animal')) if spec[0]=='body' else 'Invisible'
        target_id=idtext(spec) if spec[0] not in ('outfit','layout','wearable','scene','remains','revised','rake') else describe(spec)[0]
        if spec[0] in ('outfit','layout','wearable','scene','remains','revised','rake'):label=describe(spec)[1]
        if spec[0]=='outfit':family_label=WARDROBES[s][0]
        if spec[0]=='remains':family_label=label.split(' · ')[0]
        if s==249:family_label=['Green top','Orange dress','Blue dress'][f&31]
        witness=refs[0] if refs else None
        row=dict(shape=s,frame=f,source_name=names[s],name=family_label,category=family,status=grade,evidence=ev,refs=len(refs),
            layers=' / '.join(sorted({r[3] for r in refs})),witness=', '.join(str(v) for v in witness[:3] if v is not None) if witness else '',owner=witness[6] if witness else '',
            previous_decision=initial[2],optional_detail=initial[4] if initial[2]=="Custom art" and grade!="Custom art" and s not in bodyids and spec[0] not in ('wearable','revised','rake') and method!='Approved stock match' else "",uo_id=target_id,uo_name=label,source_image=sprite(im),target_image=tgt,width=im.width,height=im.height,target_width=tw,target_height=th,
            origin_x=origin[0],origin_y=origin[1],footprint=f'{dx} × {dy}',native_height=a>>5,method=method,note=note,
            swing=f'{646-s}/{f^1}' if s in (270,376) and f%4<2 and (646-s,f^1) in keys else '')
        rows.append(row)
    csvfile('equipment.csv',['shape','frame','name','evidence','uo_id','uo_name'],([r[k] for k in ('shape','frame','name','evidence','uo_id','uo_name')] for r in rows if r['status']=='Stock equipment'));csvfile('mapping.csv',rows[0],(r.values() for r in rows));csvfile('custom-art.csv',rows[0],(r.values() for r in rows if r['status']=='Custom art'));csvfile('references.csv',['shape','frame','x','y','lift','layer','member_or_file','byte_offset','owner'],placements)
    data=json.dumps(rows,ensure_ascii=False,separators=(',',':'))
    (OUT/'catalog.js').write_text('const CATALOG='+data+';\n','utf8')
    counts_status=dict(Counter(r['status'] for r in rows if r['refs']))
    sources=[D/name for name in inputs]+[U/name for name in ('artLegacyMUL.uop','tiledata.mul','anim.idx','anim.mul','hues.mul','Equipconv.def')]+[EXULT]
    receipt=dict(edition='Steam FORGE initial state',bounds=dict(x_min=928,x_max=1119,y_min=2080,y_max=2351),cells=192*272,shape_count=len({s for s,f in records}),frame_keys=dict(audit),references=dict(layers),town_decisions=counts_status,total_rows=len(rows),unique_png=len(written),input_sha256={str(p):digest(p) for p in sources},output_sha256={n:digest(OUT/n) for n in ('mapping.csv','custom-art.csv','references.csv','catalog.js')})
    (OUT/'sources.json').write_text(json.dumps(receipt,indent=2)+'\n','utf8')
    return rows,receipt
def covermap():
    terr=TerrainSource((D/'U7MAP').read_bytes(),(D/'U7CHUNKS').read_bytes());l,t=896,2048;w,h=256,336
    m=Image.new('RGB',(w,h));pix=m.load()
    colors={}
    for y in range(h):
        for x in range(w):
            a=terr.tile(x+l,y+t);s=a['shape'];f=a['frame'];k=s,f
            if k not in colors:
                if counts[s]>0:
                    p,_=src(s,f);colors[k]=tuple(int(v) for v in ImageStat.Stat(p.convert('RGB')).mean)
                elif names[s] in architecture:colors[k]=(213,196,148)
                else:colors[k]=(70,85,51)
            pix[x,y]=colors[k]
    m=m.resize((w*2,h*2),Image.Resampling.NEAREST);draw=ImageDraw.Draw(m)
    for a,b,c,d,color in [(928,2080,1119,2351,'#fff0aa'),(944,2112,1111,2271,'#ed7884')]:draw.rectangle(((a-l)*2,(b-t)*2,(c-l)*2,(d-t)*2),outline=color,width=2)
    m.save(OUT/'extent.png')
if __name__=='__main__':
    records,inputs=census();rows,receipt=html_data(records,inputs);covermap()
    (OUT/'index.html').write_text((BASE/'viewer.html').read_text('utf-8-sig'),encoding='utf8')
    from stock_study import build
    from preview import render
    build(OUT)
    render(OUT)
    import revised_gallery
    revised_gallery.build(OUT,rows)
    from rake_card import build as build_rake_card
    build_rake_card(OUT)
    receipt['input_sha256'][str(EXULT.with_name('paperdol_info.txt'))]=digest(EXULT.with_name('paperdol_info.txt'))
    receipt['input_sha256'][str(EXULT.with_name('bodies.txt'))]=digest(EXULT.with_name('bodies.txt'))
    for name in (*revised_gallery.FILES,'rake.png','equipment.csv','stock-study.html','stock-sources.json','outfits.csv','preview.png','extent.png','index.html'):
        receipt['output_sha256'][name]=digest(OUT/name)
    (OUT/'sources.json').write_text(json.dumps(receipt,indent=2)+'\n','utf8')
    print({k:v for k,v in receipt.items() if 'sha256' not in k})

