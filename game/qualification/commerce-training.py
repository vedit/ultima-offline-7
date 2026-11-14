"""Exercise native shop transactions and training eligibility without replacing scripts."""
import json,runpy,time
from pathlib import Path
from play import session,ROOT
from baseline import actor
from reference import members
audit=runpy.run_path(str(Path(__file__).with_name('item-use-audit.py')))
with session('commerce-training','Investigation',True,{'TRINSIC_PREPARE':'interaction-audit'}) as (folder,env,host):
    p=audit['BoundedPipe'](env['TRINSIC_PIPE'],host);evidence=[]
    def visit(n):
        x,y,z=actor(members(ROOT/'fixtures/Investigation.U7'),n)['xyz']
        assert p.raw(f'{int(p.head[4])+1} {p.head[2]} AUDITVISIT {x+1} {y} {z}')=='ok'
    def total(shape):return sum(r[9] for r in p.rows if r[1]==shape and r[6] in (56,88,184,200))
    def talk(n,topics):
        npc=next(r for r in p.rows if r[7]==n);assert p.send('USE',npc[0])=='using'
        pending=list(topics);seen=[];visited=False;end=time.monotonic()+30
        while time.monotonic()<end:
            time.sleep(.025);p.sync();mode=int(p.head[9]);token=int(p.head[10])
            if not mode:
                if visited:break
                continue
            visited=True
            seen.extend(bytes.fromhex(l[2:]).decode('cp437') for l in p.frame.splitlines() if l.startswith('T '))
            if mode==1:p.send('ANSWER',token,0)
            elif mode==2:
                choice=next((t for t in pending if t in p.choices),None)
                assert choice,(p.choices,pending,seen[-1:])
                pending.remove(choice);print('choice',choice,flush=True)
                p.send('ANSWER',token,p.choices.index(choice))
            elif mode==4:p.send('TARGET',token,56)
            else:raise AssertionError((mode,p.head))
        else:raise TimeoutError('Conversation did not return')
        assert not pending,pending
        return ' '.join(seen)
    visit(18);gold=total(644);buckets=total(810)
    words=talk(18,['Avatar','job','buy','provisions','bucket','Yes','No','bye'])
    assert total(644)==gold-2,(gold,total(644),words)
    assert total(810)==buckets+1,(buckets,total(810))
    evidence.append({'shop':'Dell','gold_spent':2,'buckets_received':1})
    audit['settle'](p);audit['movement'](p)
    visit(20);gold=total(644)
    combat=int(next(l.split()[2] for l in p.frame.splitlines() if l.startswith('P ')))
    words=talk(20,['job','train','No','hexen','bye'])
    assert 'gain in combat ability' in words,words
    assert total(644)==gold-20,(gold,total(644))
    after=int(next(l.split()[2] for l in p.frame.splitlines() if l.startswith('P ')))
    assert after>combat,(combat,after)
    evidence.append({'training':'Markus original training','gold_spent':20,'combat_before':combat,'combat_after':after})
    audit['settle'](p);audit['movement'](p)
    (folder/'commerce.json').write_text(json.dumps(evidence,indent=2));p.close()
    print(evidence,flush=True)
