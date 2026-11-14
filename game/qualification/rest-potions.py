"""Exercise original potion effects and Avatar sleep/wake with normal Usecode inputs."""
import json,runpy,time
from pathlib import Path
from play import session
audit=runpy.run_path(str(Path(__file__).with_name('item-use-audit.py')))
with session('rest-potions','Investigation',True,{'TRINSIC_PREPARE':'interaction-audit'}) as (folder,env,host):
    p=audit['BoundedPipe'](env['TRINSIC_PIPE'],host);evidence=[]
    def visit(x,y):assert p.raw(f'{int(p.head[4])+1} {p.head[2]} AUDITVISIT {x} {y} 0')=='ok'
    def stats():return list(map(int,next(l[2:] for l in p.frame.splitlines() if l.startswith('P ')).split()))
    def wait(predicate,seconds=15):
        end=time.monotonic()+seconds
        while time.monotonic()<end:
            time.sleep(.025);p.sync()
            if predicate():return
        raise AssertionError((p.head,stats()))
    def potion(frame,x,y):
        visit(x,y)
        item=next(r for r in p.rows if r[1]==340 and r[2]==frame and not r[6])
        assert p.send('MOVE',item[0],88)=='ok'
        assert p.send('USE',item[0])=='using';wait(lambda:int(p.head[9])==4)
        assert p.send('TARGET',int(p.head[10]),56)=='ok'
        audit['settle'](p)
        assert not any(r[0]==item[0] for r in p.rows)
    before=stats()[0];potion(1,954,2258)
    maximum=int(next(l.split()[1] for l in p.frame.splitlines() if l.startswith('V ')))
    assert before==maximum and stats()[0]==maximum,(before,maximum,stats())
    evidence.append('Healing potion consumed; health remains within original strength cap')
    potion(3,956,2257);assert stats()[10]&0x2000
    evidence.append('Poison potion sets original poison status')
    potion(2,947,2265);assert not stats()[10]&0x2000
    evidence.append('Cure potion clears original poison status')
    visit(1085,2269);before=int(p.head[3]);assert p.send('USE',13576)=='using'
    hours=False;end=time.monotonic()+35
    while time.monotonic()<end:
        time.sleep(.025);p.sync();mode=int(p.head[9]);token=int(p.head[10])
        if mode==1:p.send('ANSWER',token,0)
        elif mode==3:
            p.send('NUMBER',token,1);hours=True
        elif mode:raise AssertionError((mode,p.head))
        if hours and int(p.head[3])-before>=1500 and not stats()[10]&0x80:break
    else:raise AssertionError(('Rest did not wake',p.head,stats(),hours))
    audit['settle'](p);audit['movement'](p)
    evidence.append('Original bed/rest numeric choice advances one hour and wakes Avatar without movement hold')
    (folder/'effects.json').write_text(json.dumps(evidence,indent=2));p.close();print(evidence,flush=True)
