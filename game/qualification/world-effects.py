"""Assert retail Usecode effects, beyond dispatch-and-cancel coverage."""
import json,runpy,time
from pathlib import Path
from play import session
audit=runpy.run_path(str(Path(__file__).with_name('item-use-audit.py')))
with session('world-effects','Investigation',True,{'TRINSIC_PREPARE':'interaction-audit'}) as (folder,env,host):
    p=audit['BoundedPipe'](env['TRINSIC_PIPE'],host); evidence=[]
    def row(id): return next(r for r in p.rows if r[0]==id)
    def visit(x,y):
        assert p.raw(f'{int(p.head[4])+1} {p.head[2]} AUDITVISIT {x} {y} 0')=='ok'
    def wait(predicate,seconds=12):
        end=time.monotonic()+seconds
        while time.monotonic()<end:
            time.sleep(.03);p.sync()
            if predicate():return
        raise AssertionError((p.head,p.frame[-1500:]))
    visit(1076,2201)
    assert row(10808)[1:3]==[810,2],row(10808)
    assert p.send('MOVE',10808,88)=='ok'
    # This retail bucket starts with blood. Drinking is refused and preserves it.
    p.send('USE',10808);wait(lambda:int(p.head[9])==4)
    p.send('TARGET',int(p.head[10]),56);audit['settle'](p)
    assert row(10808)[2]==2
    assert any('No, thank thee.' in bytes.fromhex(l.split()[3]).decode('cp437') for l in p.frame.splitlines() if l.startswith('B '))
    evidence.append('Original blood-bucket drinking refusal preserves blood')
    # Pour onto reachable ground using the original position target and posted path.
    blood={r[0] for r in p.rows if r[1]==912}
    p.send('USE',10808);wait(lambda:int(p.head[9])==4)
    assert p.raw(f'{int(p.head[4])+1} {p.head[2]} TARGETPOS {p.head[10]} 1076 2202 0')=='ok'
    wait(lambda:any(r[1]==912 and r[0] not in blood for r in p.rows))
    evidence.append('Blood bucket poured by original target/path/post-action logic')
    audit['settle'](p)
    visit(1078,2238)
    assert p.send('MOVE',12552,88)=='ok'
    visit(1071,2235)
    p.send('USE',12552);wait(lambda:int(p.head[9])==4)
    assert p.send('TARGET',int(p.head[10]),12568)=='ok'
    wait(lambda:row(12552)[2]==1)
    evidence.append('Well fills bucket through original scripted animation')
    p.send('USE',12552);wait(lambda:int(p.head[9])==4)
    p.send('TARGET',int(p.head[10]),56)
    wait(lambda:row(12552)[2]==0)
    evidence.append('Avatar drinks water and bucket empties')
    audit['settle'](p);audit['movement'](p)
    assert p.send('SAVE')=='ok';assert p.send('LOAD')=='ok';assert row(12552)[2]==0 and row(12552)[6]==88
    evidence.append('Bucket frame and inventory ownership survive save/load')
    (folder/'effects.json').write_text(json.dumps(evidence,indent=2))
    p.close();print(evidence,flush=True)
