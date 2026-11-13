from town import *
from variants import variants
from pathlib import Path
import csv,json
from PIL import Image
def verify(root):
    def table(file):
        with (root/file).open(encoding='utf-8-sig',newline='') as h:return list(csv.DictReader(h))
    rows=table('mapping.csv');refs=table('references.csv');evidence=json.loads((root/'sources.json').read_text())
    reco,inputs=census()
    csvkeys=[(int(r['shape']),int(r['frame'])) for r in rows]
    assert len(csvkeys)==len(set(csvkeys)) and set(csvkeys)==variants(reco)
    assert {k for k,r in zip(csvkeys,rows) if int(r['refs'])}==set(reco)
    pairs=Counter((int(r['shape']),int(r['frame'])) for r in refs)
    assert pairs==Counter({k:len(p) for k,p in reco.items()})
    observed={(int(r['shape']),int(r['frame']),int(r['x']),int(r['y']),str(r['lift']),r['layer'],r['member_or_file'],int(r['byte_offset']),r['owner']) for r in refs}
    oracle={(s,f,x,y,'' if z is None else str(z),layer,file,off,owner) for (s,f),group in reco.items() for x,y,z,layer,file,off,owner in group}
    assert observed==oracle and len(observed)==len(refs)
    ground={(int(r['x']),int(r['y'])) for r in refs if r['layer']=='Terrain'}
    assert ground=={(x,y) for x in range(928,1120) for y in range(2080,2352)}
    previous=table_external(ATLAS/'atlas'/'mapping.csv')
    assert {(int(r['shape']),int(r['frame'])) for r in previous}<=set(csvkeys)
    assert all((r['target_image']!='')==(r['status']!='No visible art') for r in rows)
    allpng={r[k] for r in rows for k in ['source_image','target_image'] if r[k]}
    for h in allpng:
        p=root/'images'/(h+'.png');assert digest(p).startswith(h)
        with Image.open(p) as im:im.verify()
    from equipment import ITEMS
    assert all(r['status']=='Stock equipment' for r in rows if int(r['shape']) in ITEMS and r['target_image'])
    assert len(table('equipment.csv'))==sum(r['status']=='Stock equipment' for r in rows)
    bykey=dict(zip(csvkeys,rows))
    assert bykey[414,26]['method']=='Corpse parts' and all(bykey[867,f]['method']=='Corpse parts' for f in (0,32))
    with Image.open(root/'images'/(bykey[867,0]['target_image']+'.png')) as floor, Image.open(root/'images'/(bykey[867,32]['target_image']+'.png')) as reflected:
        expected=floor.transpose(Image.Transpose.TRANSPOSE)
        assert expected.size==reflected.size and expected.tobytes()==reflected.tobytes()
    assert all(bykey[867,f]['method']=='Death pose' for f in range(1,5))
    assert len({bykey[867,f]['target_image'] for f in range(5)})==5
    assert bykey[414,27]['uo_id']!=bykey[414,28]['uo_id']
    from costumes import WARDROBES
    outfits=table('outfits.csv')
    assert {int(r['u7_shape']) for r in outfits}==set(WARDROBES)
    assert len(outfits)==sum(len(parts) for name,body,parts in WARDROBES.values())
    assert all(r['status']=='Stock outfit' for r in rows if int(r['shape']) in WARDROBES and r['target_image'])
    assert table('custom-art.csv')==[r for r in rows if r['status']=='Custom art']
    assert all(r['target_image'] for r in rows if r['status']=='Review substitute')
    for k,v in evidence['output_sha256'].items():assert digest(root/k)==v
    js=(root/'catalog.js').read_text('utf8')
    data=json.loads(js.removeprefix('const CATALOG=').rstrip().removesuffix(';'))
    assert len(data)==len(rows)
    for j,r in zip(data,rows):assert all(str(v)==r[k] for k,v in j.items())
    return f'PASS · {len(rows)} keys, {len(refs)} witnessed records, {len(ground)} terrain cells, {len(allpng)} decoded PNGs, all prior keys retained'
def table_external(p):
    with p.open(encoding='utf-8-sig',newline='') as h:return list(csv.DictReader(h))
if __name__=='__main__':
    print(verify(Path(sys.argv[1]) if len(sys.argv)>1 else BASE/'atlas'))

