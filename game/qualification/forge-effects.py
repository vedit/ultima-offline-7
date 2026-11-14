"""Check original Trinsic forge animation and cooldown, without changing blank frames."""
import json,runpy,time
from pathlib import Path
from play import session
audit=runpy.run_path(str(Path(__file__).with_name('item-use-audit.py')))
with session('forge-effects','Investigation',True,{'TRINSIC_PREPARE':'interaction-audit'}) as (folder,env,host):
    p=audit['BoundedPipe'](env['TRINSIC_PIPE'],host)
    assert p.raw(f'{int(p.head[4])+1} {p.head[2]} AUDITVISIT 972 2291 0')=='ok'
    bellows=next(r for r in p.rows if r[1]==431 and r[3:5]==[971,2291])
    fire=next(r for r in p.rows if r[1]==739 and r[3:5]==[968,2292])
    assert fire[2]==0
    assert p.send('USE',bellows[0])=='using'
    observed=[];end=time.monotonic()+10
    while time.monotonic()<end:
        time.sleep(.025);p.sync()
        b=next(r[2] for r in p.rows if r[0]==bellows[0]);f=next(r[2] for r in p.rows if r[0]==fire[0])
        if not observed or observed[-1]!=[b,f]:observed.append([b,f])
        if any(f>0 for b,f in observed) and b==0 and f==0:break
    assert any(b>0 for b,f in observed) and any(f==3 for b,f in observed),observed
    assert observed[-1]==[0,0],observed
    audit['settle'](p);audit['movement'](p)
    (folder/'forge.json').write_text(json.dumps(observed,indent=2));p.close()
    print('Original bellows motion, fire heat and cooldown, movement recovery passed.',flush=True)
